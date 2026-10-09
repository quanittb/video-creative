# coding: utf-8
"""Conservative torso coupling based on measured LivePortrait head translation.

The schedule generator below remains for API compatibility; the video path does not
use its synthetic head, breathing, or shoulder trajectories.
"""

import math
import os
import shutil
import subprocess
import tempfile
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Sequence


def smooth_1d(arr: np.ndarray, window_size: int = 7) -> np.ndarray:
    if len(arr) < window_size:
        return arr
    pad = window_size // 2
    padded = np.pad(arr, pad, mode="edge")
    kernel = np.ones(window_size) / window_size
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[:len(arr)]


def generate_conversational_motion_schedule(n_frames: int, fps: float = 24.0, h: int = 1280, w: int = 1024) -> Dict[str, np.ndarray]:
    """
    Generates non-repetitive, organic conversational trajectories.
    All displacement values are scaled appropriately for the image resolution.
    """
    total_time = n_frames / fps

    # Target amplitudes for visible, authentic human motion (relative to 1280p)
    scale_y = h / 1280.0
    scale_x = w / 1024.0

    head_dx = np.zeros(n_frames, dtype=np.float32)
    head_dy = np.zeros(n_frames, dtype=np.float32)
    head_roll_deg = np.zeros(n_frames, dtype=np.float32)
    sh_left_dy = np.zeros(n_frames, dtype=np.float32)
    sh_right_dy = np.zeros(n_frames, dtype=np.float32)
    torso_sway_dx = np.zeros(n_frames, dtype=np.float32)

    # 1. Background breathing cycle (calm 3.8s period, ~6-9px heave)
    t_arr = np.arange(n_frames) / fps
    breath_heave = 7.5 * np.sin(2.0 * np.pi * t_arr / 3.8) * scale_y
    sh_left_dy += breath_heave
    sh_right_dy += breath_heave * 0.92  # subtle left/right asymmetry in natural breathing

    # 2. Conversational gesture schedule
    # Format: (start_time, duration, target_dx, target_dy, target_roll, sh_L, sh_R)
    rng = np.random.RandomState(1337)
    curr_t = 0.60
    events = []

    last_yaw = 0.0

    while curr_t < total_time - 0.5:
        dur = float(rng.uniform(0.40, 0.75))
        # Emphatic pitch nod on stressed points: 9 to 18px downward
        dy = float(rng.uniform(9.0, 18.0)) * scale_y

        # Asymmetric yaw shift: speaker turns slightly (-18px to +18px), never bouncing back to exact zero
        # Pick a target yaw that differs from last posture
        if abs(last_yaw) > 10.0:
            # Settle back towards center or mild opposite side
            target_yaw = float(rng.uniform(-6.0, 6.0)) * scale_x
        else:
            side = rng.choice([-1.0, 1.0])
            target_yaw = float(side * rng.uniform(10.0, 22.0)) * scale_x
        dx = target_yaw - last_yaw
        last_yaw = target_yaw

        # Micro roll (leaning head slightly, 0.8 to 1.6 degrees)
        d_roll = float(rng.uniform(-1.4, 1.4))

        # Asymmetric shoulders:
        # Turning head right -> left shoulder forward/up, right shoulder relaxed
        # Turning head left -> right shoulder forward/up, left shoulder relaxed
        yaw_dir = np.sign(dx) if abs(dx) > 2.0 else rng.choice([-1.0, 1.0])
        if yaw_dir > 0:
            sL = float(rng.uniform(12.0, 20.0)) * scale_y
            sR = float(rng.uniform(-4.0, 4.0)) * scale_y
        else:
            sL = float(rng.uniform(-4.0, 4.0)) * scale_y
            sR = float(rng.uniform(12.0, 20.0)) * scale_y

        events.append((curr_t, dur, dx, dy, d_roll, sL, sR))

        # Stillness plateau: authentic conversation has 1.0s to 2.2s of calm attentive gaze
        gap = float(rng.uniform(1.1, 2.2))
        curr_t += dur + gap

    # Synthesize smooth minimum-jerk curves
    for (t0, dur, dx, dy, d_roll, sL, sR) in events:
        idx0 = int(t0 * fps)
        n_ev = int(dur * fps)
        for i in range(n_ev):
            k = idx0 + i
            if k >= n_frames:
                break
            s = i / float(max(n_ev - 1, 1))
            # Smooth bell curve for nod & roll: sin^1.5(pi * s)
            bell = math.pow(math.sin(math.pi * s), 1.5)
            head_dy[k] += dy * bell
            head_roll_deg[k] += d_roll * bell

            # S-curve step for yaw posture transition (smoothstep)
            step = s * s * (3.0 - 2.0 * s)
            head_dx[k:] += (dx / max(n_ev, 1)) * (1.0 - s * 0.4)

        # Shoulder reaction: 4-frame delay + slower settling time
        sh_lag = 4
        n_sh = int((dur + 0.35) * fps)
        for i in range(n_sh):
            k = idx0 + sh_lag + i
            if k >= n_frames:
                break
            s = i / float(max(n_sh - 1, 1))
            pulse = math.sin(math.pi * s) * math.exp(-1.5 * s)
            sh_left_dy[k] += sL * pulse
            sh_right_dy[k] += sR * pulse

    # Smooth all trajectories to guarantee zero-jitter fluid motion
    head_dx = smooth_1d(head_dx, 9)
    head_dy = smooth_1d(head_dy, 9)
    head_roll_deg = smooth_1d(head_roll_deg, 9)
    sh_left_dy = smooth_1d(sh_left_dy, 9)
    sh_right_dy = smooth_1d(sh_right_dy, 9)

    return {
        "head_dx": head_dx,
        "head_dy": head_dy,
        "head_roll_deg": head_roll_deg,
        "sh_left_dy": sh_left_dy,
        "sh_right_dy": sh_right_dy,
    }


