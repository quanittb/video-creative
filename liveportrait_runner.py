"""LivePortrait Runner for Expressive Talking Avatar Generation.
Transfers 3D head motion, eye blinking, and organic facial dynamics
from a natural driving template onto static portraits (Asian male, female, 3D Pixar).
Matches standards seen in Avatar_Video.mp4.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def find_ffmpeg() -> str:
    in_path = shutil.which("ffmpeg")
    if in_path:
        return in_path
    candidates = [
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
        if c.is_dir():
            for f in c.glob("**/ffmpeg.exe"):
                if f.is_file():
                    return str(f)
    return "ffmpeg"


def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 5.0


def find_lp_python(lp_path: Path) -> str:
    # 1. Prefer current python if working
    try:
        r = subprocess.run([sys.executable, "-c", "import torch; print(torch.__version__)"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return sys.executable
    except Exception:
        pass

    # 2. Check candidate virtualenvs, but verify they are not broken shims
    candidates = [
        lp_path / "python" / "python.exe",
        lp_path / "venv" / "Scripts" / "python.exe",
        lp_path / ".venv" / "Scripts" / "python.exe",
        lp_path.parent / "python" / "python.exe",
        lp_path.parent / "venv" / "Scripts" / "python.exe",
    ]
    for c in candidates:
        if c.is_file():
            try:
                r = subprocess.run([str(c), "-c", "import sys"], capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    return str(c)
            except Exception:
                continue
    return sys.executable


def ensure_liveportrait_smoothing(lp_path: Path):
    """Automatically patch LivePortrait pipeline to apply Kalman temporal smoothing and Smart Blink Injection."""
    pipeline_py = lp_path / "src" / "live_portrait_pipeline.py"
    if not pipeline_py.is_file():
        return
    try:
        content = pipeline_py.read_text(encoding="utf-8")
        patched = False

        # 1. Patch Kalman smoothing for static image inputs
        if "x_d_r_lst_smooth" not in content:
            old_anim = """            if inf_cfg.flag_pasteback and inf_cfg.flag_do_crop and inf_cfg.flag_stitching:
                mask_ori_float = prepare_paste_back(inf_cfg.mask_crop, crop_info['M_c2o'], dsize=(source_rgb_lst[0].shape[1], source_rgb_lst[0].shape[0]))

        ######## animate ########"""
            smooth_block = """            if inf_cfg.flag_pasteback and inf_cfg.flag_do_crop and inf_cfg.flag_stitching:
                mask_ori_float = prepare_paste_back(inf_cfg.mask_crop, crop_info['M_c2o'], dsize=(source_rgb_lst[0].shape[1], source_rgb_lst[0].shape[0]))

        # Smooth driving motion trajectory for image source to eliminate unnatural head jerks
        x_d_r_lst_smooth = None
        x_d_t_lst_smooth = None
        if not flag_is_source_video and flag_is_driving_video:
            key_r = 'R' if 'R' in driving_template_dct['motion'][0].keys() else 'R_d'
            R_0 = driving_template_dct['motion'][0][key_r]
            t_0 = driving_template_dct['motion'][0]['t']
            if inf_cfg.flag_relative_motion:
                raw_r = [(driving_template_dct['motion'][k][key_r] @ R_0.transpose(0, 2, 1)) @ R_s.cpu().numpy() for k in range(n_frames)]
                raw_t = [x_s_info['t'].cpu().numpy() + (driving_template_dct['motion'][k]['t'] - t_0) for k in range(n_frames)]
            else:
                raw_r = [driving_template_dct['motion'][k][key_r] for k in range(n_frames)]
                raw_t = [driving_template_dct['motion'][k]['t'] for k in range(n_frames)]
            x_d_r_lst_smooth = smooth(raw_r, R_s.shape, device, inf_cfg.driving_smooth_observation_variance * 5.0)
            x_d_t_lst_smooth = smooth(raw_t, x_s_info['t'].shape, device, inf_cfg.driving_smooth_observation_variance * 5.0)

        ######## animate ########"""
            if old_anim in content:
                content = content.replace(old_anim, smooth_block)
                content = content.replace(
                    "R_new = x_d_r_lst_smooth[i] if flag_is_source_video else (R_d_i @ R_d_0.permute(0, 2, 1)) @ R_s",
                    "R_new = x_d_r_lst_smooth[i] if (x_d_r_lst_smooth is not None) else ((R_d_i @ R_d_0.permute(0, 2, 1)) @ R_s)\n                    if R_new.ndim == 2: R_new = R_new.unsqueeze(0)"
                )
                content = content.replace(
                    "t_new = x_s_info['t'] if flag_is_source_video else x_s_info['t'] + (x_d_i_info['t'] - x_d_0_info['t'])",
                    "t_new = x_d_t_lst_smooth[i] if (x_d_t_lst_smooth is not None) else (x_s_info['t'] + (x_d_i_info['t'] - x_d_0_info['t']))\n                    if t_new.ndim == 1: t_new = t_new.unsqueeze(0)"
                )
                patched = True

        # 2. Patch Smart Periodic Blink Injection into c_d_eyes_lst
        blink_marker = "# Smart Periodic Blink Engine: ensure natural full-eyelid blinks every 2.0 - 3.2s"
        if blink_marker not in content:
            old_prep = """        if not flag_is_driving_video:
            c_d_eyes_lst = c_d_eyes_lst*n_frames
            c_d_lip_lst = c_d_lip_lst*n_frames

        ######## prepare for pasteback ########"""
            if "# Smart Periodic Blink Engine" in content:
                import re
                content = re.sub(
                    r"        # Smart Periodic Blink Engine:.*?(?=        ######## prepare for pasteback ########)",
                    "",
                    content,
                    flags=re.DOTALL
                )
            new_prep = """        if not flag_is_driving_video:
            c_d_eyes_lst = c_d_eyes_lst*n_frames
            c_d_lip_lst = c_d_lip_lst*n_frames

        # Smart Periodic Blink Injection: ensure natural full-eyelid blinks every 2.0 - 3.2s
        if inf_cfg.flag_eye_retargeting and c_d_eyes_lst is not None and len(c_d_eyes_lst) > 0:
            try:
                base_open = float(np.mean([float(np.mean(c)) for c in c_d_eyes_lst[:min(len(c_d_eyes_lst), 25)]]))
                base_open = max(base_open, 0.35)
                t_blink = 0.8
                profile = [0.55, 0.12, 0.00, 0.18, 0.65]
                np.random.seed(42)
                while t_blink < (n_frames / output_fps) - 0.3:
                    center_f = int(t_blink * output_fps)
                    for offset, factor in zip([-2, -1, 0, 1, 2], profile):
                        idx = center_f + offset
                        if 0 <= idx < len(c_d_eyes_lst):
                            if factor == 0.0:
                                c_d_eyes_lst[idx] = np.zeros_like(c_d_eyes_lst[idx])
                            else:
                                val = min(float(np.mean(c_d_eyes_lst[idx])), base_open * factor)
                                c_d_eyes_lst[idx] = np.full_like(c_d_eyes_lst[idx], val)
                    t_blink += float(np.random.uniform(2.0, 3.2))
                log("Smart Periodic Blink Engine: Injected natural eye blinks.", style="bold green")
            except Exception as e:
                log(f"Blink injection notice: {e}")

        ######## prepare for pasteback ########"""
            if old_prep in content:
                content = content.replace(old_prep, new_prep)
                patched = True

        # 3. Fix LivePortrait relative motion + decouple eye retargeting from head multiplier
        if "eyes_delta * 1.15" not in content:
            stock_code = """                if inf_cfg.flag_relative_motion:  # use x_s
                    x_d_i_new = x_s + \
                        (eyes_delta if eyes_delta is not None else 0) + \
                        (lip_delta if lip_delta is not None else 0)
                else:  # use x_d,i
                    x_d_i_new = x_d_i_new + \
                        (eyes_delta if eyes_delta is not None else 0) + \
                        (lip_delta if lip_delta is not None else 0)

                if inf_cfg.flag_stitching:
                    x_d_i_new = self.live_portrait_wrapper.stitching(x_s, x_d_i_new)

            x_d_i_new = x_s + (x_d_i_new - x_s) * inf_cfg.driving_multiplier"""

            prev_code = """                # Keep 3D head rotation/translation and add eye/lip retargeting delta seamlessly
                x_d_i_new = x_d_i_new + \
                    (eyes_delta if eyes_delta is not None else 0) + \
                    (lip_delta if lip_delta is not None else 0)

                if inf_cfg.flag_stitching:
                    x_d_i_new = self.live_portrait_wrapper.stitching(x_s, x_d_i_new)

            x_d_i_new = x_s + (x_d_i_new - x_s) * inf_cfg.driving_multiplier"""

            new_code = """                if inf_cfg.flag_stitching:
                    x_d_i_new = self.live_portrait_wrapper.stitching(x_s, x_d_i_new)

            # Apply head motion multiplier, while keeping eye blinks crisp and 100% full depth
            x_d_i_new = x_s + (x_d_i_new - x_s) * inf_cfg.driving_multiplier
            if inf_cfg.flag_eye_retargeting and 'eyes_delta' in locals() and eyes_delta is not None:
                x_d_i_new = x_d_i_new + eyes_delta * 1.15
            if inf_cfg.flag_lip_retargeting and 'lip_delta' in locals() and lip_delta is not None:
                x_d_i_new = x_d_i_new + lip_delta"""

            if stock_code in content:
                content = content.replace(stock_code, new_code)
                patched = True
            elif prev_code in content:
                content = content.replace(prev_code, new_code)
                patched = True

        if patched:
            pipeline_py.write_text(content, encoding="utf-8")
            print("  [Auto-Patch] Da kich hoat Kalman Smoothing + Smart Blink Engine cho LivePortrait!")
    except Exception as e:
        print(f"  [!] Luu y khi patch LivePortrait: {e}")


