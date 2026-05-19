"""Convert install/assets/er_force_icon.png to .ico with standard Windows sizes."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.stderr.write(
        "Pillow is required. Install it with:\n"
        "  pip install pillow\n"
    )
    raise SystemExit(1)


HERE = Path(__file__).resolve().parent
PNG = HERE / "assets" / "er_force_icon.png"
ICO = HERE / "assets" / "er_force_icon.ico"

ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    if not PNG.is_file():
        sys.stderr.write(f"Missing source PNG: {PNG}\n")
        return 1

    img = Image.open(PNG).convert("RGBA")
    img.save(ICO, format="ICO", sizes=ICON_SIZES)
    try:
        print(f"Wrote {ICO.name} ({ICO.stat().st_size} bytes)")
    except UnicodeEncodeError:
        print(f"Wrote {ICO.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
