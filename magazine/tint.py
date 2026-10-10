"""
Makes a one-colour (tinted) copy of a library photo, the treatment The Weekly uses.

    python magazine/tint.py fed "#2F5BFF"

Reads  magazine/photos/color/fed.jpg
Writes magazine/photos/tinted/fed-2F5BFF.jpg   (dark tones near-black, light tones the colour)

The Daily uses the full-colour photos in magazine/photos/color/ as they are.
Needs: pip install pillow
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent


def main() -> None:
    if len(sys.argv) != 3 or not re.fullmatch(r"#[0-9A-Fa-f]{6}", sys.argv[2]):
        sys.exit(__doc__)
    key, colour = sys.argv[1], sys.argv[2].upper()
    src = ROOT / "photos" / "color" / f"{key}.jpg"
    if not src.exists():
        sys.exit(f"no such photo: {src}")
    dst = ROOT / "photos" / "tinted" / f"{key}-{colour[1:]}.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    ImageOps.colorize(Image.open(src).convert("L"), "#141311", colour).save(dst, quality=80, optimize=True)
    print(dst.relative_to(ROOT.parent))


if __name__ == "__main__":
    main()