def _apply_masked_body_warp(
    frame: np.ndarray,
    body_mask: np.ndarray,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    left_weight: np.ndarray,
    right_weight: np.ndarray,
    left_dy: float,
    right_dy: float,
) -> np.ndarray:
    """Warp only mask-supported torso pixels; every zero-mask pixel stays unchanged."""
    import cv2

    displacement_y = left_dy * left_weight + right_dy * right_weight
    map_x = grid_x
    map_y = (grid_y - displacement_y).astype(np.float32)
    warped = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    alpha_mask = body_mask[:, :, np.newaxis]
    blended = warped.astype(np.float32) * alpha_mask + frame.astype(np.float32) * (1.0 - alpha_mask)
    output = np.rint(np.clip(blended, 0, 255)).astype(np.uint8)
    output[body_mask <= 0.0] = frame[body_mask <= 0.0]
    return output


def _prepare_body_motion_mask(mask_image: np.ndarray, face_roi: Sequence[int]) -> np.ndarray:
    """Validate and feather a binary body mask inward, keeping unsupported pixels fixed."""
    import cv2

    h, w = mask_image.shape[:2]
    x, y, roi_w, roi_h = (int(v) for v in face_roi)
    if x < 0 or y < 0 or roi_w < 16 or roi_h < 16 or x + roi_w > w or y + roi_h > h:
        raise ValueError(f"Face ROI {tuple(face_roi)} nằm ngoài video {w}x{h}.")
    binary_mask = (mask_image >= 128).astype(np.uint8)
    roi_region = binary_mask[y:y + roi_h, x:x + roi_w]
    if float(roi_region.mean()) > 0.005:
        raise ValueError("Body mask chồng lên face ROI; hãy sửa mask để chỉ giữ áo/vai/thân.")
    coverage = float(binary_mask.mean())
    if coverage < 0.005 or coverage > 0.45:
        raise ValueError(f"Body mask có độ phủ {coverage:.1%}; cần mask thân người chặt, trong khoảng 0.5%-45%.")

    # Distance transform feathers inward without touching background pixels.
    feather_px = max(2.0, min(w, h) * 0.008)
    inside_distance = cv2.distanceTransform(binary_mask, cv2.DIST_L2, 5)
    body_mask = np.clip(inside_distance / feather_px, 0.0, 1.0).astype(np.float32)
    body_mask *= binary_mask

    margin_x = max(8, int(roi_w * 0.08))
    margin_y = max(8, int(roi_h * 0.08))
    protect_x0, protect_x1 = max(0, x - margin_x), min(w, x + roi_w + margin_x)
    protect_y0, protect_y1 = max(0, y - margin_y), min(h, y + roi_h + margin_y)
    body_mask[protect_y0:protect_y1, protect_x0:protect_x1] = 0.0

    # Anchor the bottom edge gradually over the final 8% of the frame.
    anchor_y = int(h * 0.92)
    anchor = np.clip((h - 1 - np.arange(anchor_y, h, dtype=np.float32)) / max(h - anchor_y, 1), 0.0, 1.0)
    body_mask[anchor_y:, :] *= anchor[:, np.newaxis]
    return body_mask


