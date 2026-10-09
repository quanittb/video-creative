# coding: utf-8
"""
Conversational Biomechanics & Kinematics Engine
------------------------------------------------
Replaces robotic, symmetric, periodic animation with authentic human conversational physics:
1. Micro-variation + Easing + Asymmetry in head pose (yaw, pitch, roll).
2. Natural moments of Stillness (movement -> still -> micro-gesture -> settle).
3. Elastic cervical neck coupling to dissolve the "floating cutout" head artifact.
4. Asymmetric, delayed shoulder articulation (amplitude 2-4/10, L/R decoupled, 3-4 frame phase lag).
5. Sub-perceptual upper-torso weight shifts.
"""

import math
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


def smooth_1d(arr: np.ndarray, window_size: int = 5) -> np.ndarray:
    """Apply zero-phase symmetric box smoothing."""
    if len(arr) < window_size:
        return arr
    pad = window_size // 2
    padded = np.pad(arr, pad, mode="edge")
    kernel = np.ones(window_size) / window_size
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[:len(arr)]


def generate_conversational_profile(n_frames: int, fps: float = 25.0) -> Dict[str, np.ndarray]:
    """
    Generate an organic, non-repeating, asymmetric conversational motion profile.
    Follows human speech mechanics:
    - Emphasis nodules on stressed syllables (Pitch micro-nod: -0.8 to -1.5 deg).
    - Subtle, attentive gaze holds (Yaw: +0.4 to +1.0 deg, asymmetric, non-returning).
    - Tiny roll adjustment (Roll: <= 0.6 deg).
    - Substantial STILLNESS windows (0.8s - 2.0s periods of resting posture).
    - Shoulder micro-articulation (amplitude 2-4/10, L/R asymmetric, 3-4 frames lag).
    """
    total_time = n_frames / fps
    pitch = np.zeros(n_frames, dtype=np.float32)
    yaw = np.zeros(n_frames, dtype=np.float32)
    roll = np.zeros(n_frames, dtype=np.float32)
    sh_left = np.zeros(n_frames, dtype=np.float32)
    sh_right = np.zeros(n_frames, dtype=np.float32)
    torso_sway = np.zeros(n_frames, dtype=np.float32)

    # Dynamic conversational events schedule
    # Format: (trigger_time_sec, duration_sec, delta_pitch_deg, delta_yaw_deg, delta_roll_deg, sh_L_px, sh_R_px)
    events = []
    curr_t = 0.55
    rng = np.random.RandomState(42)

    while curr_t < total_time - 0.4:
        # Duration of gesture: 0.35s - 0.60s
        dur = float(rng.uniform(0.35, 0.58))
        # Pitch: predominantly downward nod for emphasis (-0.7 to -1.6 deg)
        dp = float(rng.uniform(-1.6, -0.7))
        # Yaw: small asymmetric shift (-0.8 to +0.9 deg), alternating sides with unequal amplitude
        dy = float(rng.choice([-1.0, 1.0]) * rng.uniform(0.35, 0.85))
        # Roll: strictly micro-tilt (0.20 to 0.55 deg)
        dr = float(rng.uniform(-0.45, 0.45))
        # Shoulders: subtle (amplitude 2-4/10 => 1.5 to 3.8 px), coupled directly to Left/Right Yaw direction
        yaw_intensity = float(np.clip(abs(dy) / 0.6, 0.6, 1.4))
        if dy > 0:
            # Head turns RIGHT: left shoulder shifts forward/lifts slightly, right shoulder relaxes/counter-drops
            sL = float(rng.uniform(2.0, 3.8)) * yaw_intensity
            sR = float(rng.uniform(-1.2, -0.2)) * yaw_intensity
        else:
            # Head turns LEFT: right shoulder shifts forward/lifts slightly, left shoulder relaxes/counter-drops
            sL = float(rng.uniform(-1.2, -0.2)) * yaw_intensity
            sR = float(rng.uniform(2.0, 3.8)) * yaw_intensity

        events.append((curr_t, dur, dp, dy, dr, sL, sR))
        # Stillness plateau between movements: 1.0s to 2.4s of calm, grounded posture
        stillness_gap = float(rng.uniform(1.1, 2.2))
        curr_t += dur + stillness_gap

    # Synthesize smooth curves with non-linear easing & settling
    for (t0, dur, dp, dy, dr, sL, sR) in events:
        idx0 = int(t0 * fps)
        n_ev = int(dur * fps)
        for i in range(n_ev):
            k = idx0 + i
            if k >= n_frames:
                break
            s = i / float(max(n_ev - 1, 1))
            # Smooth minimum-jerk pulse: sin^1.4(pi * s)
            pulse = math.pow(math.sin(math.pi * s), 1.4)
            pitch[k] += dp * pulse
            # Yaw has a subtle persistent posture shift (does not swing back to zero identically)
            yaw_progress = 0.5 * (1.0 - math.cos(math.pi * s))
            yaw[k:] += (dy * 0.35 / n_ev) * (1.0 - s * 0.5)
            roll[k] += dr * pulse

        # Shoulder articulation: lags by 3-4 frames (0.12 - 0.16s) and settles slower
        sh_lag = 4
        n_sh = int((dur + 0.30) * fps)
        for i in range(n_sh):
            k = idx0 + sh_lag + i
            if k >= n_frames:
                break
            s = i / float(max(n_sh - 1, 1))
            # Underdamped settling curve: sin(pi * s) * exp(-1.8 * s)
            decay_pulse = math.sin(math.pi * s) * math.exp(-1.8 * s) * 2.1
            sh_left[k] += sL * decay_pulse
            sh_right[k] += sR * decay_pulse

    # Torso: ultra-slow sub-perceptual weight shift (barely 1.2px) over 7 seconds
    t_axis = np.arange(n_frames, dtype=np.float32) / fps
    torso_sway = 1.2 * np.sin(2.0 * np.pi * t_axis / 6.8).astype(np.float32)

    # Add pink physiological micro-tremor (< 0.04 deg) to prevent rigid mannequin freezing during stillness
    micro_tremor = smooth_1d(rng.normal(0, 0.035, n_frames).astype(np.float32), 7)
    pitch += micro_tremor
    yaw += micro_tremor * 0.6
    roll += micro_tremor * 0.3

    # Ensure zero-phase smoothing
    pitch = smooth_1d(pitch, 5)
    yaw = smooth_1d(yaw, 5)
    roll = smooth_1d(roll, 5)
    sh_left = smooth_1d(sh_left, 5)
    sh_right = smooth_1d(sh_right, 5)

    return {
        "pitch": pitch,
        "yaw": yaw,
        "roll": roll,
        "sh_left": sh_left,
        "sh_right": sh_right,
        "torso_sway": torso_sway,
    }


