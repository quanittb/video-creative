from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from runners.apply_conversational_motion import (
    _apply_masked_body_warp,
    _apply_silhouette_body_warp,
    _prepare_body_motion_mask,
    _prepare_body_silhouette_mask,
    apply_conversational_motion_to_video,
)


def _body_mask(height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    polygon = np.array([[25, 145], [85, 140], [175, 140], [235, 145], [255, 235], [10, 235]])
    cv2.fillPoly(mask, [polygon], 255)
    return mask


class ConversationalMotionTests(unittest.TestCase):
    def test_feathered_mask_never_leaks_outside_calibrated_pixels(self) -> None:
        mask = _body_mask(240, 270)
        roi = (70, 35, 130, 95)

        prepared = _prepare_body_motion_mask(mask, roi)

        self.assertEqual(prepared.dtype, np.float32)
        self.assertTrue(np.all(prepared[mask == 0] == 0.0))
        x, y, width, height = roi
        self.assertTrue(np.all(prepared[y:y + height, x:x + width] == 0.0))
        self.assertEqual(float(prepared.max()), 1.0)

    def test_body_warp_preserves_unsupported_pixels_and_zero_shift_is_identity(self) -> None:
        height, width = 240, 270
        mask = _body_mask(height, width)
        body_mask = _prepare_body_motion_mask(mask, (70, 35, 130, 95))
        frame = np.random.default_rng(17).integers(0, 256, (height, width, 3), dtype=np.uint8)
        grid_y, grid_x = np.mgrid[0:height, 0:width].astype(np.float32)
        left_weight = np.clip((135.0 - grid_x) / 135.0, 0.0, 1.0)
        right_weight = np.clip((grid_x - 135.0) / 135.0, 0.0, 1.0)

        identity = _apply_masked_body_warp(
            frame, body_mask, grid_x, grid_y, left_weight, right_weight, 0.0, 0.0
        )
        shifted = _apply_masked_body_warp(
            frame, body_mask, grid_x, grid_y, left_weight, right_weight, 2.0, -2.0
        )

        self.assertTrue(np.array_equal(identity, frame))
        self.assertTrue(np.array_equal(shifted[body_mask == 0.0], frame[body_mask == 0.0]))
        self.assertTrue(np.any(shifted[body_mask > 0.0] != frame[body_mask > 0.0]))

    def test_silhouette_warp_moves_outline_restores_background_and_protects_face(self) -> None:
        height, width = 240, 270
        mask = _body_mask(height, width)
        body_alpha = _prepare_body_silhouette_mask(mask, (70, 35, 130, 95))
        self.assertEqual(body_alpha.dtype, np.float32)
        self.assertTrue(np.all(body_alpha[mask == 0] == 0.0))
        self.assertTrue(np.all(body_alpha[35:130, 70:200] == 0.0))

        frame = np.full((height, width, 3), (10, 30, 50), dtype=np.uint8)
        frame[mask > 0] = (90, 100, 110)
        background_plate = cv2.inpaint(frame, mask, 7, cv2.INPAINT_TELEA)
        grid_y, grid_x = np.mgrid[0:height, 0:width].astype(np.float32)
        weights = np.ones((height, width), dtype=np.float32)
        protected_region = (70, 35, 200, 130)

        identity = _apply_silhouette_body_warp(
            frame, body_alpha, grid_x, grid_y, weights, weights,
            0.0, 0.0, 4.0, 0.0, protected_region=protected_region,
            background_plate=background_plate,
        )
        shifted = _apply_silhouette_body_warp(
            frame, body_alpha, grid_x, grid_y, weights, weights,
            20.0, 20.0, 4.0, 0.0, onset_height=1.0,
            protected_region=protected_region, background_plate=background_plate,
        )
        fractional = _apply_silhouette_body_warp(
            frame, body_alpha, grid_x, grid_y, weights, weights,
            0.25, 0.25, 4.0, 0.0, onset_height=1.0,
            protected_region=protected_region, background_plate=background_plate,
        )

        self.assertTrue(np.array_equal(identity, frame))
        self.assertTrue(np.array_equal(shifted[35:130, 70:200], frame[35:130, 70:200]))
        self.assertTrue(np.array_equal(shifted[:30, :30], frame[:30, :30]))
        # The old outline is vacated at y=140; background color must replace the coat pixel.
        self.assertTrue(np.all(np.abs(shifted[140, 135].astype(int) - (10, 30, 50)) <= 3))
        # The foreground reappears four pixels lower, proving the displacement cap.
        self.assertTrue(np.array_equal(shifted[144, 135], np.array((90, 100, 110), dtype=np.uint8)))
        # Subpixel uncovering must blend against the inferred background, not retain an old coat edge.
        self.assertTrue(np.all(fractional[140, 135] < np.array((90, 100, 110), dtype=np.uint8)))

    def test_coupled_mode_rejects_mask_overlapping_face_roi(self) -> None:
        mask = np.full((180, 200), 255, dtype=np.uint8)

        with self.assertRaisesRegex(ValueError, "chồng lên face ROI"):
            _prepare_body_motion_mask(mask, (40, 30, 100, 100))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Cần FFmpeg để kiểm thử pipeline streaming")
    def test_coupled_video_path_streams_frames_and_preserves_audio_timing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vcs_motion_test_") as temporary_dir:
            self._exercise_coupled_video_path(Path(temporary_dir))

    def _exercise_coupled_video_path(self, tmp_path: Path) -> None:
        height, width, fps, frame_count = 240, 270, 25, 18
        input_video = tmp_path / "input.mp4"
        input_audio = tmp_path / "voice.wav"
        output_video = tmp_path / "coupled output.mp4"
        body_mask_path = tmp_path / "body mask.png"

        self.assertTrue(cv2.imwrite(str(body_mask_path), _body_mask(height, width)))
        writer = cv2.VideoWriter(
            str(input_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
        )
        self.assertTrue(writer.isOpened())
        rng = np.random.default_rng(123)
        face_texture = rng.integers(50, 210, (55, 80, 3), dtype=np.uint8)
        base = np.full((height, width, 3), (50, 80, 110), dtype=np.uint8)
        for frame_index in range(frame_count):
            frame = base.copy()
            cv2.fillPoly(frame, [np.array([[25, 145], [85, 140], [175, 140], [235, 145], [255, 235], [10, 235]])], (75, 110, 145))
            face_x = 70 + frame_index // 4
            frame[45:100, face_x:face_x + 80] = face_texture
            writer.write(frame)
        writer.release()

        audio = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                f"sine=frequency=220:duration={frame_count / fps:.3f}",
                "-c:a", "pcm_s16le", str(input_audio),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(audio.returncode, 0, audio.stderr)

        self.assertTrue(apply_conversational_motion_to_video(
            str(input_video),
            str(output_video),
            audio_path=str(input_audio),
            mode="coupled",
            body_mask_path=str(body_mask_path),
            face_roi=(70, 35, 130, 95),
            max_displacement_px=2.5,
        ))
        self.assertTrue(output_video.is_file() and output_video.stat().st_size > 1000)

        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_type,width,height,r_frame_rate,duration",
                "-of", "json", str(output_video),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
        audio_stream = next(stream for stream in streams if stream["codec_type"] == "audio")
        self.assertEqual((video_stream["width"], video_stream["height"]), (width, height))
        self.assertEqual(video_stream["r_frame_rate"], f"{fps}/1")
        self.assertLessEqual(
            abs(float(video_stream["duration"]) - float(audio_stream["duration"])),
            1.0 / fps + 0.02,
        )
