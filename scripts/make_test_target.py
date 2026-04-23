"""Generate a simple 512x512 test target so you can launch the agent immediately."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "targets" / "test_landscape.png"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (512, 512), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 512, 320], fill="#9ec9f0")
    d.rectangle([0, 320, 512, 512], fill="#d4b886")
    d.ellipse([380, 60, 470, 150], fill="#ffcc33")
    d.polygon([(0, 320), (120, 200), (240, 320)], fill="#6b7a6a")
    d.polygon([(200, 320), (340, 180), (480, 320)], fill="#55655a")
    d.rectangle([80, 320, 100, 380], fill="#5a3a1a")
    d.ellipse([50, 260, 130, 350], fill="#3a5a2a")
    img.save(OUT)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
