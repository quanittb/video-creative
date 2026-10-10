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
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    import cv2
    import numpy as np
except ImportError:  # Allows non-MuseTalk workflows and syntax tests to import this module.
    cv2 = None
    np = None


MOUTH_LABELS = (11, 12, 13)
INNER_MOUTH_LABEL = 11
MUSE_TALK_PARSE_SIZE = (512, 512)
MAX_INNER_MOUTH_FRACTION = 0.30


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
    """Reject source-silent frames whose parsed mouth still looks open."""
    return float(descriptor.get("inner_mouth_fraction", 1.0)) <= MAX_INNER_MOUTH_FRACTION


def compare_face_geometry(
    target: Mapping[str, Any], donor: Mapping[str, Any], width: int, height: int,
) -> Tuple[bool, float, str]:
    """Conservative normalized face-box/mouth-shape proxy for donor alignment."""
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
    if center_delta[0] > 0.045 or center_delta[1] > 0.045:
        return False, float("inf"), "face_center_mismatch"
    if scale_delta[0] > 0.12 or scale_delta[1] > 0.12:
        return False, float("inf"), "face_scale_mismatch"
    if mouth_delta[0] > 0.07 or mouth_delta[1] > 0.10 or mouth_width_delta > 0.18:
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
    )
    return {key: descriptor[key] for key in keys if key in descriptor}