def _prepare_body_silhouette_mask(mask_image: np.ndarray, face_roi: Sequence[int]) -> np.ndarray:
    """Keep a calibrated foreground silhouette for edge motion, with a fixed face zone."""
    h, w = mask_image.shape[:2]
    x, y, roi_w, roi_h = (int(v) for v in face_roi)
    if x < 0 or y < 0 or roi_w < 16 or roi_h < 16 or x + roi_w > w or y + roi_h > h:
        raise ValueError(f"Face ROI {tuple(face_roi)} nằm ngoài video {w}x{h}.")
    binary_mask = (mask_image >= 128).astype(np.uint8)
    if float(binary_mask[y:y + roi_h, x:x + roi_w].mean()) > 0.005:
        raise ValueError("Body mask chồng lên face ROI; hãy sửa mask để chỉ giữ áo/vai/thân.")
    coverage = float(binary_mask.mean())
    if coverage < 0.005 or coverage > 0.45:
        raise ValueError(f"Body mask có độ phủ {coverage:.1%}; cần mask thân người chặt, trong khoảng 0.5%-45%.")

    margin_x = max(8, int(roi_w * 0.08))
    margin_y = max(8, int(roi_h * 0.08))
    protect_x0, protect_x1 = max(0, x - margin_x), min(w, x + roi_w + margin_x)
    protect_y0, protect_y1 = max(0, y - margin_y), min(h, y + roi_h + margin_y)
    binary_mask[protect_y0:protect_y1, protect_x0:protect_x1] = 0
    return binary_mask.astype(np.float32)


