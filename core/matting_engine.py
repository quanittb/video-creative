"""Matting Engine: High-precision portrait background removal (BiRefNet / RMBG / Rembg)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
from PIL import Image


class MattingEngine:
    """Removes portrait background with edge/hair-strand precision to produce alpha masks."""

    def __init__(self, model_name: str = "birefnet", device: str = "auto"):
        self.model_name = model_name
        self.device = device
        self._session = None

    def remove_background(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        output_path: Optional[Union[str, Path]] = None,
    ) -> Image.Image:
        """Process a single image and return a PIL Image with transparent alpha channel."""
        # Convert input to PIL Image
        if isinstance(image_input, (str, Path)):
            pil_img = Image.open(str(image_input)).convert("RGBA")
        elif isinstance(image_input, np.ndarray):
            if image_input.shape[2] == 3:
                pil_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB)).convert("RGBA")
            else:
                pil_img = Image.fromarray(image_input)
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGBA")
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        # Attempt rembg / birefnet removal
        try:
            from rembg import remove, new_session
            if self._session is None:
                # Use birefnet-general or isnet-general if available, else standard
                try:
                    self._session = new_session("birefnet-portrait")
                except Exception:
                    self._session = new_session("isnet-general-use")
            result = remove(pil_img, session=self._session)
        except ImportError:
            # Fallback placeholder alpha (simple threshold / no-op mask if rembg is not yet installed)
            print("[MattingEngine] rembg not installed. Generating dummy alpha mask for testing.")
            result = pil_img.copy()

        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            result.save(str(out_p), format="PNG")

        return result