def _warp_donor_to_target(
    donor_frame: np.ndarray, donor_bbox: Sequence[int], target_bbox: Sequence[int],
) -> np.ndarray:
    _require_image_dependencies()
    dh, dw = donor_frame.shape[:2]
    tx0, ty0, tx1, ty1 = [float(value) for value in target_bbox]
    dx0, dy0, dx1, dy1 = [float(value) for value in donor_bbox]
    sx, sy = (tx1 - tx0) / (dx1 - dx0), (ty1 - ty0) / (dy1 - dy0)
    matrix = np.asarray([[sx, 0.0, tx0 - sx * dx0], [0.0, sy, ty0 - sy * dy0]], dtype=np.float32)
    return cv2.warpAffine(donor_frame, matrix, (dw, dh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def run_extraction(
    rendered_video: Path,
    reference_video: Path,
    mask_directory: Path,
    donor_directory: Path,
    report_path: Path,
    request_path: Path,
    parser: Any,
    torch: Any,
) -> Dict[str, Any]:
    _require_image_dependencies()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    fps = int(request["fps"])
    width, height = int(request["width"]), int(request["height"])
    output_frame_count = int(request["output_frame_count"])
    source_candidates = [int(index) for index in request["quiet_source_frame_indices"]]
    requests = {int(item["output_frame_index"]): item for item in request["output_pause_frames"]}
    if fps < 1 or width < 1 or height < 1 or output_frame_count < 1:
        raise ValueError("Invalid frame geometry in mouth-mask request.")
    if not requests:
        raise ValueError("No output pause frames were supplied for mouth correction.")
    if not source_candidates:
        raise ValueError("No verified quiet-source donor frames were supplied.")
    if any(index < 0 or index >= output_frame_count for index in requests):
        raise ValueError("Pause-frame index is outside the requested output timeline.")

    rendered_capture = cv2.VideoCapture(str(rendered_video))
    reference_capture = cv2.VideoCapture(str(reference_video))
    if not rendered_capture.isOpened() or not reference_capture.isOpened():
        raise RuntimeError("Could not open rendered or quiet-source video for mask extraction.")
    donor_cache: Dict[int, Tuple[np.ndarray, Dict[str, Any]]] = {}
    reasons: Counter[str] = Counter()
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
            "patch_prepared": False,
            "status": "skipped",
            "skip_reason": "not_processed",
            "target_geometry": None,
            "mask_pixel_count": 0,
            "alpha_written_pixel_count": 0,
            "donor_alignment_rejection_reasons": {},
            "selected_donor_frame_index": None,
            "selected_donor_closed_mouth_metric": None,
            "selected_donor_geometry_score": None,
        }
        for output_index, item in requests.items()
    }
    corrected_frames = 0
    started = time.perf_counter()
    mask_directory.mkdir(parents=True, exist_ok=False)
    donor_directory.mkdir(parents=True, exist_ok=False)
    zero_mask = np.zeros((height, width), dtype=np.uint8)
    zero_donor = np.zeros((height, width, 3), dtype=np.uint8)
    try:
        for donor_index in source_candidates:
            donor_frame = _read_frame(reference_capture, donor_index)
            if donor_frame is None or donor_frame.shape[:2] != (height, width):
                reasons["quiet_donor_frame_unreadable_or_wrong_size"] += 1
                continue
            try:
                labels = _raw_label_map(parser, donor_frame, torch)
                descriptor, reason = describe_face_and_mouth(labels)
            except Exception as error:
                reasons["donor_parser_error:" + type(error).__name__] += 1
                continue
            if descriptor is None:
                reasons["donor_" + reason] += 1
                continue
            if not is_closed_donor(descriptor):
                reasons["quiet_donor_mouth_not_closed"] += 1
                continue
            donor_cache[donor_index] = (donor_frame, descriptor)

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
                        best: Optional[Tuple[float, float, int, np.ndarray, Dict[str, Any]]] = None
                        alignment_rejections: Counter[str] = Counter()
                        for donor_index, (donor_frame, donor_descriptor) in donor_cache.items():
                            allowed, score, rejection_reason = compare_face_geometry(
                                target_descriptor, donor_descriptor, width, height,
                            )
                            if not allowed:
                                alignment_rejections[rejection_reason] += 1
                                continue
                            inner_fraction = float(donor_descriptor.get("inner_mouth_fraction", 1.0))
                            candidate = (inner_fraction, score, donor_index, donor_frame, donor_descriptor)
                            if best is None or candidate[:3] < best[:3]:
                                best = candidate
                        if best is None:
                            reasons["no_quiet_donor_with_confident_face_alignment"] += 1
                            diagnostic["skip_reason"] = (
                                "no_validated_closed_donor_frame_available" if not donor_cache
                                else "no_donor_passed_face_geometry_gates"
                            )
                            diagnostic["donor_alignment_rejection_reasons"] = dict(sorted(alignment_rejections.items()))
                        else:
                            _, geometry_score, donor_index, donor_frame, donor_descriptor = best
                            diagnostic["selected_donor_frame_index"] = donor_index
                            diagnostic["selected_donor_geometry_score"] = round(geometry_score, 6)
                            donor_inner_fraction = float(donor_descriptor.get("inner_mouth_fraction", 1.0))
                            diagnostic["selected_donor_closed_mouth_metric"] = {
                                "name": "inner_mouth_fraction",
                                "value": round(donor_inner_fraction, 6),
                                "maximum_closed_threshold": MAX_INNER_MOUTH_FRACTION,
                                "passed": is_closed_donor(donor_descriptor),
                            }
                            aligned_donor = _warp_donor_to_target(
                                donor_frame, donor_descriptor["face_bbox"], target_descriptor["face_bbox"],
                            )
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

    donor_count = len(donor_cache)
    coverage_status = ("none" if not corrected_frames else
                       "full" if corrected_frames == len(requests) else "partial")
    report = {
        "status": ("applied" if coverage_status == "full" else
                   "partially_applied" if coverage_status == "partial" else
                   "no_confident_mouth_donor_alignment"),
        "coverage_status": coverage_status,
        "parser": "MuseTalk FaceParsing.net raw argmax; labels 11, 12, 13; no extra model",
        "mask_region": "semantic lip classes, 3x3 dilation, 5x5 Gaussian feather sigma=0.9 at native resolution",
        "mask_alignment": "normalized face-box scale/translation plus mouth-center/width proxy; rejected above conservative thresholds",
        "donor_validation": "source frame lies fully within verified quiet-source interval and inner-mouth label 11 is <= {:.2f} of parsed lip mask".format(MAX_INNER_MOUTH_FRACTION),
        "donor_selection_policy": "Keep the existing closed-mouth and face-geometry gates; rank geometry-valid quiet donors by lowest inner_mouth_fraction, then lowest normalized face-geometry score.",
        "diagnostic_scope": "Per-frame records describe parser/donor patch preparation only; they do not visually validate that the output mouth appears closed or natural.",
        "frame_time_basis": "timestamp_seconds is the output video frame start: output_frame_index / FPS; frame_interval_seconds gives its full 1/FPS interval.",
        "frame_diagnostics": [frame_diagnostics[index] for index in sorted(frame_diagnostics)],
        "requested_output_pause_frames": len(requests),
        "corrected_output_pause_frames": corrected_frames,
        "corrected_output_frame_indices": corrected_indices,
        "corrected_pause_frame_fraction": round(corrected_frames / float(len(requests)), 6),
        "uncovered_output_pause_frame_count": len(requests) - corrected_frames,
        "selected_donor_by_output_frame": selected_donor_by_output_frame,
        "quiet_source_candidate_frames": len(source_candidates),
        "valid_closed_donor_frames": donor_count,
        "selected_donor_frame_count": sum(selected_donors.values()),
        "selected_donor_frame_counts": {str(index): count for index, count in sorted(selected_donors.items())},
        "uncorrected_output_pause_frame_indices": sorted(set(requests) - set(corrected_indices)),
        "mean_mask_pixels": round(float(np.mean(mask_areas)), 2) if mask_areas else 0.0,
        "mean_mask_fraction_of_frame": round(float(np.mean(mask_areas)) / float(width * height), 8) if mask_areas else 0.0,
        "skipped_frame_reasons": dict(sorted(reasons.items())),
        "inference_wall_seconds": round(time.perf_counter() - started, 3),
        "experimental_pose_proxy": True,
        "speech_and_nonmask_pixels_policy": "leave MuseTalk content unchanged; only nonzero semantic lip alpha may use a verified quiet-source donor",
        "unshifted_output_audio_policy": "map MuseTalk input audio stream 0:a:0 with stream copy; do not gate or replace output audio",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendered-video", required=True, type=Path)
    parser.add_argument("--reference-video", required=True, type=Path)
    parser.add_argument("--mask-directory", required=True, type=Path)
    parser.add_argument("--donor-directory", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        import torch
        from musetalk.utils.face_parsing import FaceParsing

        parser = FaceParsing()
        report = run_extraction(
            args.rendered_video.resolve(), args.reference_video.resolve(),
            args.mask_directory.resolve(), args.donor_directory.resolve(),
            args.report.resolve(), args.request.resolve(),
            parser, torch,
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception as error:
        print("Mouth mask extraction failed safely: {}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