def _apply_silhouette_body_warp(
    frame: np.ndarray,
    body_alpha: np.ndarray,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    left_weight: np.ndarray,
    right_weight: np.ndarray,
    left_dy: float,
    right_dy: float,
    max_displacement_px: float,
    onset_y: float,
    onset_height: float = 32.0,
    protected_region: Optional[Sequence[int]] = None,
    background_plate: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Move foreground and alpha together, patching only the newly vacated edge band."""
    import cv2

    if abs(left_dy) < 1e-4 and abs(right_dy) < 1e-4:
        return frame.copy()

    height, width = frame.shape[:2]
    row = np.arange(height, dtype=np.float32)[:, None]
    onset = np.clip((row - onset_y) / max(onset_height, 1.0), 0.0, 1.0)
    displacement_y = left_dy * left_weight + right_dy * right_weight
    anchor_y = int(height * 0.92)
    anchor = np.ones(height, dtype=np.float32)
    anchor[anchor_y:] = np.clip(
        (height - 1 - np.arange(anchor_y, height, dtype=np.float32)) / max(height - anchor_y, 1),
        0.0,
        1.0,
    )
    displacement_y = np.clip(displacement_y * onset * anchor[:, None], -max_displacement_px, max_displacement_px)
    map_y = (grid_y - displacement_y).astype(np.float32)

    alpha = np.clip(body_alpha, 0.0, 1.0).astype(np.float32)
    warped_alpha = cv2.remap(
        alpha, grid_x, map_y, cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0.0,
    )
    premultiplied = frame.astype(np.float32) * alpha[:, :, None]
    warped_premultiplied = cv2.remap(
        premultiplied, grid_x, map_y, cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0.0,
    )
    foreground = np.zeros_like(warped_premultiplied)
    np.divide(
        warped_premultiplied,
        np.maximum(warped_alpha[:, :, None], 1e-6),
        out=foreground,
        where=warped_alpha[:, :, None] > 1e-6,
    )

    # Use a one-time plate that treats the complete foreground as unknown. Limit
    # its visible contribution to the narrow strip vacated by this frame's warp.
    binary_alpha = (alpha >= 0.5).astype(np.uint8)
    edge_distance = cv2.distanceTransform(binary_alpha, cv2.DIST_L2, 3)
    edge_band = (binary_alpha > 0) & (edge_distance <= math.ceil(max_displacement_px) + 3)
    vacated = ((alpha - warped_alpha) > 1e-6) & edge_band
    background = frame.copy()
    if background_plate is not None and np.any(vacated):
        background[vacated] = background_plate[vacated]

    output = np.rint(
        foreground * warped_alpha[:, :, None]
        + background.astype(np.float32) * (1.0 - warped_alpha[:, :, None])
    )
    output = np.clip(output, 0, 255).astype(np.uint8)
    if protected_region is not None:
        x0, y0, x1, y1 = (int(value) for value in protected_region)
        output[y0:y1, x0:x1] = frame[y0:y1, x0:x1]
    return output


def apply_conversational_motion_to_video(
    in_video: str,
    out_video: str,
    audio_path: Optional[str] = None,
    mode: str = "off",
    body_mask_path: Optional[str] = None,
    face_roi: Optional[Sequence[int]] = None,
    max_displacement_px: float = 2.5,
    head_motion_lag_seconds: float = 0.14,
    coupling_strength: float = 0.25,
    body_render_mode: str = "interior",
) -> bool:
    """Couple a small torso response to measured head motion, never generate head motion.

    The default is an exact file copy. Coupled mode requires a calibrated white-on-black
    body mask and face ROI; it rejects missing or unsafe calibration data.
    """
    in_path = Path(in_video).resolve()
    out_path = Path(out_video).resolve()
    if not in_path.is_file():
        print(f"[Motion] Không tìm thấy video đầu vào: {in_path}")
        return False
    if mode == "off":
        if in_path != out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(in_path, out_path)
        return True
    if mode != "coupled":
        print("[Motion] mode chỉ nhận 'off' hoặc 'coupled'.")
        return False
    if body_render_mode not in ("interior", "silhouette"):
        print("[Motion] body_render_mode chỉ nhận 'interior' hoặc 'silhouette'.")
        return False
    if not body_mask_path or face_roi is None:
        print("[Motion] Chế độ coupled cần --body-mask và --face-roi đã hiệu chuẩn theo video đầu vào.")
        return False
    if len(face_roi) != 4 or max_displacement_px <= 0 or head_motion_lag_seconds <= 0 or coupling_strength <= 0:
        print("[Motion] ROI cần dạng x,y,w,h; giới hạn dịch chuyển, độ trễ và coupling phải lớn hơn 0.")
        return False
    if audio_path and not Path(audio_path).is_file():
        print(f"[Motion] Không tìm thấy audio: {Path(audio_path).resolve()}")
        return False

    import cv2

    cap = cv2.VideoCapture(str(in_path))
    if not cap.isOpened():
        print(f"[Motion] Không mở được video: {in_path}")
        return False
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        print(f"[Motion] Video không có frame: {in_path}")
        return False
    h, w = first_frame.shape[:2]
    x, y, roi_w, roi_h = (int(v) for v in face_roi)
    if x < 0 or y < 0 or roi_w < 16 or roi_h < 16 or x + roi_w > w or y + roi_h > h:
        cap.release()
        print(f"[Motion] Face ROI {tuple(face_roi)} nằm ngoài video {w}x{h}.")
        return False

    mask_path = Path(body_mask_path).resolve()
    mask_image = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask_image is None:
        cap.release()
        print(f"[Motion] Không đọc được body mask: {mask_path}")
        return False
    if mask_image.shape != (h, w):
        cap.release()
        print(f"[Motion] Kích thước mask {mask_image.shape[1]}x{mask_image.shape[0]} khác video {w}x{h}.")
        return False

    try:
        body_mask = (
            _prepare_body_silhouette_mask(mask_image, face_roi)
            if body_render_mode == "silhouette"
            else _prepare_body_motion_mask(mask_image, face_roi)
        )
    except ValueError as exc:
        cap.release()
        print(f"[Motion] {exc}")
        return False

    background_plate = None
    if body_render_mode == "silhouette":
        # Generate once from the first frame while excluding the complete body matte.
        background_plate = cv2.inpaint(
            first_frame,
            (body_mask >= 0.5).astype(np.uint8) * 255,
            max(3, int(math.ceil(max_displacement_px)) + 3),
            cv2.INPAINT_TELEA,
        )

    # Track stable upper-face features only; lower-face and mouth motion are excluded.
    tracking_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    tracking_mask[:max(1, int(roi_h * 0.68)), :] = 255
    first_gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    first_roi = first_gray[y:y + roi_h, x:x + roi_w]
    points = cv2.goodFeaturesToTrack(
        first_roi,
        maxCorners=120,
        qualityLevel=0.01,
        minDistance=4,
        mask=tracking_mask,
        blockSize=7,
    )
    if points is None or len(points) < 6:
        cap.release()
        print("[Motion] Không đủ feature ở vùng trán/mắt; kiểm tra --face-roi hoặc dùng motion-mode off.")
        return False
    points[:, 0, 0] += x
    points[:, 0, 1] += y

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        cap.release()
        print("[Motion] Không tìm thấy ffmpeg trong PATH.")
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_name = tempfile.mkstemp(prefix=f"_{out_path.stem}_motion_", suffix=".mp4", dir=str(out_path.parent))
    os.close(fd)
    temp_raw = Path(raw_name)
    temp_raw.unlink(missing_ok=True)
    target_stage = None
    ffmpeg_cmd = [
        ffmpeg, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "bgr24", "-r", f"{fps:.6f}", "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
        str(temp_raw),
    ]
    proc = None
    prev_gray = first_gray
    head_pos_x = 0.0
    head_pos_y = 0.0
    shoulder_left = 0.0
    shoulder_right = 0.0
    slow_head_pos_x = 0.0
    slow_head_pos_y = 0.0
    alpha = 1.0 - math.exp(-1.0 / max(fps * head_motion_lag_seconds, 1e-6))
    slow_alpha = 1.0 - math.exp(-1.0 / max(fps * 0.9, 1e-6))
    max_px = max_displacement_px * h / 1280.0
    center_x = x + roi_w * 0.5
    grid_y, grid_x = np.mgrid[0:h, 0:w].astype(np.float32)
    if body_render_mode == "silhouette":
        shoulder_y0 = min(h - 1, max(int(y + roi_h + h * 0.02), int(h * 0.76)))
        shoulder_y1 = min(h, max(shoulder_y0 + 1, int(h * 0.88)))
        shoulder_rows = body_mask[shoulder_y0:shoulder_y1] > 0.0
        shoulder_grid_x = grid_x[shoulder_y0:shoulder_y1]
        left_support = np.where(shoulder_rows & (shoulder_grid_x < center_x))
        right_support = np.where(shoulder_rows & (shoulder_grid_x >= center_x))
        left_center = float(np.mean(left_support[1])) if len(left_support[1]) else center_x * 0.5
        right_center = float(np.mean(right_support[1])) if len(right_support[1]) else (center_x + w) * 0.5
        left_weight = np.clip((center_x - grid_x) / max(center_x - left_center, 1.0), 0.0, 1.0)
        right_weight = np.clip((grid_x - center_x) / max(right_center - center_x, 1.0), 0.0, 1.0)
        onset_y = float(y + roi_h + max(8, int(roi_h * 0.08)))
    else:
        left_weight = np.clip((center_x - grid_x) / max(center_x, 1.0), 0.0, 1.0)
        right_weight = np.clip((grid_x - center_x) / max(w - center_x, 1.0), 0.0, 1.0)
        onset_y = 0.0
    if body_render_mode == "silhouette":
        margin_x = max(8, int(roi_w * 0.08))
        margin_y = max(8, int(roi_h * 0.08))
        protect_x0, protect_x1 = max(0, x - margin_x), min(w, x + roi_w + margin_x)
        protect_y0, protect_y1 = max(0, y - margin_y), min(h, y + roi_h + margin_y)

    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        frame = first_frame
        frame_index = 0
        while True:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if frame_index > 0:
                if points is not None and len(points) >= 6:
                    next_points, status, _errors = cv2.calcOpticalFlowPyrLK(
                        prev_gray,
                        gray,
                        points,
                        None,
                        winSize=(21, 21),
                        maxLevel=3,
                        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
                    )
                    valid = status.reshape(-1).astype(bool) if status is not None else np.zeros(len(points), dtype=bool)
                    if next_points is not None and int(valid.sum()) >= 6:
                        deltas = next_points[valid, 0, :] - points[valid, 0, :]
                        dx, dy = np.median(deltas, axis=0)
                        head_pos_x += float(np.clip(dx, -w * 0.02, w * 0.02))
                        head_pos_y += float(np.clip(dy, -h * 0.02, h * 0.02))
                        points = next_points[valid].reshape(-1, 1, 2)
                    else:
                        points = None

                if points is None or len(points) < 12:
                    current_roi = gray[y:y + roi_h, x:x + roi_w]
                    refreshed = cv2.goodFeaturesToTrack(
                        current_roi,
                        maxCorners=120,
                        qualityLevel=0.01,
                        minDistance=4,
                        mask=tracking_mask,
                        blockSize=7,
                    )
                    if refreshed is not None:
                        refreshed[:, 0, 0] += x
                        refreshed[:, 0, 1] += y
                        points = refreshed

                if body_render_mode == "silhouette":
                    slow_head_pos_x += slow_alpha * (head_pos_x - slow_head_pos_x)
                    slow_head_pos_y += slow_alpha * (head_pos_y - slow_head_pos_y)
                    highpass_x = head_pos_x - slow_head_pos_x
                    highpass_y = head_pos_y - slow_head_pos_y
                    base_limit = max_px * 0.70
                    transient_limit = max_px * 0.30
                    target_left = float(np.clip(
                        -head_pos_x * coupling_strength - head_pos_y * 0.10,
                        -base_limit, base_limit,
                    ))
                    target_right = float(np.clip(
                        head_pos_x * coupling_strength - head_pos_y * 0.10,
                        -base_limit, base_limit,
                    ))
                    target_left += float(np.clip(
                        -highpass_x * coupling_strength * 0.70 - highpass_y * 0.08,
                        -transient_limit, transient_limit,
                    ))
                    target_right += float(np.clip(
                        highpass_x * coupling_strength * 0.70 - highpass_y * 0.08,
                        -transient_limit, transient_limit,
                    ))
                    target_left = float(np.clip(target_left, -max_px, max_px))
                    target_right = float(np.clip(target_right, -max_px, max_px))
                else:
                    target_left = float(np.clip((-head_pos_x * coupling_strength - head_pos_y * 0.10), -max_px, max_px))
                    target_right = float(np.clip((head_pos_x * coupling_strength - head_pos_y * 0.10), -max_px, max_px))
                shoulder_left += alpha * (target_left - shoulder_left)
                shoulder_right += alpha * (target_right - shoulder_right)

            if body_render_mode == "silhouette":
                warped = _apply_silhouette_body_warp(
                    frame, body_mask, grid_x, grid_y, left_weight, right_weight,
                    shoulder_left, shoulder_right, max_px, onset_y,
                    protected_region=(protect_x0, protect_y0, protect_x1, protect_y1),
                    background_plate=background_plate,
                )
            else:
                warped = _apply_masked_body_warp(
                    frame, body_mask, grid_x, grid_y, left_weight, right_weight,
                    shoulder_left, shoulder_right,
                )
            proc.stdin.write(warped.tobytes())
            prev_gray = gray
            frame_index += 1
            ret, frame = cap.read()
            if not ret:
                break

        cap.release()
        proc.stdin.close()
        return_code = proc.wait()
        if return_code != 0 or not temp_raw.is_file() or temp_raw.stat().st_size <= 1000:
            print(f"[Motion] FFmpeg encode thất bại (exit code {return_code}).")
            return False

        audio_source = Path(audio_path).resolve() if audio_path else in_path
        if audio_path and not audio_source.is_file():
            print(f"[Motion] Không tìm thấy audio: {audio_source}")
            return False
        fd, target_stage_name = tempfile.mkstemp(prefix=f"_{out_path.stem}_", suffix=".mp4", dir=str(out_path.parent))
        os.close(fd)
        target_stage = Path(target_stage_name)
        target_stage.unlink(missing_ok=True)
        cmd_mux = [
            ffmpeg,
            "-y",
            "-i", str(temp_raw),
            "-i", str(audio_source),
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(target_stage),
        ]
        mux = subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if mux.returncode != 0 or not target_stage.is_file() or target_stage.stat().st_size <= 1000:
            print(f"[Motion] Không mux được audio/video: {mux.stderr.strip()}")
            target_stage.unlink(missing_ok=True)
            return False
        os.replace(target_stage, out_path)
        return True
    except (OSError, BrokenPipeError, subprocess.SubprocessError) as exc:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        print(f"[Motion] Lỗi xử lý video: {exc}")
        return False
    finally:
        cap.release()
        temp_raw.unlink(missing_ok=True)
        if target_stage is not None:
            target_stage.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Couple conservative torso motion to measured LivePortrait head motion")
    parser.add_argument("input", nargs="?", default="avatar_option_b_result.mp4")
    parser.add_argument("output", nargs="?", default="avatar_option_b_motion.mp4")
    parser.add_argument("--mode", choices=["off", "coupled"], default="off")
    parser.add_argument("--body-mask", default=None, help="Grayscale mask; white is body pixels allowed to move")
    parser.add_argument("--face-roi", nargs=4, type=int, metavar=("X", "Y", "W", "H"), default=None)
    parser.add_argument("--max-displacement-px", type=float, default=2.5)
    parser.add_argument("--head-motion-lag-seconds", type=float, default=0.14)
    parser.add_argument("--coupling-strength", type=float, default=0.25)
    parser.add_argument("--body-render-mode", choices=["interior", "silhouette"], default="interior")
    args = parser.parse_args()
    ok = apply_conversational_motion_to_video(
        args.input,
        args.output,
        mode=args.mode,
        body_mask_path=args.body_mask,
        face_roi=args.face_roi,
        max_displacement_px=args.max_displacement_px,
        head_motion_lag_seconds=args.head_motion_lag_seconds,
        coupling_strength=args.coupling_strength,
        body_render_mode=args.body_render_mode,
    )
    if not ok:
        raise SystemExit(1)
    print(f"Video đã lưu: {args.output}")
