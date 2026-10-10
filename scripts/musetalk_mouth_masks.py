#!/usr/bin/env python3
"""Extract conservative, frame-aligned MuseTalk lip masks for pause correction.

This helper is launched with the installed MuseTalk Python and working directory so
that it reuses MuseTalk's own FaceParsing model and checkpoints. It deliberately
does not import MuseTalk at module import time; the geometry and mask validation
helpers remain testable offline without loading Torch or a GPU model.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    import cv2
except ImportError:  # Allows non-MuseTalk workflows and syntax tests to import this module.
    cv2 = None

try:
    import numpy as np
except ImportError:  # Geometry-only offline checks do not need NumPy.
    np = None


MOUTH_LABELS = (11, 12, 13)
INNER_MOUTH_LABEL = 11
MUSE_TALK_PARSE_SIZE = (512, 512)
MAX_INNER_MOUTH_FRACTION = 0.18
MAX_MOUTH_APERTURE_RATIO = 0.025
MIN_MOUTH_WIDTH_PIXELS = 12.0
MIN_COLOR_MATCH_LIP_PIXELS = 8
MIN_COLOR_MATCH_PIXELS_PER_LIP_CLASS = 4
MAX_LIP_LUMINANCE_SHIFT = 12.0
MAX_LIP_CHROMA_SHIFT = 18.0
MAX_SPEECH_POSE_PARSE_CANDIDATES_PER_SOURCE_POSE = 8
MAX_SPEECH_POSE_LANDMARK_CHECKS_PER_SOURCE_POSE = 2


def _require_image_dependencies() -> None:
    if cv2 is None or np is None:
        raise RuntimeError("Mouth-only parsing requires the OpenCV and NumPy already present in the MuseTalk runtime.")


def _largest_component_bbox(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    _require_image_dependencies()
    components, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if components <= 1:
        return None
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, width, height, area = [int(value) for value in stats[component]]
    if area <= 0:
        return None
    return x, y, x + width, y + height


def _normalized_bbox(bbox: Sequence[int], width: int, height: int) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    return (x0 / float(width), y0 / float(height), x1 / float(width), y1 / float(height))


def describe_face_and_mouth(labels: np.ndarray) -> Tuple[Optional[Dict[str, Any]], str]:
    """Validate raw MuseTalk parser labels and return tight face/lip geometry.

    MuseTalk's standard FaceParsing wrapper turns labels into broad jaw/raw masks;
    this consumes the same model's raw argmax labels. The frame may be rejected,
    in which case the caller leaves it unmodified.
    """
    _require_image_dependencies()
    if labels.ndim != 2 or labels.size == 0:
        return None, "invalid_label_map_shape"
    if not np.issubdtype(labels.dtype, np.integer):
        return None, "non_integer_label_map"
    height, width = labels.shape
    if width < 32 or height < 32:
        return None, "frame_too_small"
    observed = np.unique(labels)
    if observed.size == 0 or int(observed.max()) > 18 or int(observed.min()) < 0:
        return None, "unexpected_label_ids"

    face_bbox = _largest_component_bbox(labels == 1)
    if face_bbox is None:
        return None, "face_skin_not_detected"
    fx0, fy0, fx1, fy1 = face_bbox
    face_width, face_height = fx1 - fx0, fy1 - fy0
    if face_width < width * 0.12 or face_height < height * 0.12:
        return None, "face_region_too_small"
    if fx0 < 0 or fy0 < 0 or fx1 > width or fy1 > height:
        return None, "face_region_out_of_frame"

    # Restrict lips to the detected skin component's neighborhood, preventing a
    # stray semantic label elsewhere in the frame from becoming a donor mask.
    pad_x = max(2, int(round(face_width * 0.06)))
    pad_y = max(2, int(round(face_height * 0.06)))
    x0, x1 = max(0, fx0 - pad_x), min(width, fx1 + pad_x)
    y0, y1 = max(0, fy0 - pad_y), min(height, fy1 + pad_y)
    mouth_mask = np.isin(labels, MOUTH_LABELS)
    mouth_mask[:y0, :] = False
    mouth_mask[y1:, :] = False
    mouth_mask[:, :x0] = False
    mouth_mask[:, x1:] = False
    mouth_bbox = _largest_component_bbox(mouth_mask)
    mouth_area = int(mouth_mask.sum())
    if mouth_bbox is None or mouth_area < 8:
        return None, "mouth_lip_labels_not_detected"
    mx0, my0, mx1, my1 = mouth_bbox
    mouth_width, mouth_height = mx1 - mx0, my1 - my0
    rel_cx = ((mx0 + mx1) * 0.5 - fx0) / float(face_width)
    rel_cy = ((my0 + my1) * 0.5 - fy0) / float(face_height)
    rel_width = mouth_width / float(face_width)
    rel_height = mouth_height / float(face_height)
    area_fraction = mouth_area / float(face_width * face_height)
    if not (0.15 <= rel_cx <= 0.85 and 0.35 <= rel_cy <= 0.98):
        return None, "mouth_outside_expected_face_region"
    if not (0.045 <= rel_width <= 0.80 and 0.012 <= rel_height <= 0.45):
        return None, "mouth_geometry_out_of_range"
    if not (0.0004 <= area_fraction <= 0.20):
        return None, "mouth_mask_area_out_of_range"

    inner_area = int(np.logical_and(labels == INNER_MOUTH_LABEL, mouth_mask).sum())
    inner_fraction = inner_area / float(mouth_area)
    return {
        "face_bbox": [fx0, fy0, fx1, fy1],
        "face_bbox_normalized": list(_normalized_bbox(face_bbox, width, height)),
        "mouth_bbox": [mx0, my0, mx1, my1],
        "mouth_center_relative_to_face": [round(rel_cx, 6), round(rel_cy, 6)],
        "mouth_size_relative_to_face": [round(rel_width, 6), round(rel_height, 6)],
        "mouth_area_pixels": mouth_area,
        "inner_mouth_fraction": round(inner_fraction, 6),
        "mouth_mask": mouth_mask,
    }, "ok"


def is_closed_donor(descriptor: Mapping[str, Any]) -> bool:
    """Require both semantic parsing and measured lip landmarks to indicate closure."""
    try:
        aperture_ratio = float(descriptor["mouth_aperture_ratio"])
        parser_fraction = float(descriptor["inner_mouth_fraction"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        descriptor.get("mouth_aperture_status") == "measured"
        and parser_fraction <= MAX_INNER_MOUTH_FRACTION
        and math.isfinite(aperture_ratio)
        and aperture_ratio <= MAX_MOUTH_APERTURE_RATIO
    )


def measure_mouth_aperture(
    landmarks: Any,
    image_shape: Optional[Sequence[int]] = None,
    min_mouth_width_pixels: float = MIN_MOUTH_WIDTH_PIXELS,
) -> Tuple[Optional[float], str, Optional[float]]:
    """Measure inner-lip opening normalized by mouth width from 68-point landmarks.

    This pure geometry helper deliberately accepts NumPy-like input without importing
    the face detector or Torch. Missing, malformed, or low-resolution landmarks fail
    closed so parser labels alone cannot certify a donor as neutral.
    """
    try:
        points = [[float(value) for value in point] for point in landmarks]
    except (TypeError, ValueError):
        return None, "invalid_landmarks", None
    if len(points) != 68 or any(len(point) != 2 for point in points):
        return None, "invalid_landmark_shape", None
    if not all(math.isfinite(value) for point in points for value in point):
        return None, "non_finite_landmarks", None
    if image_shape is not None:
        if len(image_shape) < 2:
            return None, "invalid_image_shape", None
        image_height, image_width = int(image_shape[0]), int(image_shape[1])
        if image_height < 1 or image_width < 1:
            return None, "invalid_image_shape", None
        mouth_points = points[48:68]
        if (
            any(point[0] < 0 or point[0] >= image_width for point in mouth_points)
            or any(point[1] < 0 or point[1] >= image_height for point in mouth_points)
        ):
            return None, "mouth_landmarks_out_of_frame", None

    left_corner, right_corner = points[48], points[54]
    mouth_axis = [right_corner[0] - left_corner[0], right_corner[1] - left_corner[1]]
    mouth_width = math.hypot(mouth_axis[0], mouth_axis[1])
    if not math.isfinite(mouth_width) or mouth_width < float(min_mouth_width_pixels):
        return None, "mouth_width_too_small", mouth_width if math.isfinite(mouth_width) else None
    axis = [mouth_axis[0] / mouth_width, mouth_axis[1] / mouth_width]
    normal = [-axis[1], axis[0]]
    if abs(normal[1]) < 0.25:
        return None, "mouth_orientation_uncertain", mouth_width
    # Orient the normal toward the lower lip in image coordinates, including rolled heads.
    if normal[1] < 0:
        normal = [-normal[0], -normal[1]]
    upper_lower_pairs = ((61, 67), (62, 66), (63, 65))
    gaps = [((points[lower][0] - points[upper][0]) * normal[0]
             + (points[lower][1] - points[upper][1]) * normal[1])
            for upper, lower in upper_lower_pairs]
    if not all(math.isfinite(gap) for gap in gaps):
        return None, "invalid_lip_geometry", mouth_width
    if max(gaps) <= 0.0:
        return None, "non_positive_inner_lip_aperture", mouth_width
    aperture_ratio = max(0.0, max(gaps)) / mouth_width
    return float(aperture_ratio), "measured", mouth_width


def detect_mouth_aperture(detector: Any, image_bgr: np.ndarray) -> Tuple[Optional[float], str, Optional[float]]:
    """Run an injected face-alignment detector and measure its largest face."""
    _require_image_dependencies()
    if detector is None:
        return None, "landmark_detector_unavailable", None
    if image_bgr is None or image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        return None, "invalid_image", None
    try:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        predictions = detector.get_landmarks(image_rgb)
    except Exception as error:
        return None, "landmark_detector_error:" + type(error).__name__, None
    if predictions is None:
        return None, "face_landmarks_not_detected", None
    valid: List[Tuple[float, Sequence[Sequence[float]]]] = []
    for prediction in predictions:
        try:
            points = [[float(value) for value in point] for point in prediction]
        except (TypeError, ValueError):
            continue
        if len(points) != 68 or any(len(point) != 2 for point in points):
            continue
        if not all(math.isfinite(value) for point in points for value in point):
            continue
        jaw = points[:17]
        area = float(
            (max(point[0] for point in jaw) - min(point[0] for point in jaw))
            * (max(point[1] for point in jaw) - min(point[1] for point in jaw))
        )
        if area > 0:
            valid.append((area, points))
    if not valid:
        return None, "face_landmarks_invalid", None
    valid.sort(key=lambda item: item[0], reverse=True)
    aperture, reason, mouth_width = measure_mouth_aperture(valid[0][1], image_bgr.shape[:2])
    if len(valid) > 1 and valid[1][0] >= valid[0][0] * 0.9:
        return None, "ambiguous_multiple_faces", mouth_width
    return aperture, reason, mouth_width


def _face_alignment_detector(torch: Any) -> Tuple[Optional[Any], Optional[str]]:
    """Load the already-declared face-alignment dependency only in the MuseTalk process."""
    try:
        import face_alignment

        landmark_types = face_alignment.LandmarksType
        landmark_type = getattr(landmark_types, "TWO_D", None)
        if landmark_type is None:
            landmark_type = getattr(landmark_types, "_2D", None)
        if landmark_type is None:
            return None, "face_alignment_2d_landmark_type_unavailable"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        return face_alignment.FaceAlignment(landmark_type, flip_input=False, device=device), None
    except Exception as error:
        return None, "face_alignment_init_error:" + type(error).__name__


def _exact_mapped_donor(
    output_request: Mapping[str, Any],
    donor_cache: Mapping[int, Tuple[np.ndarray, Dict[str, Any], Dict[str, Any]]],
) -> Optional[Tuple[int, np.ndarray, Dict[str, Any], Dict[str, Any]]]:
    """Return only the requested exact source-index donor; never search nearby frames."""
    source_index = int(output_request.get("exact_source_frame_index", -1))
    donor_index = int(output_request.get("donor_frame_index", -1))
    if source_index < 0 or donor_index != source_index:
        return None
    donor = donor_cache.get(donor_index)
    if donor is None:
        return None
    return donor_index, *donor


def _exact_source_donor_missing_reason(
    donor_index: int,
    source_frame_count: int,
    donor_frame_count: int,
    trailing_truncation_verified: bool,
) -> Optional[str]:
    if (trailing_truncation_verified and donor_frame_count == source_frame_count - 1
            and donor_index == source_frame_count - 1):
        return "exact_mapped_donor_frame_missing_trailing_truncation"
    return None


def _pingpong_frame_index(frame_index: int, source_frame_count: int) -> int:
    if source_frame_count < 1 or frame_index < 0:
        raise ValueError("Ping-pong frame mapping requires nonnegative output and positive source counts.")
    position = frame_index % (2 * source_frame_count)
    return position if position < source_frame_count else 2 * source_frame_count - 1 - position


def _bounded_evenly_spaced_indices(indices: Sequence[int], maximum: int) -> List[int]:
    """Choose a deterministic timeline-spanning candidate subset without growing with duration."""
    ordered = sorted(set(int(index) for index in indices))
    if maximum < 1:
        raise ValueError("Candidate shortlist maximum must be positive.")
    if len(ordered) <= maximum:
        return ordered
    if maximum == 1:
        return [ordered[len(ordered) // 2]]
    selected = []
    for position in range(maximum):
        source_position = int(round(position * (len(ordered) - 1) / float(maximum - 1)))
        selected.append(ordered[source_position])
    return sorted(set(selected))


def _derive_speech_pose_candidates(
    requests: Mapping[int, Mapping[str, Any]],
    pause_intervals: Sequence[Mapping[str, Any]],
    donor_frame_count: int,
    motion_base_frame_count: int,
    fps: int,
) -> Dict[int, List[int]]:
    """Derive only active, in-video donors that match a requested source pose exactly."""
    if donor_frame_count < 1 or motion_base_frame_count < 1 or fps < 1:
        raise ValueError("Speech-pose candidate mapping requires valid frame counts and FPS.")
    pause_indices = set(requests)
    target_source_indices: set[int] = set()
    for output_index, item in requests.items():
        source_index = int(item.get("exact_source_frame_index", -1))
        if source_index != _pingpong_frame_index(output_index, motion_base_frame_count):
            raise ValueError("Speech-pose request source index does not match the exact ping-pong mapping.")
        target_source_indices.add(source_index)
    candidate_map: Dict[int, List[int]] = {index: [] for index in sorted(target_source_indices)}
    for output_index in range(donor_frame_count):
        if output_index in pause_indices:
            continue
        start = output_index / float(fps)
        end = (output_index + 1) / float(fps)
        if any(
            float(interval["start_seconds"]) < end - 1e-9
            and float(interval["end_seconds"]) > start + 1e-9
            for interval in pause_intervals
        ):
            continue
        source_index = _pingpong_frame_index(output_index, motion_base_frame_count)
        if source_index in candidate_map:
            candidate_map[source_index].append(output_index)
    return candidate_map


def _face_mouth_geometry_deltas(
    target: Mapping[str, Any], donor: Mapping[str, Any], width: int, height: int,
) -> Dict[str, List[float] | float]:
    tf = target["face_bbox"]
    df = donor["face_bbox"]
    tm = target["mouth_center_relative_to_face"]
    dm = donor["mouth_center_relative_to_face"]
    tw, th = tf[2] - tf[0], tf[3] - tf[1]
    dw, dh = df[2] - df[0], df[3] - df[1]
    tcenter = ((tf[0] + tf[2]) * 0.5 / width, (tf[1] + tf[3]) * 0.5 / height)
    dcenter = ((df[0] + df[2]) * 0.5 / width, (df[1] + df[3]) * 0.5 / height)
    center_delta = (abs(tcenter[0] - dcenter[0]), abs(tcenter[1] - dcenter[1]))
    scale_delta = (abs(tw / float(dw) - 1.0), abs(th / float(dh) - 1.0))
    mouth_delta = (abs(float(tm[0]) - float(dm[0])), abs(float(tm[1]) - float(dm[1])))
    target_mouth_width = float(target["mouth_size_relative_to_face"][0])
    donor_mouth_width = float(donor["mouth_size_relative_to_face"][0])
    mouth_width_delta = abs(target_mouth_width - donor_mouth_width)
    return {
        "normalized_face_center_delta": [center_delta[0], center_delta[1]],
        "face_scale_delta": [scale_delta[0], scale_delta[1]],
        "relative_mouth_center_delta": [mouth_delta[0], mouth_delta[1]],
        "relative_mouth_width_delta": mouth_width_delta,
    }


def compare_face_geometry(
    target: Mapping[str, Any], donor: Mapping[str, Any], width: int, height: int,
) -> Tuple[bool, float, str]:
    """Conservative normalized face-box/mouth-shape proxy for donor alignment."""
    deltas = _face_mouth_geometry_deltas(target, donor, width, height)
    center_delta = deltas["normalized_face_center_delta"]
    scale_delta = deltas["face_scale_delta"]
    mouth_delta = deltas["relative_mouth_center_delta"]
    mouth_width_delta = deltas["relative_mouth_width_delta"]
    # Mouth patches are small: the old face-box gates allowed several pixels
    # of displacement at the mouth, which leaves a visible lip/skin outline.
    if center_delta[0] > 0.025 or center_delta[1] > 0.025:
        return False, float("inf"), "face_center_mismatch"
    if scale_delta[0] > 0.07 or scale_delta[1] > 0.07:
        return False, float("inf"), "face_scale_mismatch"
    if mouth_delta[0] > 0.025 or mouth_delta[1] > 0.04 or mouth_width_delta > 0.08:
        return False, float("inf"), "mouth_pose_proxy_mismatch"
    score = (
        center_delta[0] + center_delta[1]
        + 0.25 * (scale_delta[0] + scale_delta[1])
        + 0.5 * (mouth_delta[0] + mouth_delta[1])
        + 0.25 * mouth_width_delta
    )
    return True, score, "ok"


def build_feathered_mouth_mask(labels: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[Dict[str, Any]], str]:
    _require_image_dependencies()
    descriptor, reason = describe_face_and_mouth(labels)
    if descriptor is None:
        return None, None, reason
    mask = (descriptor["mouth_mask"].astype(np.uint8) * 255)
    # Minimal expansion closes tiny segmentation gaps; blur stays local to the
    # parser-defined lip contour instead of using a screen-space rectangle.
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.GaussianBlur(mask, (5, 5), 0.9)
    descriptor = {key: value for key, value in descriptor.items() if key != "mouth_mask"}
    return mask, descriptor, "ok"


def _raw_label_map(parser: Any, image_bgr: np.ndarray, torch: Any) -> np.ndarray:
    _require_image_dependencies()
    from PIL import Image

    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Input frame must be a 3-channel image.")
    height, width = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    resampling = getattr(Image, "Resampling", Image)
    pil_image = Image.fromarray(rgb).resize(MUSE_TALK_PARSE_SIZE, resampling.BILINEAR)
    tensor = parser.preprocess(pil_image).unsqueeze(0)
    try:
        device = next(parser.net.parameters()).device
    except (StopIteration, AttributeError):
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tensor = tensor.to(device)
    with torch.no_grad():
        logits = parser.net(tensor)[0]
    labels = logits.squeeze(0).argmax(0).detach().cpu().numpy().astype(np.uint8)
    return cv2.resize(labels, (width, height), interpolation=cv2.INTER_NEAREST)


def _read_frame(capture: Any, frame_index: int) -> Optional[np.ndarray]:
    _require_image_dependencies()
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
    ok, frame = capture.read()
    return frame if ok and frame is not None else None


def _geometry_report(descriptor: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if descriptor is None:
        return None
    keys = (
        "face_bbox", "face_bbox_normalized", "mouth_bbox", "mouth_center_relative_to_face",
        "mouth_size_relative_to_face", "mouth_area_pixels", "inner_mouth_fraction",
        "mouth_aperture_ratio", "mouth_aperture_status", "mouth_width_pixels_landmarked",
    )
    return {key: descriptor[key] for key in keys if key in descriptor}


def _warp_donor_to_target(
    donor_frame: np.ndarray, donor_bbox: Sequence[int], target_bbox: Sequence[int],
    donor_anchor_bbox: Optional[Sequence[int]] = None,
    target_anchor_bbox: Optional[Sequence[int]] = None,
    interpolation: Optional[int] = None,
    preserve_donor_scale: bool = False,
) -> np.ndarray:
    _require_image_dependencies()
    dh, dw = donor_frame.shape[:2]
    tx0, ty0, tx1, ty1 = [float(value) for value in target_bbox]
    dx0, dy0, dx1, dy1 = [float(value) for value in donor_bbox]
    sx, sy = (tx1 - tx0) / (dx1 - dx0), (ty1 - ty0) / (dy1 - dy0)
    offset_x, offset_y = tx0 - sx * dx0, ty0 - sy * dy0
    if preserve_donor_scale:
        # Same-pose donors already share the motion-base framing. Translate their
        # closed lips into the target mouth center without resizing the aperture.
        sx = sy = 1.0
        if donor_anchor_bbox is None or target_anchor_bbox is None:
            raise ValueError("Scale-preserving donor alignment requires donor and target mouth anchors.")
        dmx0, dmy0, dmx1, dmy1 = [float(value) for value in donor_anchor_bbox]
        tmx0, tmy0, tmx1, tmy1 = [float(value) for value in target_anchor_bbox]
        offset_x = (tmx0 + tmx1 - dmx0 - dmx1) * 0.5
        offset_y = (tmy0 + tmy1 - dmy0 - dmy1) * 0.5
    elif donor_anchor_bbox is not None and target_anchor_bbox is not None:
        dmx0, dmy0, dmx1, dmy1 = [float(value) for value in donor_anchor_bbox]
        tmx0, tmy0, tmx1, tmy1 = [float(value) for value in target_anchor_bbox]
        donor_center = ((dmx0 + dmx1) * 0.5, (dmy0 + dmy1) * 0.5)
        target_center = ((tmx0 + tmx1) * 0.5, (tmy0 + tmy1) * 0.5)
        # Preserve face-derived scale but anchor the transform on the lips;
        # this avoids carrying the face-box translation error into the patch.
        offset_x = target_center[0] - sx * donor_center[0]
        offset_y = target_center[1] - sy * donor_center[1]
    matrix = np.asarray([[sx, 0.0, offset_x], [0.0, sy, offset_y]], dtype=np.float32)
    flags = cv2.INTER_LINEAR if interpolation is None else interpolation
    return cv2.warpAffine(donor_frame, matrix, (dw, dh), flags=flags, borderMode=cv2.BORDER_REPLICATE)


def _match_donor_lip_color(
    donor_bgr: np.ndarray,
    target_bgr: np.ndarray,
    alpha: np.ndarray,
    target_labels: np.ndarray,
    donor_labels: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Match bounded donor lip color to the target's visible lip pixels.

    Upper/lower lip classes are matched independently in Lab. Inner-mouth
    pixels are deliberately preserved; bounded shifts avoid blurring or
    recoloring pixels outside the semantic lip patch.
    """
    _require_image_dependencies()
    if (donor_bgr.shape != target_bgr.shape or donor_bgr.ndim != 3
            or donor_bgr.shape[2] != 3 or alpha.shape != target_labels.shape
            or target_labels.shape != donor_labels.shape):
        return donor_bgr, {"status": "skipped", "reason": "color_match_shape_mismatch", "sample_pixel_count": 0}

    alpha_mask = alpha > 0
    lip_samples = {
        label: (target_labels == label) & (donor_labels == label) & alpha_mask
        for label in (12, 13)
    }
    sample_counts = {str(label): int(np.count_nonzero(mask)) for label, mask in lip_samples.items()}
    sample_count = sum(sample_counts.values())
    if sample_count < MIN_COLOR_MATCH_LIP_PIXELS:
        return donor_bgr, {
            "status": "skipped", "reason": "insufficient_corresponding_lip_pixels",
            "sample_pixel_count": sample_count, "sample_pixel_counts_by_label": sample_counts,
        }

    target_lab = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    donor_lab = cv2.cvtColor(donor_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    adjusted_lab = donor_lab.copy()
    lip_adjustments: Dict[str, Dict[str, Any]] = {}
    donor_lips = np.isin(donor_labels, (12, 13)) & alpha_mask
    for label, sample_mask in lip_samples.items():
        count = sample_counts[str(label)]
        if count < MIN_COLOR_MATCH_PIXELS_PER_LIP_CLASS:
            return donor_bgr, {
                "status": "skipped", "reason": "insufficient_corresponding_lip_class_pixels",
                "sample_pixel_count": sample_count, "sample_pixel_counts_by_label": sample_counts,
            }
        target_median = np.median(target_lab[sample_mask], axis=0)
        donor_median = np.median(donor_lab[sample_mask], axis=0)
        requested_shift = target_median - donor_median
        applied_shift = np.asarray([
            np.clip(requested_shift[0], -MAX_LIP_LUMINANCE_SHIFT, MAX_LIP_LUMINANCE_SHIFT),
            np.clip(requested_shift[1], -MAX_LIP_CHROMA_SHIFT, MAX_LIP_CHROMA_SHIFT),
            np.clip(requested_shift[2], -MAX_LIP_CHROMA_SHIFT, MAX_LIP_CHROMA_SHIFT),
        ])
        donor_class = (donor_labels == label) & alpha_mask
        for channel in range(3):
            adjusted_lab[donor_class, channel] = np.clip(
                adjusted_lab[donor_class, channel] + applied_shift[channel], 0, 255,
            )
        lip_adjustments[str(label)] = {
            "sample_pixel_count": count,
            "requested_delta_lab": [round(float(value), 3) for value in requested_shift],
            "applied_delta_lab": [round(float(value), 3) for value in applied_shift],
        }
    converted_bgr = cv2.cvtColor(np.rint(adjusted_lab).astype(np.uint8), cv2.COLOR_LAB2BGR)
    adjusted_bgr = donor_bgr.copy()
    adjusted_bgr[donor_lips] = converted_bgr[donor_lips]
    return adjusted_bgr, {
        "status": "applied",
        "method": "bounded_per_class_median_Lab_color_match",
        "sample_pixel_count": sample_count,
        "sample_pixel_counts_by_label": sample_counts,
        "class_adjustments": lip_adjustments,
        "maximum_absolute_shift_lab": [
            MAX_LIP_LUMINANCE_SHIFT, MAX_LIP_CHROMA_SHIFT, MAX_LIP_CHROMA_SHIFT,
        ],
        "luminance_adjusted": True,
        "inner_mouth_adjusted": False,
    }


def run_extraction(
    rendered_video: Path,
    reference_video: Path,
    mask_directory: Path,
    donor_directory: Path,
    report_path: Path,
    request_path: Path,
    parser: Any,
    torch: Any,
    landmark_detector: Any = None,
    landmark_detector_error: Optional[str] = None,
) -> Dict[str, Any]:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    fps = int(request["fps"])
    width, height = int(request["width"]), int(request["height"])
    output_frame_count = int(request["output_frame_count"])
    donor_mode = str(request.get("donor_mode", "quiet-source"))
    if donor_mode not in ("quiet-source", "silence-conditioned-exact-source", "speech-pose-bank"):
        raise ValueError("Unsupported mouth donor mode: {}".format(donor_mode))
    requests = {int(item["output_frame_index"]): item for item in request["output_pause_frames"]}
    pause_indices = set(requests)
    motion_base_frame_count = int(request.get("motion_base_frame_count", request.get("donor_source_frame_count", 0)))
    donor_frame_count = int(request.get("donor_video_frame_count", output_frame_count))
    pause_intervals = request.get("pause_intervals") or []
    speech_pose_candidates: Dict[int, List[int]] = {}
    if donor_mode == "quiet-source":
        source_candidates = [int(index) for index in request.get("quiet_source_frame_indices", [])]
    elif donor_mode == "silence-conditioned-exact-source":
        source_candidates = sorted({int(item.get("donor_frame_index", -1)) for item in requests.values()})
    else:
        speech_pose_candidates = _derive_speech_pose_candidates(
            requests, pause_intervals, donor_frame_count, motion_base_frame_count, fps,
        )
        supplied = {
            int(source_index): sorted(set(int(index) for index in indices))
            for source_index, indices in (request.get("speech_pose_candidate_frame_indices_by_source") or {}).items()
        }
        if supplied != speech_pose_candidates:
            raise ValueError(
                "Speech-pose candidate indices do not match pause exclusions and exact ping-pong source mapping."
            )
        speech_pose_candidates = {
            source_index: _bounded_evenly_spaced_indices(
                candidates, MAX_SPEECH_POSE_PARSE_CANDIDATES_PER_SOURCE_POSE,
            )
            for source_index, candidates in speech_pose_candidates.items()
        }
        source_candidates = sorted({index for indices in speech_pose_candidates.values() for index in indices})
    if fps < 1 or width < 1 or height < 1 or output_frame_count < 1:
        raise ValueError("Invalid frame geometry in mouth-mask request.")
    if not requests:
        raise ValueError("No output pause frames were supplied for mouth correction.")
    if not source_candidates and donor_mode != "speech-pose-bank":
        raise ValueError("No eligible donor frames were supplied.")
    if any(index < 0 or index >= output_frame_count for index in requests):
        raise ValueError("Pause-frame index is outside the requested output timeline.")
    donor_source_frame_count = int(request.get("donor_source_frame_count", donor_frame_count))
    trailing_truncation_verified = request.get("donor_trailing_truncation_verified") is True
    if donor_frame_count < 1 or donor_source_frame_count < 1:
        raise ValueError("Invalid donor frame count in mouth-mask request.")
    if donor_mode == "silence-conditioned-exact-source":
        if trailing_truncation_verified and donor_frame_count != donor_source_frame_count - 1:
            raise ValueError("Trailing-truncation verification does not match the donor/source frame counts.")
        if donor_frame_count != donor_source_frame_count and not (
                trailing_truncation_verified and donor_frame_count == donor_source_frame_count - 1):
            raise ValueError("Silence-conditioned donor frame count is not an approved exact/prefix match.")
        if any(index < 0 or index >= donor_source_frame_count for index in source_candidates):
            raise ValueError("Mapped donor-frame index is outside the motion-base source timeline.")
        if any(index >= donor_frame_count and not (
                trailing_truncation_verified and index == donor_source_frame_count - 1)
               for index in source_candidates):
            raise ValueError("Donor-frame index is outside the supplied donor video.")
    elif any(index < 0 or index >= donor_frame_count for index in source_candidates):
        raise ValueError("Donor-frame index is outside the supplied donor video.")
    if donor_mode == "silence-conditioned-exact-source":
        for item in requests.values():
            source_index = int(item.get("exact_source_frame_index", -1))
            donor_index = int(item.get("donor_frame_index", -1))
            if source_index < 0 or source_index != donor_index:
                raise ValueError("Silence-conditioned mode requires donor_frame_index to equal the exact ping-pong source frame.")
    elif donor_mode == "speech-pose-bank":
        if motion_base_frame_count < 1:
            raise ValueError("Speech-pose mode requires the verified motion-base frame count.")
        if donor_frame_count < output_frame_count:
            raise ValueError("Speech-pose donor video must cover the complete requested output preview.")
        if any(index < 0 or index >= donor_frame_count for index in source_candidates):
            raise ValueError("Speech-pose donor frame is outside the rendered output timeline.")
    speech_pose_by_candidate = {
        donor_index: source_index
        for source_index, indices in speech_pose_candidates.items()
        for donor_index in indices
    }

    _require_image_dependencies()
    rendered_capture = cv2.VideoCapture(str(rendered_video))
    reference_capture = cv2.VideoCapture(str(reference_video))
    if not rendered_capture.isOpened() or not reference_capture.isOpened():
        raise RuntimeError("Could not open rendered video or the selected mouth-donor video for mask extraction.")
    donor_cache: Dict[int, Tuple[np.ndarray, Dict[str, Any], Dict[str, Any]]] = {}
    donor_validation: Dict[int, Dict[str, Any]] = {}
    reasons: Counter[str] = Counter()
    missing_terminal_reason = (
        _exact_source_donor_missing_reason(
            donor_source_frame_count - 1, donor_source_frame_count, donor_frame_count,
            trailing_truncation_verified,
        ) if donor_mode == "silence-conditioned-exact-source" else None
    )
    if missing_terminal_reason:
        donor_validation[donor_source_frame_count - 1] = {
            "status": "skipped",
            "reason": missing_terminal_reason,
            "closed_mouth_metric": None,
        }
    selected_donors: Counter[int] = Counter()
    mask_areas: List[int] = []
    corrected_indices: List[int] = []
    selected_donor_by_output_frame: Dict[str, int] = {}
    frame_diagnostics: Dict[int, Dict[str, Any]] = {
        output_index: {
            "output_frame_index": output_index,
            "timestamp_seconds": round(output_index / float(fps), 6),
            "frame_interval_seconds": [round(output_index / float(fps), 6),
                                       round((output_index + 1) / float(fps), 6)],
            "exact_source_frame_index": int(item.get("exact_source_frame_index", -1)),
            "source_frame_index": int(item.get("exact_source_frame_index", -1)),
            "donor_frame_index_requested": int(item.get("donor_frame_index", -1)) if donor_mode == "silence-conditioned-exact-source" else None,
            "donor_frame_indices_requested": list(speech_pose_candidates.get(int(item.get("exact_source_frame_index", -1)), [])) if donor_mode == "speech-pose-bank" else None,
            "donor_frame_index": None,
            "patch_prepared": False,
            "status": "skipped",
            "skip_reason": "not_processed",
            "target_geometry": None,
            "mask_pixel_count": 0,
            "alpha_written_pixel_count": 0,
            "donor_alignment_rejection_reasons": {},
            "selected_donor_frame_index": None,
            "selected_donor_geometry": None,
            "selected_donor_geometry_deltas": None,
            "selected_donor_closed_mouth_metric": None,
            "selected_donor_mouth_aperture_metric": None,
            "selected_donor_geometry_score": None,
            "lip_color_adjustment": None,
        }
        for output_index, item in requests.items()
    }
    corrected_frames = 0
    started = time.perf_counter()
    zero_mask = np.zeros((height, width), dtype=np.uint8)
    zero_donor = np.zeros((height, width, 3), dtype=np.uint8)
    speech_pose_parse_cache: Dict[int, List[Tuple[int, np.ndarray, Dict[str, Any], np.ndarray]]] = {}

    def validate_closed_donor(
        donor_index: int,
        donor_frame: np.ndarray,
        descriptor: Dict[str, Any],
        labels: np.ndarray,
    ) -> None:
        aperture, aperture_reason, mouth_width = detect_mouth_aperture(landmark_detector, donor_frame)
        descriptor["mouth_aperture_ratio"] = aperture
        descriptor["mouth_aperture_status"] = "measured" if aperture is not None else aperture_reason
        descriptor["mouth_width_pixels_landmarked"] = mouth_width
        landmark_metric = {
            "name": "inner_lip_gap_over_mouth_width",
            "value": round(aperture, 6) if aperture is not None else None,
            "mouth_width_pixels": round(mouth_width, 3) if mouth_width is not None else None,
            "maximum_closed_threshold": MAX_MOUTH_APERTURE_RATIO,
            "status": "measured" if aperture is not None else aperture_reason,
            "passed": aperture is not None and aperture <= MAX_MOUTH_APERTURE_RATIO,
        }
        closed_metric = {
            "name": "inner_mouth_fraction",
            "value": round(float(descriptor.get("inner_mouth_fraction", 1.0)), 6),
            "maximum_closed_threshold": MAX_INNER_MOUTH_FRACTION,
            "parser_passed": float(descriptor.get("inner_mouth_fraction", 1.0)) <= MAX_INNER_MOUTH_FRACTION,
            "landmark_mouth_aperture": landmark_metric,
            "passed": is_closed_donor(descriptor),
        }
        if not is_closed_donor(descriptor):
            reasons["donor_mouth_not_confidently_closed"] += 1
            donor_validation[donor_index] = {
                "status": "skipped", "reason": "donor_mouth_not_confidently_closed",
                "source_frame_index": speech_pose_by_candidate.get(donor_index),
                "landmark_checked": donor_mode == "speech-pose-bank",
                "closed_mouth_metric": closed_metric,
            }
            return
        donor_cache[donor_index] = (donor_frame, descriptor, labels)
        donor_validation[donor_index] = {
            "status": "available", "reason": None,
            "source_frame_index": speech_pose_by_candidate.get(donor_index),
            "landmark_checked": donor_mode == "speech-pose-bank",
            "closed_mouth_metric": closed_metric,
        }

    def build_report() -> Dict[str, Any]:
        donor_count = len(donor_cache)
        coverage_status = ("none" if not corrected_frames else
                           "full" if corrected_frames == len(requests) else "partial")
        report = {
            "status": ("applied" if coverage_status == "full" else
                       "partially_applied" if coverage_status == "partial" else
                       "no_confident_mouth_donor_alignment"),
            "coverage_status": coverage_status,
            "donor_mode": donor_mode,
            "parser": "MuseTalk FaceParsing.net raw argmax; labels 11, 12, 13",
            "landmark_aperture_gate": {
                "detector": "face-alignment 68-point landmarks",
                "detector_status": landmark_detector_error or ("ready" if landmark_detector is not None else "unavailable"),
                "measurement": "maximum central inner-lip vertical gap projected perpendicular to mouth axis, divided by mouth-corner width",
                "maximum_closed_threshold": MAX_MOUTH_APERTURE_RATIO,
                "minimum_mouth_width_pixels": MIN_MOUTH_WIDTH_PIXELS,
                "unavailable_or_uncertain_policy": "fail closed; a parser-only result cannot certify a closed-mouth donor",
            },
            "mask_region": "target semantic inner-mouth and lip classes 11, 12, 13, 3x3 dilation, 5x5 Gaussian feather sigma=0.9 at native resolution",
            "mask_alignment": ("exact-pose donors use mouth-center translation only, with donor scale fixed at 1.0 so the measured closed-lip aperture is not resized; conservative face/mouth proxy gates reject displaced candidates"
                               if donor_mode == "speech-pose-bank" else
                               "face-box scale with mouth-center anchored translation; conservative face/mouth proxy gates reject visibly displaced candidates"),
            "donor_validation": (
                "only the exact ping-pong-mapped frame from the silence-conditioned MuseTalk pass is eligible; parser inner-mouth fraction must be <= {:.2f} and landmark aperture must be <= {:.3f}; no fallback donor is permitted".format(MAX_INNER_MOUTH_FRACTION, MAX_MOUTH_APERTURE_RATIO)
                if donor_mode == "silence-conditioned-exact-source" else
                "donors must be non-pause frames from this full-audio MuseTalk output with the same exact ping-pong source pose; at most {} parser-preselected candidates per source pose receive landmark closure checks; no cross-pose fallback; parser inner-mouth fraction must be <= {:.2f} and landmark aperture must be <= {:.3f}".format(MAX_SPEECH_POSE_LANDMARK_CHECKS_PER_SOURCE_POSE, MAX_INNER_MOUTH_FRACTION, MAX_MOUTH_APERTURE_RATIO)
                if donor_mode == "speech-pose-bank" else
                "source frame lies fully within verified quiet-source interval; parser inner-mouth fraction must be <= {:.2f} and landmark aperture must be <= {:.3f}".format(MAX_INNER_MOUTH_FRACTION, MAX_MOUTH_APERTURE_RATIO)
            ),
            "donor_selection_policy": (
                "Use only the exact mapped donor frame if parser fraction <= {:.2f}, landmark aperture <= {:.3f}, and face/mouth geometry gates pass; never fall back to another frame.".format(MAX_INNER_MOUTH_FRACTION, MAX_MOUTH_APERTURE_RATIO)
                if donor_mode == "silence-conditioned-exact-source" else
                "For a target, inspect only the bounded parser-ranked donor shortlist for its exact mapped base pose, then apply existing strict closure and face/mouth geometry gates; missing pose donors stay uncovered."
                if donor_mode == "speech-pose-bank" else
                "Require parser fraction <= {:.2f} and landmark aperture <= {:.3f}; rank eligible donors by lowest face/mouth geometry score, then lowest inner_mouth_fraction.".format(MAX_INNER_MOUTH_FRACTION, MAX_MOUTH_APERTURE_RATIO)
            ),
            "face_mouth_alignment_gate": {
                "maximum_normalized_face_center_delta": 0.025,
                "maximum_face_scale_delta": 0.07,
                "maximum_relative_mouth_center_delta": [0.025, 0.04],
                "maximum_relative_mouth_width_delta": 0.08,
                "transform_anchor": "mouth_bbox_center_with_face_bbox_scale",
            },
            "lip_color_policy": "Bounded per-class median Lab L/a/b match from overlapping parsed upper/lower lip pixels; inner-mouth label 11 is untouched; skip if fewer than {} total or {} per-class matching samples.".format(MIN_COLOR_MATCH_LIP_PIXELS, MIN_COLOR_MATCH_PIXELS_PER_LIP_CLASS),
            "diagnostic_scope": (
                "All eligible donors were validated and none passed the closed-mouth gates; requested output frames were not parsed because no patch could be prepared."
                if not donor_cache else
                "Per-frame records describe parser and measured-landmark donor eligibility/patch preparation; final composited frames require a separate post-FFmpeg aperture validation and passing thresholds do not guarantee universal subjective quality."
            ),
            "frame_time_basis": "timestamp_seconds is the output video frame start: output_frame_index / FPS; frame_interval_seconds gives its full 1/FPS interval.",
            "donor_video_frame_count": donor_frame_count,
            "donor_source_frame_count": donor_source_frame_count,
            "source_rendered_video": request.get("rendered_full_audio_video", str(rendered_video.resolve())),
            "donor_video": str(reference_video.resolve()),
            "planned_output_path": request.get("planned_output_path"),
            "donor_trailing_truncation_verified": trailing_truncation_verified,
            "missing_trailing_donor_frame_index": (
                donor_source_frame_count - 1 if trailing_truncation_verified else None
            ),
            "missing_trailing_frame_policy": "leave any pause mapped to the absent last source frame unchanged; do not pad, shift, interpolate, or choose another donor",
            "frame_diagnostics": [frame_diagnostics[index] for index in sorted(frame_diagnostics)],
            "requested_output_pause_frames": len(requests),
            "corrected_output_pause_frames": corrected_frames,
            "corrected_output_frame_indices": corrected_indices,
            "corrected_pause_frame_fraction": round(corrected_frames / float(len(requests)), 6),
            "uncovered_output_pause_frame_count": len(requests) - corrected_frames,
            "selected_donor_by_output_frame": selected_donor_by_output_frame,
            "quiet_source_candidate_frames": len(source_candidates) if donor_mode == "quiet-source" else 0,
            "exact_neutral_donor_candidate_frames": len(source_candidates) if donor_mode == "silence-conditioned-exact-source" else 0,
            "speech_pose_candidate_frames_tested": len(source_candidates) if donor_mode == "speech-pose-bank" else 0,
            "speech_pose_candidate_indices_by_source": ({str(index): values for index, values in sorted(speech_pose_candidates.items())} if donor_mode == "speech-pose-bank" else None),
            "speech_pose_candidate_indices_before_bounding": ({str(index): values for index, values in sorted((request.get("speech_pose_candidate_frame_indices_by_source") or {}).items(), key=lambda item: int(item[0]))} if donor_mode == "speech-pose-bank" else None),
            "speech_pose_parse_candidate_limit_per_source_pose": MAX_SPEECH_POSE_PARSE_CANDIDATES_PER_SOURCE_POSE if donor_mode == "speech-pose-bank" else None,
            "speech_pose_landmark_check_limit_per_source_pose": MAX_SPEECH_POSE_LANDMARK_CHECKS_PER_SOURCE_POSE if donor_mode == "speech-pose-bank" else None,
            "donor_frame_validation": {str(index): value for index, value in sorted(donor_validation.items())},
            "valid_closed_donor_frames": donor_count,
            "selected_donor_frame_count": sum(selected_donors.values()),
            "selected_donor_frame_counts": {str(index): count for index, count in sorted(selected_donors.items())},
            "uncorrected_output_pause_frame_indices": sorted(set(requests) - set(corrected_indices)),
            "mean_mask_pixels": round(float(np.mean(mask_areas)), 2) if mask_areas else 0.0,
            "mean_mask_fraction_of_frame": round(float(np.mean(mask_areas)) / float(width * height), 8) if mask_areas else 0.0,
            "skipped_frame_reasons": dict(sorted(reasons.items())),
            "inference_wall_seconds": round(time.perf_counter() - started, 3),
            "experimental_pose_proxy": True,
            "speech_and_nonmask_pixels_policy": (
                "leave MuseTalk content unchanged; only nonzero semantic lip alpha may use the exact mapped silence-conditioned donor frame"
                if donor_mode == "silence-conditioned-exact-source" else
                "leave the full-audio MuseTalk frame unchanged outside the semantic mouth alpha; only a validated same-pose speech frame may supply the mouth patch"
                if donor_mode == "speech-pose-bank" else
                "leave MuseTalk content unchanged; only nonzero semantic lip alpha may use a verified quiet-source donor"
            ),
            "unshifted_output_audio_policy": "map MuseTalk input audio stream 0:a:0 with stream copy; do not gate or replace output audio",
        }
        return report

    try:
        for donor_index in source_candidates:
            if _exact_source_donor_missing_reason(
                    donor_index, donor_source_frame_count, donor_frame_count,
                    trailing_truncation_verified):
                continue
            donor_frame = _read_frame(reference_capture, donor_index)
            if donor_frame is None or donor_frame.shape[:2] != (height, width):
                reasons["quiet_donor_frame_unreadable_or_wrong_size"] += 1
                continue
            try:
                labels = _raw_label_map(parser, donor_frame, torch)
                descriptor, reason = describe_face_and_mouth(labels)
            except Exception as error:
                reasons["donor_parser_error:" + type(error).__name__] += 1
                donor_validation[donor_index] = {
                    "status": "skipped", "reason": "donor_parser_error:" + type(error).__name__,
                    "closed_mouth_metric": None,
                }
                continue
            if descriptor is None:
                reasons["donor_" + reason] += 1
                donor_validation[donor_index] = {
                    "status": "skipped", "reason": "donor_" + reason,
                    "source_frame_index": speech_pose_by_candidate.get(donor_index),
                    "closed_mouth_metric": None,
                }
                continue
            if donor_mode == "speech-pose-bank":
                source_index = speech_pose_by_candidate[donor_index]
                parser_fraction = float(descriptor.get("inner_mouth_fraction", 1.0))
                donor_validation[donor_index] = {
                    "status": "parser_prefiltered",
                    "reason": None if parser_fraction <= MAX_INNER_MOUTH_FRACTION else "parser_inner_mouth_fraction_above_threshold",
                    "source_frame_index": source_index,
                    "inner_mouth_fraction": round(parser_fraction, 6),
                    "maximum_inner_mouth_fraction": MAX_INNER_MOUTH_FRACTION,
                    "landmark_checked": False,
                }
                if parser_fraction > MAX_INNER_MOUTH_FRACTION:
                    reasons["donor_parser_inner_mouth_fraction_above_threshold"] += 1
                    continue
                speech_pose_parse_cache.setdefault(source_index, []).append(
                    (donor_index, donor_frame, descriptor, labels),
                )
                continue
            validate_closed_donor(donor_index, donor_frame, descriptor, labels)

        if donor_mode == "speech-pose-bank":
            for source_index in sorted(speech_pose_candidates):
                parser_candidates = sorted(
                    speech_pose_parse_cache.get(source_index, []),
                    key=lambda item: (float(item[2].get("inner_mouth_fraction", 1.0)), item[0]),
                )
                shortlist = parser_candidates[:MAX_SPEECH_POSE_LANDMARK_CHECKS_PER_SOURCE_POSE]
                for donor_index, _, descriptor, _ in parser_candidates[len(shortlist):]:
                    donor_validation[donor_index] = {
                        "status": "skipped",
                        "reason": "speech_pose_landmark_validation_budget_exceeded",
                        "source_frame_index": source_index,
                        "inner_mouth_fraction": round(float(descriptor.get("inner_mouth_fraction", 1.0)), 6),
                        "landmark_checked": False,
                    }
                    reasons["speech_pose_landmark_validation_budget_exceeded"] += 1
                for donor_index, donor_frame, descriptor, labels in shortlist:
                    donor_validation[donor_index]["landmark_checked"] = True
                    validate_closed_donor(donor_index, donor_frame, descriptor, labels)

        if not donor_cache:
            for diagnostic in frame_diagnostics.values():
                source_index = int(diagnostic.get("exact_source_frame_index", -1))
                if donor_mode == "speech-pose-bank" and not speech_pose_candidates.get(source_index):
                    skip_reason = "no_non_pause_donor_for_exact_pingpong_pose"
                else:
                    skip_reason = "no_validated_closed_donor_frame_available"
                diagnostic["skip_reason"] = skip_reason
                reasons[skip_reason] += 1
            # Target parsing cannot produce a patch without at least one donor
            # that passed both closure checks; return the diagnostics now.
            report = build_report()
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return report

        mask_directory.mkdir(parents=True, exist_ok=False)
        donor_directory.mkdir(parents=True, exist_ok=False)

        for output_index in range(output_frame_count):
            mask = zero_mask
            if output_index in requests:
                diagnostic = frame_diagnostics[output_index]
                target_frame = _read_frame(rendered_capture, output_index)
                if target_frame is None or target_frame.shape[:2] != (height, width):
                    reasons["pause_output_frame_unreadable_or_wrong_size"] += 1
                    diagnostic["skip_reason"] = "pause_output_frame_unreadable_or_wrong_size"
                else:
                    try:
                        labels = _raw_label_map(parser, target_frame, torch)
                        target_mask, target_descriptor, reason = build_feathered_mouth_mask(labels)
                    except Exception as error:
                        target_mask, target_descriptor, reason = None, None, "parser_error:" + type(error).__name__
                    if target_mask is None or target_descriptor is None:
                        reasons["target_" + reason] += 1
                        diagnostic["skip_reason"] = "target_" + reason
                    else:
                        diagnostic["target_geometry"] = _geometry_report(target_descriptor)
                        diagnostic["mask_pixel_count"] = int(np.count_nonzero(target_mask))
                        best: Optional[Tuple[float, float, int, np.ndarray, Dict[str, Any], np.ndarray]] = None
                        alignment_rejections: Counter[str] = Counter()
                        if donor_mode == "silence-conditioned-exact-source":
                            exact_donor_index = int(requests[output_index]["donor_frame_index"])
                            diagnostic["donor_frame_index_requested"] = exact_donor_index
                            validation = donor_validation.get(exact_donor_index, {})
                            diagnostic["donor_closed_mouth_metric"] = validation.get("closed_mouth_metric")
                            exact_donor = _exact_mapped_donor(requests[output_index], donor_cache)
                            candidates = [exact_donor] if exact_donor is not None else []
                            if not candidates:
                                skip_reason = (
                                    validation.get("reason")
                                    or _exact_source_donor_missing_reason(
                                        exact_donor_index, donor_source_frame_count, donor_frame_count,
                                        trailing_truncation_verified,
                                    )
                                    or "exact_mapped_neutral_donor_unavailable"
                                )
                                reasons[skip_reason] += 1
                                diagnostic["skip_reason"] = skip_reason
                        elif donor_mode == "speech-pose-bank":
                            source_index = int(requests[output_index].get("exact_source_frame_index", -1))
                            requested_donor_indices = speech_pose_candidates.get(source_index, [])
                            diagnostic["donor_frame_indices_requested"] = list(requested_donor_indices)
                            candidates = [
                                (donor_index, *donor_cache[donor_index])
                                for donor_index in requested_donor_indices if donor_index in donor_cache
                            ]
                            if not requested_donor_indices:
                                diagnostic["skip_reason"] = "no_non_pause_donor_for_exact_pingpong_pose"
                            elif not candidates:
                                reasons["no_closed_speech_donor_for_exact_pingpong_pose"] += 1
                                diagnostic["skip_reason"] = "no_closed_speech_donor_for_exact_pingpong_pose"
                        else:
                            candidates = [
                                (donor_index, donor_frame, donor_descriptor, donor_labels)
                                for donor_index, (donor_frame, donor_descriptor, donor_labels) in donor_cache.items()
                            ]
                        for donor_index, donor_frame, donor_descriptor, donor_labels in candidates:
                            allowed, score, rejection_reason = compare_face_geometry(
                                target_descriptor, donor_descriptor, width, height,
                            )
                            if not allowed:
                                alignment_rejections[rejection_reason] += 1
                                continue
                            inner_fraction = float(donor_descriptor.get("inner_mouth_fraction", 1.0))
                            # Eligibility already enforces a closed-mouth gate;
                            # rank geometrically aligned candidates first so a
                            # very closed but visibly shifted donor cannot win.
                            candidate = (score, inner_fraction, donor_index, donor_frame, donor_descriptor, donor_labels)
                            if best is None or candidate[:3] < best[:3]:
                                best = candidate
                        if best is None:
                            reasons["no_quiet_donor_with_confident_face_alignment"] += 1
                            if diagnostic["skip_reason"] in (None, "not_processed"):
                                diagnostic["skip_reason"] = (
                                    "no_validated_closed_donor_frame_available" if not donor_cache
                                    else "no_donor_passed_face_geometry_gates"
                                )
                            diagnostic["donor_alignment_rejection_reasons"] = dict(sorted(alignment_rejections.items()))
                        else:
                            geometry_score, _, donor_index, donor_frame, donor_descriptor, donor_labels = best
                            diagnostic["selected_donor_frame_index"] = donor_index
                            diagnostic["donor_frame_index"] = donor_index
                            diagnostic["selected_donor_geometry_score"] = round(geometry_score, 6)
                            diagnostic["selected_donor_geometry"] = _geometry_report(donor_descriptor)
                            diagnostic["selected_donor_geometry_deltas"] = {
                                key: ([round(float(value), 6) for value in values]
                                      if isinstance(values, list) else round(float(values), 6))
                                for key, values in _face_mouth_geometry_deltas(
                                    target_descriptor, donor_descriptor, width, height,
                                ).items()
                            }
                            donor_inner_fraction = float(donor_descriptor.get("inner_mouth_fraction", 1.0))
                            diagnostic["selected_donor_closed_mouth_metric"] = {
                                "name": "inner_mouth_fraction",
                                "value": round(donor_inner_fraction, 6),
                                "maximum_closed_threshold": MAX_INNER_MOUTH_FRACTION,
                                "parser_passed": donor_inner_fraction <= MAX_INNER_MOUTH_FRACTION,
                                "landmark_mouth_aperture": {
                                    "name": "inner_lip_gap_over_mouth_width",
                                    "value": round(float(donor_descriptor["mouth_aperture_ratio"]), 6),
                                    "mouth_width_pixels": round(float(donor_descriptor["mouth_width_pixels_landmarked"]), 3),
                                    "maximum_closed_threshold": MAX_MOUTH_APERTURE_RATIO,
                                    "status": "measured",
                                    "passed": float(donor_descriptor["mouth_aperture_ratio"]) <= MAX_MOUTH_APERTURE_RATIO,
                                },
                                "passed": is_closed_donor(donor_descriptor),
                            }
                            diagnostic["selected_donor_mouth_aperture_metric"] = diagnostic["selected_donor_closed_mouth_metric"]["landmark_mouth_aperture"]
                            donor_mouth_bbox = donor_descriptor["mouth_bbox"]
                            target_mouth_bbox = target_descriptor["mouth_bbox"]
                            alignment_args = (
                                donor_descriptor["face_bbox"], target_descriptor["face_bbox"],
                                donor_mouth_bbox, target_mouth_bbox,
                            )
                            aligned_donor = _warp_donor_to_target(
                                donor_frame, *alignment_args,
                                preserve_donor_scale=donor_mode == "speech-pose-bank",
                            )
                            aligned_donor_labels = _warp_donor_to_target(
                                donor_labels, *alignment_args, interpolation=cv2.INTER_NEAREST,
                                preserve_donor_scale=donor_mode == "speech-pose-bank",
                            )
                            aligned_donor, color_adjustment = _match_donor_lip_color(
                                aligned_donor, target_frame, target_mask, labels, aligned_donor_labels,
                            )
                            diagnostic["lip_color_adjustment"] = color_adjustment
                            if color_adjustment["status"] != "applied":
                                reasons["donor_target_lip_color_unverified"] += 1
                                diagnostic["skip_reason"] = "donor_target_lip_color_unverified"
                            else:
                                # Composite donor pixels only through a parser-derived
                                # alpha mask around the target's current lip classes.
                                # maskedmerge consumes an all-zero frame for every
                                # non-corrected timestamp, leaving those frames untouched.
                                mask = target_mask
                                target_frame_path = mask_directory / ("{:08d}.png".format(output_index))
                                if not cv2.imwrite(str(target_frame_path), mask):
                                    raise RuntimeError("Could not write semantic lip alpha for output frame {}.".format(output_index))
                                # Use an output-timed donor sequence because the best
                                # closed source frame can differ at each pause timestamp.
                                donor_path = donor_directory / ("{:08d}.png".format(output_index))
                                if not cv2.imwrite(str(donor_path), aligned_donor):
                                    reasons["donor_patch_write_failed"] += 1
                                    mask = zero_mask
                                    diagnostic["skip_reason"] = "donor_patch_write_failed"
                                    if not cv2.imwrite(str(target_frame_path), zero_mask):
                                        raise RuntimeError("Could not write zero lip alpha after donor failure.")
                                else:
                                    corrected_frames += 1
                                    corrected_indices.append(output_index)
                                    selected_donors[donor_index] += 1
                                    selected_donor_by_output_frame[str(output_index)] = donor_index
                                    mask_areas.append(int(np.count_nonzero(mask)))
                                    diagnostic["patch_prepared"] = True
                                    diagnostic["status"] = "patch_prepared"
                                    diagnostic["skip_reason"] = None
                                    diagnostic["alpha_written_pixel_count"] = int(np.count_nonzero(mask))
            if output_index not in requests or not np.any(mask):
                mask = zero_mask
                path = mask_directory / ("{:08d}.png".format(output_index))
                if not path.exists():
                    if not cv2.imwrite(str(path), mask):
                        raise RuntimeError("Could not write zero lip alpha for output frame {}.".format(output_index))
                donor_path = donor_directory / ("{:08d}.png".format(output_index))
                if not donor_path.exists():
                    if not cv2.imwrite(str(donor_path), zero_donor):
                        raise RuntimeError("Could not write zero donor frame {}.".format(output_index))
    finally:
        rendered_capture.release()
        reference_capture.release()

    report = build_report()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def validate_output_pause_frames(
    video_path: Path,
    frame_indices: Sequence[int],
    landmark_detector: Any,
    max_aperture_ratio: float = MAX_MOUTH_APERTURE_RATIO,
) -> Dict[str, Any]:
    """Measure the final encoded pause frames; every requested frame must pass."""
    _require_image_dependencies()
    indices = sorted(set(int(index) for index in frame_indices))
    if not indices:
        return {
            "status": "not_applicable", "method": "face-alignment 68-point inner-lip aperture",
            "requested_frame_count": 0, "passed_frame_count": 0, "failed_frame_indices": [],
            "frame_measurements": [],
        }
    if landmark_detector is None:
        return {
            "status": "failed", "reason": "landmark_detector_unavailable",
            "method": "face-alignment 68-point inner-lip aperture",
            "requested_frame_count": len(indices), "passed_frame_count": 0,
            "failed_frame_indices": indices, "frame_measurements": [],
        }
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("Could not open the final pause-corrected video for mouth-aperture validation.")
    measurements: List[Dict[str, Any]] = []
    try:
        for frame_index in indices:
            frame = _read_frame(capture, frame_index)
            if frame is None:
                measurements.append({
                    "frame_index": frame_index, "status": "failed", "reason": "frame_unreadable",
                    "aperture_ratio": None, "mouth_width_pixels": None, "passed": False,
                })
                continue
            aperture, reason, mouth_width = detect_mouth_aperture(landmark_detector, frame)
            passed = aperture is not None and aperture <= max_aperture_ratio
            measurements.append({
                "frame_index": frame_index,
                "status": "measured" if aperture is not None else "failed",
                "reason": None if aperture is not None else reason,
                "aperture_ratio": round(aperture, 6) if aperture is not None else None,
                "mouth_width_pixels": round(mouth_width, 3) if mouth_width is not None else None,
                "maximum_closed_threshold": max_aperture_ratio,
                "passed": passed,
            })
    finally:
        capture.release()
    failed = [item["frame_index"] for item in measurements if not item["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "method": "face-alignment 68-point inner-lip aperture normalized by mouth-corner width on final encoded frame",
        "maximum_closed_threshold": max_aperture_ratio,
        "requested_frame_count": len(indices),
        "passed_frame_count": len(indices) - len(failed),
        "failed_frame_indices": failed,
        "frame_measurements": measurements,
        "quality_scope": "A pass means each measured pause frame is under the aperture threshold; it is a geometric QC gate, not a guarantee of subjective naturalness across every character, pose, codec, or language.",
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendered-video", type=Path)
    parser.add_argument("--reference-video", type=Path)
    parser.add_argument("--mask-directory", type=Path)
    parser.add_argument("--donor-directory", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--validate-output-video", type=Path)
    parser.add_argument("--validate-request", type=Path)
    parser.add_argument("--validation-report", type=Path)
    parser.add_argument("--check-landmark-detector", action="store_true",
                        help="Initialize the 68-point detector and exit; use before expensive inference.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        import torch
        landmark_detector, detector_error = _face_alignment_detector(torch)
        if args.check_landmark_detector:
            report = {
                "status": "ready" if landmark_detector is not None and detector_error is None else "failed",
                "detector": "face-alignment 68-point landmarks",
                "initialization_error": detector_error,
                "quality_scope": "Dependency/model initialization only; no image or video quality is certified.",
            }
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report["status"] == "ready" else 2
        if args.validate_output_video is not None:
            if args.validate_request is None or args.validation_report is None:
                raise ValueError("Final-output validation requires --validate-request and --validation-report.")
            request = json.loads(args.validate_request.read_text(encoding="utf-8"))
            indices = [int(item["output_frame_index"]) for item in request.get("output_pause_frames", [])]
            report = validate_output_pause_frames(
                args.validate_output_video.resolve(), indices, landmark_detector,
            )
            if detector_error:
                report["detector_initialization_error"] = detector_error
            args.validation_report.parent.mkdir(parents=True, exist_ok=True)
            args.validation_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report["status"] in ("passed", "not_applicable") else 2
        required = (args.rendered_video, args.reference_video, args.mask_directory,
                    args.donor_directory, args.report, args.request)
        if any(value is None for value in required):
            raise ValueError("Extraction mode requires --rendered-video, --reference-video, --mask-directory, --donor-directory, --report, and --request.")
        from musetalk.utils.face_parsing import FaceParsing

        parser = FaceParsing()
        report = run_extraction(
            args.rendered_video.resolve(), args.reference_video.resolve(),
            args.mask_directory.resolve(), args.donor_directory.resolve(),
            args.report.resolve(), args.request.resolve(),
            parser, torch, landmark_detector, detector_error,
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception as error:
        print("Mouth mask extraction failed safely: {}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
