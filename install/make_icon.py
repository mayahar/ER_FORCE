"""Convert install/assets/err_force_icon.png to .ico with standard Windows sizes."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Pillow is required: pip install pillow") from exc

HERE = Path(__file__).resolve().parent
PNG = HERE / "assets" / "err_force_icon.png"
if not PNG.is_file():
    PNG = HERE / "assets" / "er_force_icon.png"
ICO = HERE / "assets" / "err_force_icon.ico"

img = Image.open(PNG).convert("RGBA")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(ICO, format="ICO", sizes=sizes)
print(f"Wrote {ICO}")
