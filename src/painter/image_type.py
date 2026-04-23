"""Classify a reference image into a coarse "type" used for skill scoping."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


def classify(png_bytes: bytes) -> dict[str, float | str]:
    """Return {'type': str, 'mean': float, 'std': float, 'saturation': float, 'warmth': float}."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    gray = arr.mean(axis=2)
    r_mean = float(arr[..., 0].mean())
    g_mean = float(arr[..., 1].mean())
    b_mean = float(arr[..., 2].mean())

    brightness = float(gray.mean())
    contrast = float(gray.std())
    # Simple saturation proxy: max - min of channels
    sat = float((arr.max(axis=2) - arr.min(axis=2)).mean())
    warmth = r_mean - b_mean

    if contrast > 60 and brightness > 120:
        t = "high_contrast"
    elif brightness < 80:
        t = "dark"
    elif brightness > 180:
        t = "bright"
    elif sat < 30:
        t = "muted"
    else:
        t = "balanced"

    return {
        "type": t,
        "mean": brightness,
        "std": contrast,
        "saturation": sat,
        "warmth": warmth,
    }
