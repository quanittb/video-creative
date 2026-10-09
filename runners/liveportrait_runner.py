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
import tempfile
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
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Không đọc được thời lượng audio {audio_path}: {res.stderr.strip()}")
    try:
        duration = float(res.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe trả thời lượng audio không hợp lệ: {res.stdout.strip()!r}") from exc
    if duration <= 0:
        raise RuntimeError(f"Audio không có thời lượng hợp lệ: {audio_path}")
    return duration


def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Không đọc được thời lượng driving video {video_path}: {res.stderr.strip()}")
    try:
        duration = float(res.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe trả thời lượng driving không hợp lệ: {res.stdout.strip()!r}") from exc
    if duration <= 0:
        raise RuntimeError(f"Driving video không có thời lượng hợp lệ: {video_path}")
    return duration


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

        # 1. Patch Kalman smoothing + Euler Pose Stabilization for static image inputs
        if "Euler Pose Stabilization" not in content:
            euler_smooth_block = """            if inf_cfg.flag_pasteback and inf_cfg.flag_do_crop and inf_cfg.flag_stitching:
                mask_ori_float = prepare_paste_back(inf_cfg.mask_crop, crop_info['M_c2o'], dsize=(source_rgb_lst[0].shape[1], source_rgb_lst[0].shape[0]))

        # Smooth driving motion trajectory for image source with Euler Pose Stabilization (eliminates unnatural bobblehead tilt & restless shaking)
        x_d_r_lst_smooth = None
        x_d_t_lst_smooth = None
        if not flag_is_source_video and flag_is_driving_video:
            key_r = 'R' if 'R' in driving_template_dct['motion'][0].keys() else 'R_d'
            R_0 = driving_template_dct['motion'][0][key_r]
            t_0 = driving_template_dct['motion'][0]['t']
            has_euler = ('pitch' in driving_template_dct['motion'][0] and 'pitch' in x_s_info)
            if inf_cfg.flag_relative_motion:
                if has_euler:
                    # Professional MC Stabilization: Preserve natural micro-nodding (Pitch 0.70x),
                    # while heavily dampening bobblehead sideways tilt (Roll 0.20x) and side-turning (Yaw 0.30x)
                    p_0 = torch.tensor(driving_template_dct['motion'][0]['pitch'], device=device)
                    y_0 = torch.tensor(driving_template_dct['motion'][0]['yaw'], device=device)
                    r_0 = torch.tensor(driving_template_dct['motion'][0]['roll'], device=device)
                    p_s = x_s_info['pitch']
                    y_s = x_s_info['yaw']
                    r_s = x_s_info['roll']

                    raw_r = []
                    for k in range(n_frames):
                        p_k = torch.tensor(driving_template_dct['motion'][k]['pitch'], device=device)
                        y_k = torch.tensor(driving_template_dct['motion'][k]['yaw'], device=device)
                        r_k = torch.tensor(driving_template_dct['motion'][k]['roll'], device=device)
                        p_new = p_s + (p_k - p_0) * 1.00
                        y_new = y_s + (y_k - y_0) * 0.85
                        r_new = r_s + (r_k - r_0) * 0.65
                        R_mat = get_rotation_matrix(p_new, y_new, r_new)
                        raw_r.append(R_mat.cpu().numpy())
                else:
                    raw_r = [(driving_template_dct['motion'][k][key_r] @ R_0.transpose(0, 2, 1)) @ R_s.cpu().numpy() for k in range(n_frames)]
                raw_t = [x_s_info['t'].cpu().numpy() + (driving_template_dct['motion'][k]['t'] - t_0) * 0.80 for k in range(n_frames)]
            else:
                raw_r = [driving_template_dct['motion'][k][key_r] for k in range(n_frames)]
                raw_t = [driving_template_dct['motion'][k]['t'] for k in range(n_frames)]
            x_d_r_lst_smooth = smooth(raw_r, R_s.shape, device, inf_cfg.driving_smooth_observation_variance * 1.5)
            x_d_t_lst_smooth = smooth(raw_t, x_s_info['t'].shape, device, inf_cfg.driving_smooth_observation_variance * 1.5)

        ######## animate ########"""
            if "x_d_r_lst_smooth = None" in content:
                import re
                content = re.sub(
                    r"        # Smooth driving motion trajectory.*?(?=        ######## animate ########)",
                    euler_smooth_block.replace("            if inf_cfg.flag_pasteback and inf_cfg.flag_do_crop and inf_cfg.flag_stitching:\n                mask_ori_float = prepare_paste_back(inf_cfg.mask_crop, crop_info['M_c2o'], dsize=(source_rgb_lst[0].shape[1], source_rgb_lst[0].shape[0]))\n\n", "") + "\n",
                    content,
                    flags=re.DOTALL
                )
                patched = True
            else:
                old_anim = """            if inf_cfg.flag_pasteback and inf_cfg.flag_do_crop and inf_cfg.flag_stitching:
                mask_ori_float = prepare_paste_back(inf_cfg.mask_crop, crop_info['M_c2o'], dsize=(source_rgb_lst[0].shape[1], source_rgb_lst[0].shape[0]))

        ######## animate ########"""
                if old_anim in content:
                    content = content.replace(old_anim, euler_smooth_block)
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
            # Balanced vertical shoulder heave to match organic presenter breathing (1.15x)
            scale_y = (h / 610.0) * 1.15
            scale_x = (w / 1080.0) * 0.85

            for i, frame in enumerate(frames):
                t_idx = i % n_traj
                h_y = float(heave_y[t_idx]) * scale_y
                s_y = float(shrug_y[t_idx]) * scale_y * 0.45 * ((grid_x - cx) / (w * 0.40))
                s_x = float(sway_x[t_idx]) * scale_x

                total_dy = (h_y + s_y) * weight
                total_dx = s_x * weight

                map_y = (grid_y - total_dy).astype(np.float32)
                map_x = (grid_x - total_dx).astype(np.float32)

                warped = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                out.write(warped)
            out.release()
            print(f"  [TorsoKinematics] Da ap dung nhip tho & dong bo vai-nguc tu nhien ({fc} frames)!")
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
    driving_multiplier: float = 0.55,
    flag_eye_retargeting: bool = False,
    source_max_dim: int = 1280,
    fps: int = 25,
    driving_policy: str = "hold",
    legacy_vendor_patch: bool = False,
) -> bool:
    """Run one LivePortrait pass and attach the original speech audio."""
    source_path = Path(source_img).resolve()
    driving_path = Path(driving_video).resolve()
    audio_file = Path(audio_path).resolve()
    out_file = Path(output_path).resolve()
    lp_path = Path(liveportrait_dir or (Path(__file__).resolve().parent.parent / "LivePortrait")).resolve()
    infer_py = lp_path / "inference.py"
    ffmpeg = find_ffmpeg()

    if not source_path.is_file():
        print(f"[LivePortrait] Không tìm thấy ảnh nguồn: {source_path}")
        return False
    if not driving_path.is_file():
        print(f"[LivePortrait] Không tìm thấy driving video: {driving_path}")
        return False
    if not audio_file.is_file():
        print(f"[LivePortrait] Không tìm thấy audio: {audio_file}")
        return False
    if not infer_py.is_file():
        print(f"[LivePortrait] Không tìm thấy inference.py tại {infer_py}")
        return False
    if source_max_dim <= 0 or fps <= 0:
        print("[LivePortrait] source_max_dim và fps phải lớn hơn 0.")
        return False
    if driving_policy not in {"hold", "loop"}:
        print("[LivePortrait] driving_policy chỉ nhận 'hold' hoặc 'loop'.")
        return False

    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="vcs_lp_"))
    muxed_output = None
    try:
        dur = get_audio_duration(str(audio_file))
        driving_duration = get_video_duration(str(driving_path))
        prepared_driving = temp_dir / "prepared_driving.mp4"
        video_filters = [f"fps={fps}"]
        input_options = []
        if driving_policy == "loop":
            input_options = ["-stream_loop", "-1"]
        elif driving_duration < dur:
            video_filters.append(f"tpad=stop_mode=clone:stop_duration={dur - driving_duration:.6f}")

        cmd_prep = [
            ffmpeg, "-y", *input_options,
            "-i", str(driving_path),
            "-vf", ",".join(video_filters),
            "-an", "-t", f"{dur:.6f}",
            "-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(prepared_driving),
        ]
        prep = subprocess.run(cmd_prep, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if prep.returncode != 0 or not prepared_driving.is_file():
            raise RuntimeError(f"Không chuẩn hóa được driving video: {prep.stderr.strip()}")

        if legacy_vendor_patch:
            ensure_liveportrait_smoothing(lp_path)

        lp_py = find_lp_python(lp_path)
        raw_anim = temp_dir / f"{source_path.stem}--{prepared_driving.stem}.mp4"
        print(
            f"[LivePortrait] {source_path.name}; multiplier={driving_multiplier}; "
            f"fps={fps}; source_max_dim={source_max_dim}; eye_retargeting={flag_eye_retargeting}; "
            f"legacy_patches={legacy_vendor_patch}"
        )
        cmd_lp = [
            lp_py,
            str(infer_py),
            "-s", str(source_path),
            "-d", str(prepared_driving),
            "-o", str(temp_dir),
            "--flag_relative_motion",
            "--flag_pasteback",
            "--flag_crop_driving_video",
            "--driving_option", "expression-friendly",
            "--driving_multiplier", str(driving_multiplier),
            "--source_max_dim", str(source_max_dim),
        ]
        if flag_eye_retargeting:
            cmd_lp.append("--flag_eye_retargeting")
        child_env = os.environ.copy()
        if legacy_vendor_patch:
            child_env["VCS_LEGACY_MOTION_PATCHES"] = "1"
        else:
            child_env.pop("VCS_LEGACY_MOTION_PATCHES", None)
        proc = subprocess.run(cmd_lp, cwd=str(lp_path), text=True, env=child_env)
        if proc.returncode != 0:
            print(f"[LivePortrait] Inference thất bại với exit code {proc.returncode}.")
            return False
        if not raw_anim.is_file() or raw_anim.stat().st_size <= 1000:
            print(f"[LivePortrait] Inference không tạo được video pasteback dự kiến: {raw_anim}")
            return False

        fd, muxed_name = tempfile.mkstemp(prefix=f"_{out_file.stem}_lp_", suffix=".mp4", dir=str(out_file.parent))
        os.close(fd)
        muxed_output = Path(muxed_name)
        muxed_output.unlink(missing_ok=True)
        cmd_merge = [
            ffmpeg, "-y",
            "-i", str(raw_anim),
            "-i", str(audio_file),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(muxed_output),
        ]
        merge = subprocess.run(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if merge.returncode != 0 or not muxed_output.is_file() or muxed_output.stat().st_size <= 1000:
            raise RuntimeError(f"Không mux được audio gốc vào video LivePortrait: {merge.stderr.strip()}")
        os.replace(muxed_output, out_file)
        return True
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[LivePortrait] Lỗi pipeline: {exc}")
        return False
    finally:
        if muxed_output is not None:
            muxed_output.unlink(missing_ok=True)
        shutil.rmtree(temp_dir, ignore_errors=True)



def main():
    parser = argparse.ArgumentParser(description="LivePortrait Runner")
    parser.add_argument("--source", required=True, help="Path to character source portrait image")
    parser.add_argument("--driving", required=True, help="Path to motion driving video template")
    parser.add_argument("--audio", required=True, help="Path to scene speech audio")
    parser.add_argument("--output", required=True, help="Path to output video file")
    default_lp = str(Path(__file__).resolve().parent.parent / "LivePortrait")
    parser.add_argument("--lp_dir", default=default_lp, help="LivePortrait root directory")
    parser.add_argument("--source-max-dim", type=int, default=1280)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--multiplier", type=float, default=0.55)
    parser.add_argument("--driving-policy", choices=["hold", "loop"], default="hold")
    parser.add_argument("--flag-eye-retargeting", action="store_true", default=False)
    parser.add_argument("--legacy-vendor-patches", action="store_true", default=False)
    args = parser.parse_args()

    ok = run_liveportrait(
        source_img=args.source,
        driving_video=args.driving,
        audio_path=args.audio,
        output_path=args.output,
        liveportrait_dir=args.lp_dir,
        driving_multiplier=args.multiplier,
        flag_eye_retargeting=args.flag_eye_retargeting,
        source_max_dim=args.source_max_dim,
        fps=args.fps,
        driving_policy=args.driving_policy,
        legacy_vendor_patch=args.legacy_vendor_patches,
    )
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
