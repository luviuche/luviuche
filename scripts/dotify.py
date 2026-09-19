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


def _fit_square(
    img: Image.Image,
    crop: tuple[float, float, float, float] | None = None,
    square: bool = True,
) -> Image.Image:
    """Crop the source, squaring it up unless told otherwise.

    `crop` is (left, top, right, bottom) as fractions of the image. A portrait
    almost always needs one: a centre crop of a phone photo keeps half a room
    and throws away the face, and at ~1,900 dots there is no resolution to
    spare on a wall.
    """
    if crop:
        box = (
            int(crop[0] * img.width),
            int(crop[1] * img.height),
            int(crop[2] * img.width),
            int(crop[3] * img.height),
        )
        img = img.crop(box)
    if not square:
        # The caller promises the crop's aspect matches cols:rows. Useful for
        # a head-and-shoulders portrait, which is taller than it is wide and
        # would lose the hair or the chin to a square.
        return img
    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    return img.crop((left, top, left + side, top + side))


def _vignette(shape: tuple[int, int], start: float) -> np.ndarray:
    """Smooth elliptical falloff: 1 in the middle, 0 at the corners.

    A portrait photographed indoors carries a wall with it, and a bright wall
    becomes a slab of ink above the head. Fading the edges removes it without
    any segmentation model, and reads as a spotlight rather than a mistake.
    """
    rows, cols = shape
    r = (np.arange(rows)[:, None] - (rows - 1) / 2) / max((rows - 1) / 2, 1)
    c = (np.arange(cols)[None, :] - (cols - 1) / 2) / max((cols - 1) / 2, 1)
    d = np.sqrt(r**2 + c**2) / np.sqrt(2)
    t = np.clip((d - start) / max(1.0 - start, 1e-6), 0.0, 1.0)
    return 1.0 - (t * t * (3.0 - 2.0 * t))


def dotify(
    img: Image.Image,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    gamma: float = 1.0,
    autocontrast: bool = True,
    floor: float = 0.0,
    invert: bool = False,
    crop: tuple[float, float, float, float] | None = None,
    square: bool = True,
    vignette: float = 0.0,
) -> np.ndarray:
    """Return a rows x cols float array of INK, 0..1, where 1 is a full dot.

    Ink, not brightness. Whether ink means light or dark pixels depends on the
    photo: a face lit against a dark room is bright ink, a dark-haired subject
    against a white wall is the opposite. Pass `invert` for the latter. The
    banner then draws the same ink in both themes - light dots on a dark
    background, dark dots on a light one - and the portrait reads correctly
    either way.
    """
    grey = _luminance(_fit_square(img, crop, square))
    if autocontrast:
        # Clip a little off both tails: photos out of a phone are rarely
        # contrasty enough to survive being reduced to ~2000 dots.
        grey = ImageOps.autocontrast(grey, cutoff=2)
    small = grey.resize((cols, rows), Image.Resampling.LANCZOS)

    data = np.asarray(small, dtype=np.float32) / 255.0
    if invert:
        data = 1.0 - data
    if gamma != 1.0:
        data = np.power(data, gamma)
    if vignette > 0:
        data = data * _vignette(data.shape, vignette)
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
    ap.add_argument(
        "--invert",
        action="store_true",
        help="ink where the image is DARK - use it when the subject is darker "
        "than the background, which is most indoor portraits",
    )
    ap.add_argument(
        "--vignette",
        type=float,
        default=0.0,
        help="fade ink toward the edges; the value is where the falloff starts "
        "(0.45 is a good portrait, 0 disables it)",
    )
    ap.add_argument(
        "--no-square",
        action="store_true",
        help="keep the crop's own aspect instead of squaring it - match it to --cols/--rows",
    )
    ap.add_argument(
        "--crop",
        help="left,top,right,bottom as fractions of the image, e.g. 0.12,0.2,0.84,0.74",
    )
    args = ap.parse_args()

    crop = tuple(float(v) for v in args.crop.split(",")) if args.crop else None
    if crop and len(crop) != 4:
        ap.error("--crop needs four comma-separated fractions")

    if args.monogram:
        grid = monogram(args.monogram, args.cols, args.rows, gamma=args.gamma, floor=args.floor)
    elif args.image:
        grid = dotify(
            Image.open(args.image),
            args.cols,
            args.rows,
            gamma=args.gamma,
            floor=args.floor,
            invert=args.invert,
            crop=crop,
            square=not args.no_square,
            vignette=args.vignette,
        )
    else:
        ap.error("pass an image path or --monogram")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, grid.astype(np.float32))
    ink = float(grid.mean())
    print(f"{args.out}  {grid.shape[1]}x{grid.shape[0]} cells  mean ink {ink:.3f}")


if __name__ == "__main__":
    main()