def apply_conversational_biomechanics_to_video(
    in_video_path: str,
    out_video_path: str,
    motion_profile: Optional[Dict[str, np.ndarray]] = None,
) -> bool:
    """
    Applies organic cervical elasticity and decoupled, asymmetric shoulder micro-articulation.
    Solves:
    1. Cutout head disconnect via smooth cervical tension gradient (chin -> collar).
    2. Over-animated shoulders by pinning amplitude to 2-4/10 with L/R asymmetry.
    3. Shoulder delay (reacts after head, settles with damping).
    4. Sub-perceptual torso weight shifts with generous stillness plateaus.
    """
    try:
        import cv2

        cap = cv2.VideoCapture(in_video_path)
        if not cap.isOpened():
            return False
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ret, f0 = cap.read()
        if not ret:
            cap.release()
            return False
        h, w, _ = f0.shape

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        frames = []
        for _ in range(fc):
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        if not frames:
            return False

        if motion_profile is None:
            motion_profile = generate_conversational_profile(len(frames), fps=fps)

        sh_left = motion_profile["sh_left"]
        sh_right = motion_profile["sh_right"]
        torso_sway = motion_profile["torso_sway"]

        # Anatomical vertical landmarks (based on standard portrait framing)
        y_chin = int(0.48 * h)
        y_collar = int(0.56 * h)
        y_max = float(h)
        cx = w / 2.0

        grid_y, grid_x = np.mgrid[0:h, 0:w].astype(np.float32)

        # 1. Cervical elastic coupling mask (neck follows head with tension gradient)
        neck_weight = np.zeros((h, w), dtype=np.float32)
        neck_mask = (grid_y >= y_chin) & (grid_y < y_collar)
        t_neck = (grid_y[neck_mask] - y_chin) / max(y_collar - y_chin, 1.0)
        # S-curve smoothstep for natural tissue elasticity
        neck_weight[neck_mask] = t_neck * t_neck * (3.0 - 2.0 * t_neck)

        # 2. Torso & shoulder anchoring mask
        torso_weight = np.zeros((h, w), dtype=np.float32)
        torso_mask = grid_y >= y_collar
        t_torso = (grid_y[torso_mask] - y_collar) / max(y_max - y_collar, 1.0)
        torso_weight[torso_mask] = 1.0 - 0.50 * (t_torso ** 1.3)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(out_video_path, fourcc, fps, (w, h))

        # Normalized horizontal factor: -1.0 at left edge, 0 at center, +1.0 at right edge
        lateral_factor = (grid_x - cx) / (w * 0.50)
        # Blend weights for Left Shoulder vs Right Shoulder
        left_shoulder_weight = np.clip(-lateral_factor, 0.0, 1.0)
        right_shoulder_weight = np.clip(lateral_factor, 0.0, 1.0)
        center_sternum_weight = 1.0 - (left_shoulder_weight + right_shoulder_weight)

        n_profile = len(sh_left)

        for i, frame in enumerate(frames):
            idx = i % n_profile
            sl = float(sh_left[idx])
            sr = float(sh_right[idx])
            sw = float(torso_sway[idx])

            # Asymmetric shoulder displacement: each side acts independently
            # Scale displacement proportionally to 1080p height (subtle: max 3-5px in 1080p)
            scale = h / 1080.0
            dy_shoulder = (sl * left_shoulder_weight + sr * right_shoulder_weight + 0.3 * (sl + sr) * center_sternum_weight) * scale
            dx_sway = sw * scale

            # Neck receives 40% of shoulder reaction to eliminate the pinned-cutout seam
            total_dy = dy_shoulder * torso_weight + (dy_shoulder * 0.40) * neck_weight
            total_dx = dx_sway * (torso_weight + neck_weight * 0.50)

            map_y = (grid_y - total_dy).astype(np.float32)
            map_x = (grid_x - total_dx).astype(np.float32)

            warped = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            out.write(warped)

        out.release()
        return True
    except Exception as e:
        print(f"  [!] ConversationalBiomechanics notice: {e}")
        return False
