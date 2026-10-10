#!/usr/bin/env python3
"""GPU-side adapter for the pinned EchoMimic V3 Flash source checkout."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _runtime_version_errors(modules: Mapping[str, Any]) -> List[str]:
    if sys.version_info[:2] != (3, 11):
        return ["Python {}.{}; yêu cầu 3.11.x".format(sys.version_info.major, sys.version_info.minor)]
    required_versions = {
        "torch": "2.5.1+cu124",
        "torchvision": "0.20.1+cu124",
        "diffusers": "0.32.2",
        "transformers": "4.46.3",
        "accelerate": "1.1.1",
        "numpy": "1.26.4",
    }
    installed_versions = {
        "torch": str(modules["torch"].__version__),
        "torchvision": str(modules["torchvision"].__version__),
        "diffusers": str(modules["diffusers"].__version__),
        "transformers": str(modules["transformers"].__version__),
        "accelerate": _package_version("accelerate"),
        "numpy": _package_version("numpy"),
    }
    return ["{}={} (yêu cầu {})".format(name, installed_versions[name], expected)
            for name, expected in required_versions.items() if installed_versions[name] != expected]


def _import_runtime_modules() -> Dict[str, Any]:
    import numpy
    import torch
    import diffusers
    import transformers
    import librosa
    import pyloudnorm
    import omegaconf
    import einops
    import torchvision
    import sentencepiece
    import safetensors

    from transformers import AutoTokenizer, Wav2Vec2FeatureExtractor
    from src.fm_solvers_unipc import FlowUniPCMultistepScheduler
    from src.pipeline_wan_fun_inpaint_audio_2512 import WanFunInpaintAudioPipeline
    from src.wan_image_encoder import CLIPModel
    from src.wan_text_encoder import WanT5EncoderModel
    from src.wan_transformer3d_audio_2512 import WanTransformerAudioMask3DModel
    from src.wan_vae import AutoencoderKLWan
    from src.wav2vec2 import Wav2Vec2Model

    return locals()


def runtime_probe(echo_root: Path) -> int:
    print("Python: {}".format(sys.version.replace("\n", " ")))
    try:
        modules = _import_runtime_modules()
    except Exception:
        print("ERROR: Echo runtime import không hoàn tất:")
        traceback.print_exc()
        return 1
    torch = modules["torch"]
    print("torch={} | diffusers={} | transformers={}".format(
        modules["torch"].__version__, modules["diffusers"].__version__, modules["transformers"].__version__
    ))
    for package in ("accelerate", "numpy", "librosa", "pyloudnorm", "einops", "torchvision", "sentencepiece", "safetensors"):
        print("{}={}".format(package, _package_version(package)))
    mismatched = _runtime_version_errors(modules)
    if mismatched:
        print("ERROR: Version runtime lệch pin: " + "; ".join(mismatched))
        return 1
    if not torch.cuda.is_available():
        print("ERROR: PyTorch trong venv không nhận CUDA. Không fallback sang CPU.")
        return 1
    device = torch.cuda.get_device_properties(0)
    total_gib = device.total_memory / (1024 ** 3)
    try:
        free_bytes, _ = torch.cuda.mem_get_info(0)
    except TypeError:
        free_bytes, _ = torch.cuda.mem_get_info()
    bf16 = bool(torch.cuda.is_bf16_supported())
    print("GPU: {} | VRAM {:.2f} GiB | đang trống {:.2f} GiB | BF16 {}".format(
        device.name, total_gib, free_bytes / (1024 ** 3), "supported" if bf16 else "unsupported"
    ))
    print("Echo source: {}".format(echo_root))
    if total_gib < 10.5:
        print("ERROR: Profile này cần GPU xấp xỉ RTX 3060 12GB trở lên với sequential CPU offload.")
        return 1
    if not bf16:
        print("ERROR: Checkpoint Flash-Pro ở nhánh này dùng BF16; GPU hiện tại không báo hỗ trợ BF16.")
        return 1
    if free_bytes < 8 * (1024 ** 3):
        print("WARNING: VRAM trống dưới 8 GiB; đóng ứng dụng dùng GPU trước khi render.")
    print("Inference policy: sequential CPU offload; không gọi pipeline.to(cuda) sau khi gắn hook.")
    print("Probe chỉ import/check CUDA, chưa nạp checkpoint hay render.")
    return 0


def load_flash_checkpoint_header(checkpoint: Path) -> Dict[str, Tuple[int, ...]]:
    """Read only Safetensors header metadata to verify model parameter coverage."""
    from safetensors import safe_open

    with safe_open(str(checkpoint), framework="pt", device="cpu") as file:
        return {name: tuple(file.get_slice(name).get_shape()) for name in file.keys()}


def validate_parameter_coverage(model: Any, checkpoint_shapes: Mapping[str, Sequence[int]]) -> None:
    missing: List[str] = []
    shape_mismatch: List[str] = []
    for name, parameter in model.named_parameters():
        expected_shape = tuple(int(part) for part in parameter.shape)
        checkpoint_shape = checkpoint_shapes.get(name)
        if checkpoint_shape is None:
            missing.append(name)
        elif tuple(checkpoint_shape) != expected_shape:
            shape_mismatch.append("{}: model={} checkpoint={}".format(name, expected_shape, tuple(checkpoint_shape)))
        if parameter.device.type == "meta":
            missing.append(name + " (meta tensor remains)")
    if missing or shape_mismatch:
        details = []
        if missing:
            details.append("missing learned parameters: " + ", ".join(missing[:12]))
        if shape_mismatch:
            details.append("shape mismatch: " + "; ".join(shape_mismatch[:12]))
        raise RuntimeError("Flash checkpoint coverage validation failed; refusing random/incompatible weights. " + " | ".join(details))


def _load_models(echo_root: Path, model_root: Path, device: Any) -> Tuple[Any, Any, Any, Any]:
    """Load components in RAM-conscious order, keeping each component on CPU before offload hooks."""
    import torch
    from omegaconf import OmegaConf
    from transformers import AutoTokenizer, Wav2Vec2FeatureExtractor
    from src.fm_solvers_unipc import FlowUniPCMultistepScheduler
    from src.pipeline_wan_fun_inpaint_audio_2512 import WanFunInpaintAudioPipeline
    from src.wan_image_encoder import CLIPModel
    from src.wan_text_encoder import WanT5EncoderModel
    from src.wan_transformer3d_audio_2512 import WanTransformerAudioMask3DModel
    from src.wan_vae import AutoencoderKLWan
    from src.wav2vec2 import Wav2Vec2Model

    config = OmegaConf.load(str(echo_root / "config" / "config.yaml"))
    weight_dtype = torch.bfloat16
    base_dir = model_root / "Wan2.1-Fun-V1.1-1.3B-InP"
    flash_dir = model_root / "echomimicv3-flash-pro"
    wav2vec_dir = model_root / "chinese-wav2vec2-base"
    print("Loading CLIP image encoder first to keep CPU peak below loading T5 first...")
    clip_image_encoder = CLIPModel.from_pretrained(str(base_dir / config.image_encoder_kwargs.image_encoder_subpath)).to(dtype=weight_dtype).eval()
    gc.collect()

    print("Loading VAE...")
    vae_kwargs = OmegaConf.to_container(config.vae_kwargs, resolve=True)
    vae_path = base_dir / str(config.vae_kwargs.vae_subpath)
    vae = AutoencoderKLWan.from_pretrained(str(vae_path), additional_kwargs=vae_kwargs).to(dtype=weight_dtype).eval()
    gc.collect()

    print("Loading Flash-Pro transformer directly (no base transformer checkpoint)...")
    flash_checkpoint = flash_dir / "diffusion_pytorch_model.safetensors"
    checkpoint_shapes = load_flash_checkpoint_header(flash_checkpoint)
    transformer_kwargs = OmegaConf.to_container(config.transformer_additional_kwargs, resolve=True)
    transformer = WanTransformerAudioMask3DModel.from_pretrained(
        str(flash_dir),
        transformer_additional_kwargs=transformer_kwargs,
        low_cpu_mem_usage=True,
        torch_dtype=weight_dtype,
    ).to(dtype=weight_dtype).eval()
    validate_parameter_coverage(transformer, checkpoint_shapes)
    del checkpoint_shapes
    gc.collect()

    print("Loading tokenizer and T5 text encoder after CLIP/transformer CPU weights are placed...")
    tokenizer_path = base_dir / str(config.text_encoder_kwargs.tokenizer_subpath)
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True)
    text_kwargs = OmegaConf.to_container(config.text_encoder_kwargs, resolve=True)
    text_encoder = WanT5EncoderModel.from_pretrained(
        str(base_dir / str(config.text_encoder_kwargs.text_encoder_subpath)),
        additional_kwargs=text_kwargs,
        low_cpu_mem_usage=True,
        torch_dtype=weight_dtype,
    ).to(dtype=weight_dtype).eval()
    gc.collect()

    print("Loading Wav2Vec2 speech encoder on CPU...")
    audio_encoder = Wav2Vec2Model.from_pretrained(str(wav2vec_dir), local_files_only=True).to("cpu").eval()
    audio_encoder.feature_extractor._freeze_parameters()
    audio_feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(str(wav2vec_dir), local_files_only=True)

    scheduler_kwargs = dict(OmegaConf.to_container(config.scheduler_kwargs, resolve=True))
    scheduler_kwargs["shift"] = 1
    accepted = set(__import__("inspect").signature(FlowUniPCMultistepScheduler.__init__).parameters)
    scheduler = FlowUniPCMultistepScheduler(**{key: value for key, value in scheduler_kwargs.items() if key in accepted})
    pipeline = WanFunInpaintAudioPipeline(
        transformer=transformer,
        vae=vae,
        tokenizer=tokenizer,
        text_encoder=text_encoder,
        scheduler=scheduler,
        clip_image_encoder=clip_image_encoder,
    )
    # The official CLI's parsed GPU_memory_mode does not apply offload. Install the
    # supported Diffusers hooks once, and never call pipeline.to(cuda) afterwards.
    pipeline.enable_sequential_cpu_offload(device=device)
    print("Sequential CPU offload hooks installed; TeaCache and Riflex remain disabled.")
    return pipeline, audio_encoder, audio_feature_extractor, weight_dtype


def _sync_cuda(torch: Any, device: Any) -> None:
    torch.cuda.synchronize(device)


def _gpu_memory_stats(torch: Any, device: Any) -> Dict[str, Any]:
    _sync_cuda(torch, device)
    return {
        "gpu_name": torch.cuda.get_device_name(device),
        "allocated_mb": torch.cuda.memory_allocated(device) / (1024 ** 2),
        "reserved_mb": torch.cuda.memory_reserved(device) / (1024 ** 2),
        "peak_allocated_mb": torch.cuda.max_memory_allocated(device) / (1024 ** 2),
        "peak_reserved_mb": torch.cuda.max_memory_reserved(device) / (1024 ** 2),
    }


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_audio_embeddings(audio_path: Path, frames: int, audio_feature_extractor: Any, audio_encoder: Any, torch: Any, weight_dtype: Any, device: Any) -> Any:
    import librosa
    import numpy as np
    import pyloudnorm as pyln
    from einops import rearrange

    audio, sample_rate = librosa.load(str(audio_path), sr=16000, mono=True)
    if audio.size == 0 or not np.isfinite(audio).all():
        raise ValueError("Audio đã trim rỗng hoặc có NaN/Inf.")
    meter = pyln.Meter(sample_rate)
    loudness = meter.integrated_loudness(audio)
    if math.isfinite(loudness) and abs(loudness) <= 100:
        audio = pyln.normalize.loudness(audio, loudness, -23.0)
    audio = audio[: int(frames / 25 * sample_rate)]
    if audio.size < int((frames - 1) / 25 * sample_rate):
        raise ValueError("Wave sau trim ngắn hơn frame count cần cho conditioning.")
    extracted = np.squeeze(audio_feature_extractor(audio, sampling_rate=sample_rate).input_values)
    audio_values = torch.from_numpy(extracted).float().unsqueeze(0)
    with torch.no_grad():
        output = audio_encoder(audio_values, seq_len=frames, output_hidden_states=True)
    hidden_states = output.hidden_states
    if hidden_states is None or len(hidden_states) < 2:
        raise RuntimeError("Wav2Vec2 không trả hidden states cần thiết.")
    audio_features = torch.stack(hidden_states[1:], dim=1).squeeze(0)
    audio_features = rearrange(audio_features, "b s d -> s b d").cpu().detach()
    audio_embeds = audio_features.to(device=device, dtype=weight_dtype)
    indices = (torch.arange(5) - 2)
    center_indices = torch.arange(0, frames).unsqueeze(1) + indices.unsqueeze(0)
    center_indices = torch.clamp(center_indices, min=0, max=audio_embeds.shape[0] - 1)
    return audio_embeds[center_indices].unsqueeze(0)


def _input_tensors(image_path: Path, frames: int, torch: Any) -> Tuple[Any, Any, Any]:
    import numpy as np
    from PIL import Image

    with Image.open(str(image_path)) as source:
        image = source.convert("RGB")
    pixels = np.asarray(image, dtype=np.uint8)
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError("Padded source image must be RGB.")
    video = torch.from_numpy(pixels.copy()).permute(2, 0, 1).unsqueeze(1).unsqueeze(0)
    video = torch.tile(video, (1, 1, frames, 1, 1)).float().div_(255.0)
    mask = torch.zeros((1, 1, frames, pixels.shape[0], pixels.shape[1]), dtype=torch.uint8)
    mask[:, :, 1:, :, :] = 255
    return video, mask, image


def _encode_silent_video(frames: Any, destination: Path, fps: int, ffmpeg: str = "ffmpeg") -> float:
    import numpy as np
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError("Video frame array must be [F,H,W,3].")
    _, height, width, _ = frames.shape
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s:v", "{}x{}".format(width, height), "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
        "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
    ]
    started = time.perf_counter()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stdin is not None
    assert process.stderr is not None
    try:
        for frame in frames:
            process.stdin.write(np.ascontiguousarray(frame).tobytes())
        process.stdin.close()
        error_bytes = process.stderr.read()
        code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        temporary.unlink(missing_ok=True)
        raise
    if code != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg silent-base encode failed ({}): {}".format(code, error_bytes.decode("utf-8", errors="replace").strip()))
    os.replace(str(temporary), str(destination))
    return time.perf_counter() - started


def _mux_audio(silent_path: Path, audio_path: Path, destination: Path, ffmpeg: str = "ffmpeg") -> float:
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent_path), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", str(temporary),
    ]
    started = time.perf_counter()
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg voice-preview mux failed: {}".format(result.stderr.decode("utf-8", errors="replace").strip()))
    os.replace(str(temporary), str(destination))
    return time.perf_counter() - started


def execute_plan(plan_path: Path) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    echo_root = Path(plan["echo_root"]).resolve()
    model_root = Path(plan["model_root"]).resolve()
    output_dir = Path(plan["outputs_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    profile = plan["profile"]
    frames = int(plan["frames"])
    ffmpeg = str(plan.get("ffmpeg", "ffmpeg"))
    if frames < 5 or (frames - 1) % 4 != 0:
        raise ValueError("Frame count phải có dạng 4n+1 và ít nhất 5.")
    if len(plan["inputs"]) != (2 if plan.get("benchmark") else 1):
        raise ValueError("Số input không đúng với chế độ benchmark/run.")
    torch = None
    try:
        modules = _import_runtime_modules()
        np = modules["numpy"]
        torch = modules["torch"]
        version_errors = _runtime_version_errors(modules)
        if version_errors:
            raise RuntimeError("GPU worker runtime lệch dependency pin: " + "; ".join(version_errors))
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA không khả dụng; từ chối chạy CPU fallback.")
        if not torch.cuda.is_bf16_supported():
            raise RuntimeError("GPU không hỗ trợ BF16 cho checkpoint Flash-Pro.")
        device = torch.device("cuda:0")
        torch.cuda.reset_peak_memory_stats(device)
        _sync_cuda(torch, device)
        model_started = time.perf_counter()
        pipeline, audio_encoder, audio_feature_extractor, weight_dtype = _load_models(echo_root, model_root, device)
        _sync_cuda(torch, device)
        model_load_seconds = time.perf_counter() - model_started
        torch.cuda.reset_peak_memory_stats(device)

        audio_started = time.perf_counter()
        audio_embeds = _prepare_audio_embeddings(
            Path(plan["inputs"][0]["audio"]), frames, audio_feature_extractor, audio_encoder, torch, weight_dtype, device
        )
        _sync_cuda(torch, device)
        audio_seconds = time.perf_counter() - audio_started
        del audio_encoder, audio_feature_extractor
        gc.collect()

        items = []
        for index, item in enumerate(plan["inputs"], 1):
            # This branch intentionally benchmarks two images against the same audio.
            if index > 1 and _file_sha256(Path(item["audio"])) != _file_sha256(Path(plan["inputs"][0]["audio"])):
                raise ValueError("Một batch benchmark phải dùng cùng audio conditioning.")
            item_started = time.perf_counter()
            video, mask, clip_image = _input_tensors(Path(item["image"]), frames, torch)
            output_path = output_dir / ("motion_base_{}.mp4".format(index))
            preview_path = output_dir / ("voice_preview_{}.mp4".format(index))
            if output_path.exists() or preview_path.exists():
                raise FileExistsError("Refusing to overwrite a stale worker output.")
            torch.cuda.reset_peak_memory_stats(device)
            generation_started = time.perf_counter()
            generator = torch.Generator(device=device).manual_seed(int(profile["seed"]))

            def report_step_end(pipe: Any, step_index: int, timestep: Any, callback_kwargs: Dict[str, Any]) -> Dict[str, Any]:
                print("  Render {}/{}".format(step_index + 1, int(profile["steps"])), flush=True)
                return callback_kwargs

            with torch.no_grad():
                generated = pipeline(
                    prompt=plan["prompt"],
                    negative_prompt=plan["negative_prompt"],
                    audio_embeds=audio_embeds,
                    audio_scale=1.0,
                    ip_mask=None,
                    use_un_ip_mask=False,
                    height=int(profile["height"]),
                    width=int(profile["width"]),
                    video=video,
                    mask_video=mask,
                    num_frames=frames,
                    num_inference_steps=int(profile["steps"]),
                    guidance_scale=float(profile["guidance_scale"]),
                    audio_guidance_scale=float(profile["audio_guidance_scale"]),
                    neg_scale=1.0,
                    neg_steps=0,
                    use_dynamic_cfg=False,
                    use_dynamic_acfg=False,
                    generator=generator,
                    output_type="numpy",
                    return_dict=True,
                    callback_on_step_end=report_step_end,
                    clip_image=clip_image,
                    max_sequence_length=512,
                    cfg_skip_ratio=0.0,
                    shift=float(profile["shift"]),
                ).videos
            _sync_cuda(torch, device)
            generation_seconds = time.perf_counter() - generation_started
            if not isinstance(generated, np.ndarray):
                generated = np.asarray(generated)
            expected_shape = (1, 3, frames, int(profile["height"]), int(profile["width"]))
            if tuple(generated.shape) != expected_shape:
                raise RuntimeError("Model output shape {} differs from expected {}.".format(tuple(generated.shape), expected_shape))
            if not np.isfinite(generated).all():
                raise RuntimeError("Model output contains NaN/Inf.")
            frames_rgb = np.transpose(generated[0], (1, 2, 3, 0))
            frames_rgb = np.clip(frames_rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
            encode_seconds = _encode_silent_video(frames_rgb, output_path, int(profile["fps"]), ffmpeg)
            mux_seconds = _mux_audio(output_path, Path(item["audio"]), preview_path, ffmpeg)
            timing = {
                "shared_model_load_seconds": model_load_seconds,
                "shared_audio_conditioning_seconds": audio_seconds,
                "pipeline_call_seconds": generation_seconds,
                "item_wall_seconds": time.perf_counter() - item_started,
                "silent_encode_seconds": encode_seconds,
                "audio_mux_seconds": mux_seconds,
                "cuda_memory": _gpu_memory_stats(torch, device),
            }
            items.append({
                "motion_base": str(output_path.resolve()),
                "voice_preview": str(preview_path.resolve()),
                "timing": timing,
            })
            del generated, frames_rgb, video, mask, clip_image, generator
            gc.collect()
            torch.cuda.empty_cache()

        result = {"status": "complete", "items": items, "profile": profile, "frame_count": frames}
        (output_dir / "backend_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("Backend completed {} output(s).".format(len(items)))
        return 0
    except Exception:
        traceback.print_exc()
        return 1


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EchoMimic V3 Flash child worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe")
    probe.add_argument("--echo-root", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    return parser


def main(argv: Sequence[str] = None) -> int:
    args = make_parser().parse_args(argv)
    if args.command == "probe":
        return runtime_probe(args.echo_root)
    return execute_plan(args.plan)


if __name__ == "__main__":
    raise SystemExit(main())
