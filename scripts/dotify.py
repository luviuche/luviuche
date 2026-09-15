"""Turn an image into a dot-matrix intensity grid.

The banner draws one <circle> per cell, sized by that cell's intensity, so this
module only has to answer one question: how bright is each cell, 0..1.

Themes are NOT baked in here. A single luminance grid is cached per source and
the banner inverts it for the light theme, which keeps one .npy serving both.

    python scripts/dotify.py photo.jpg -o assets/source/cache/portrait.npy
    python scripts/dotify.py --monogram LV -o assets/source/cache/mono.npy
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

# A tall-ish grid: the banner's dot panel is roughly square but portraits read
# better with a little more vertical resolution.
DEFAULT_COLS = 42
DEFAULT_ROWS = 46

FONT_CANDIDATES = [
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _luminance(img: Image.Image) -> Image.Image:
    """Flatten to greyscale, honouring alpha so logos keep their silhouette."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        grey = ImageOps.grayscale(img.convert("RGB"))
        alpha = img.getchannel("A")
        # Transparent pixels must read as empty, not as black ink.
        return Image.composite(grey, Image.new("L", img.size, 0), alpha)
    return ImageOps.grayscale(img.convert("RGB"))


def _fit_square(img: Image.Image) -> Image.Image:
    """Centre-crop to a square so the grid is never stretched."""
    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    return img.crop((left, top, left + side, top + side))


def dotify(
    img: Image.Image,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    gamma: float = 1.0,
    autocontrast: bool = True,
    floor: float = 0.0,
) -> np.ndarray:
    """Return a rows x cols float array in 0..1, where 1 is a full-size dot."""
    grey = _luminance(_fit_square(img))
    if autocontrast:
        # Clip a little off both tails: photos out of a phone are rarely
        # contrasty enough to survive being reduced to ~2000 dots.
        grey = ImageOps.autocontrast(grey, cutoff=2)
    small = grey.resize((cols, rows), Image.Resampling.LANCZOS)

    data = np.asarray(small, dtype=np.float32) / 255.0
    if gamma != 1.0:
        data = np.power(data, gamma)
    if floor > 0:
        # Lift the dark end so the silhouette keeps a faint dot field instead
        # of dropping to nothing.
        data = floor + (1.0 - floor) * data
    return np.clip(data, 0.0, 1.0)


def monogram(
    text: str,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    **kwargs,
) -> np.ndarray:
    """Render initials as a dot grid - the stand-in until a photo exists."""
    size = 512
    canvas = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(canvas)

    # Start oversized and shrink until the glyphs fit the canvas, so the
    # monogram fills the dot panel instead of floating in the middle of it.
    font = _load_font(size)
    for pt in range(size, 24, -6):
        font = _load_font(pt)
        box = draw.textbbox((0, 0), text, font=font)
        if (box[2] - box[0]) <= size * 0.84 and (box[3] - box[1]) <= size * 0.74:
            break

    draw.text((size * 0.1, size * 0.1), text, fill=255, font=font)

    # Recentre on the actual ink rather than the font metrics: bearings and
    # descender space would otherwise push the glyphs off-centre in the grid.
    ink = canvas.getbbox()
    if ink:
        glyphs = canvas.crop(ink)
        side = int(max(glyphs.size) / 0.84)
        canvas = Image.new("L", (side, side), 0)
        canvas.paste(glyphs, ((side - glyphs.width) // 2, (side - glyphs.height) // 2))

    return dotify(canvas, cols, rows, autocontrast=False, **kwargs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", help="source image (omit with --monogram)")
    ap.add_argument("-o", "--out", required=True, type=Path)
    ap.add_argument("--monogram", help="render these initials instead of an image")
    ap.add_argument("--cols", type=int, default=DEFAULT_COLS)
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--floor", type=float, default=0.0)
    args = ap.parse_args()

    if args.monogram:
        grid = monogram(args.monogram, args.cols, args.rows, gamma=args.gamma, floor=args.floor)
    elif args.image:
        grid = dotify(
            Image.open(args.image), args.cols, args.rows, gamma=args.gamma, floor=args.floor
        )
    else:
        ap.error("pass an image path or --monogram")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, grid.astype(np.float32))
    ink = float(grid.mean())
    print(f"{args.out}  {grid.shape[1]}x{grid.shape[0]} cells  mean ink {ink:.3f}")


if __name__ == "__main__":
    main()