def apply_torso_micro_kinematics(in_path: str, out_path: str) -> bool:
    """Apply organic torso micro-breathing and coupled shoulder movement to eliminate static cutout feel."""
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(in_path)
        if not cap.isOpened():
            return False
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ret, f0 = cap.read()
        if not ret:
            cap.release()
            return False
        h, w, _ = f0.shape

        # Load benchmark trajectory if available
        traj_candidates = [
            Path(__file__).resolve().parent.parent / "assets" / "driving_templates" / "torso_motion_trajectory.json",
            Path("assets/driving_templates/torso_motion_trajectory.json"),
            Path.home() / "Dropbox" / "PC" / "Downloads" / "torso_motion_trajectory.json",
            Path("C:/Users/Admin/Dropbox/PC/Downloads/torso_motion_trajectory.json"),
            Path("C:/Users/quant/Dropbox/PC/Downloads/torso_motion_trajectory.json"),
        ]
        traj_data = None
        for tc in traj_candidates:
            if tc.is_file():
                try:
                    import json
                    with open(tc, "r", encoding="utf-8") as tf:
                        traj_data = json.load(tf)
                        break
                except Exception:
                    pass

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

        y_chin = int(0.48 * h)
        y_collar = int(0.56 * h)
        y_max = float(h)
        cx = w / 2.0

        grid_y, grid_x = np.mgrid[0:h, 0:w].astype(np.float32)
        weight = np.zeros((h, w), dtype=np.float32)

        # Transition ramp from chin to collar
        ramp_mask = (grid_y >= y_chin) & (grid_y < y_collar)
        t = (grid_y[ramp_mask] - y_chin) / max(y_collar - y_chin, 1.0)
        weight[ramp_mask] = 0.5 * (1.0 - np.cos(np.pi * t))

        # Torso zone (keeps strong shoulder articulation, smooth bottom anchoring)
        torso_mask = (grid_y >= y_collar)
        t_down = (grid_y[torso_mask] - y_collar) / max(y_max - y_collar, 1.0)
        weight[torso_mask] = 1.0 - 0.45 * (t_down ** 1.5)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

        if traj_data and "heave_y" in traj_data:
            heave_y = np.array(traj_data["heave_y"])
            shrug_y = np.array(traj_data["shrug_y"])
            sway_x = np.array(traj_data["sway_x"])
            n_traj = len(heave_y)
            # Boost vertical shoulder heave to match benchmark strong breathing and emphasis (2.4x)
            scale_y = (h / 610.0) * 2.4
            scale_x = (w / 1080.0) * 1.2

            for i, frame in enumerate(frames):
                t_idx = i % n_traj
                dist_ratio = np.abs(grid_x - cx) / (w * 0.5)
                shoulder_boost = 0.85 + 0.35 * dist_ratio
                h_y = float(heave_y[t_idx]) * scale_y * shoulder_boost
                s_y = float(shrug_y[t_idx]) * scale_y * ((grid_x - cx) / (w * 0.35))
                s_x = float(sway_x[t_idx]) * scale_x

                total_dy = (h_y + s_y) * weight
                total_dx = s_x * weight

                map_y = (grid_y - total_dy).astype(np.float32)
                map_x = (grid_x - total_dx).astype(np.float32)

                warped = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                out.write(warped)
            out.release()
            print(f"  [TorsoKinematics] Da ap dung quy dao day vai manh chuan mau ({fc} frames tu Avatar_Video)!")
            return True
        else:
            # Fallback to analytical vertical heave and shrug
            for i, frame in enumerate(frames):
                breath_y = 6.5 * np.sin(2.0 * np.pi * i / (fps * 3.6))
                shrug_y = 3.5 * np.sin(2.0 * np.pi * i / (fps * 2.4)) * ((grid_x - cx) / (w * 0.40))
                total_dy = (breath_y + shrug_y) * weight
                map_y = (grid_y - total_dy).astype(np.float32)
                map_x = grid_x
                warped = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                out.write(warped)
            out.release()
            print(f"  [TorsoKinematics] Da tao nhip tho & day vai sinh hoc ({fc} frames)!")
            return True
    except Exception as e:
        print(f"  [!] Luu y TorsoKinematics: {e}")
        return False


def run_liveportrait(
    source_img: str,
    driving_video: str,
    audio_path: str,
    output_path: str,
    liveportrait_dir: Optional[str] = None,
    driving_multiplier: float = 0.80,
    flag_eye_retargeting: bool = True,
) -> bool:
    """Run LivePortrait inference and attach synchronized speech audio."""
    lp_path = Path(liveportrait_dir or (Path(__file__).resolve().parent.parent / "LivePortrait"))
    infer_py = lp_path / "inference.py"
    ffmpeg = find_ffmpeg()

    # Ensure temporal smoothing and smart blink injection are active
    ensure_liveportrait_smoothing(lp_path)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.is_file():
        out_file.unlink(missing_ok=True)
    temp_dir = out_file.parent / f"_lp_temp_{out_file.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    dur = get_audio_duration(audio_path)

    # 1. Prepare driving video matching audio duration if necessary
    prepared_driving = temp_dir / "prepared_driving.mp4"
    cmd_prep = [
        ffmpeg, "-y",
        "-stream_loop", "-1",
        "-i", str(driving_video),
        "-t", str(dur),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(prepared_driving),
    ]
    subprocess.run(cmd_prep, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. If LivePortrait repo is present, execute inference
    if infer_py.is_file():
        lp_py = find_lp_python(lp_path)
        print(f"[LivePortrait] Running GPU inference via {lp_py} for {Path(source_img).name} (multiplier={driving_multiplier}, option=pose-friendly, eye_retargeting={flag_eye_retargeting})...")
        cmd_lp = [
            lp_py,
            str(infer_py),
            "-s", str(source_img),
            "-d", str(prepared_driving),
            "-o", str(temp_dir),
            "--flag_relative_motion",
            "--flag_pasteback",
            "--driving_option", "pose-friendly",
            "--driving_multiplier", str(driving_multiplier),
        ]
        if flag_eye_retargeting:
            cmd_lp.append("--flag_eye_retargeting")
        proc = subprocess.run(cmd_lp, cwd=str(lp_path), text=True)
        if proc.returncode == 0:
            # Prioritize full-resolution pasteback output over low-res 3-panel concat preview
            pastebacks = list(temp_dir.glob("*pasteback*.mp4"))
            non_concats = [v for v in temp_dir.glob("*.mp4") if v != prepared_driving and not v.name.endswith("_concat.mp4")]
            gen_videos = pastebacks or non_concats or [v for v in temp_dir.glob("*.mp4") if v != prepared_driving]
            if gen_videos:
                raw_anim = gen_videos[0]
                
                # Apply Torso & Shoulder Elastic Kinematics (Micro-Breathing + Coupled Shoulder Tilt)
                torso_anim = temp_dir / "torso_kinematics.mp4"
                ok_torso = apply_torso_micro_kinematics(str(raw_anim), str(torso_anim))
                video_to_merge = torso_anim if (ok_torso and torso_anim.is_file()) else raw_anim

                # Merge with speech audio
                cmd_merge = [
                    ffmpeg, "-y",
                    "-i", str(video_to_merge),
                    "-i", str(audio_path),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-shortest",
                    str(out_file),
                ]
                subprocess.run(cmd_merge, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return True
        else:
            print(f"[LivePortrait] Tien trinh inference that bai voi exit code: {proc.returncode}!")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    # Fallback if LivePortrait repo is not found
    print(f"[LivePortrait] Khong tim thay ma nguon LivePortrait tai {liveportrait_dir}, bo qua Chặng 1.")
    shutil.rmtree(temp_dir, ignore_errors=True)
    return False



def main():
    parser = argparse.ArgumentParser(description="LivePortrait Runner")
    parser.add_argument("--source", required=True, help="Path to character source portrait image")
    parser.add_argument("--driving", required=True, help="Path to motion driving video template")
    parser.add_argument("--audio", required=True, help="Path to scene speech audio")
    parser.add_argument("--output", required=True, help="Path to output video file")
    default_lp = str(Path(__file__).resolve().parent.parent / "LivePortrait")
    parser.add_argument("--lp_dir", default=default_lp, help="LivePortrait root directory")
    args = parser.parse_args()

    run_liveportrait(
        source_img=args.source,
        driving_video=args.driving,
        audio_path=args.audio,
        output_path=args.output,
        liveportrait_dir=args.lp_dir,
    )


if __name__ == "__main__":
    main()
