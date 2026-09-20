"""Download Simple Icons and rasterise them into dot-matrix source images.

Run by hand when you want a different set of icons in the banner; the result
is committed, so CI never needs network access or a rasteriser.

    python scripts/fetch_icons.py linux python openjdk
    python scripts/fetch_icons.py --list-known

Icons are drawn white on transparent. dotify reads the alpha channel, so the
fill colour only has to be bright - the banner recolours everything anyway.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "source" / "icons"
CDN = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{}.svg"

SIZE = 512
PAD = 0.12  # keeps the glyph off the panel edge

# Handy starting points; any Simple Icons slug works.
KNOWN = [
    "linux", "archlinux", "openjdk", "python", "spring", "docker",
    "git", "gnubash", "postgresql", "fastapi", "mysql", "github",
]


def rasterise(svg: Path, png: Path) -> None:
    inner = int(SIZE * (1 - 2 * PAD))
    subprocess.run(
        ["rsvg-convert", "-w", str(inner), "-h", str(inner), "-a", str(svg), "-o", str(png)],
        check=True,
    )
    # Centre the glyph on a transparent square so every icon shares one frame.
    from PIL import Image

    glyph = Image.open(png).convert("RGBA")
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(glyph, ((SIZE - glyph.width) // 2, (SIZE - glyph.height) // 2), glyph)
    canvas.save(png)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slugs", nargs="*", help="Simple Icons slugs, e.g. linux python")
    ap.add_argument("--list-known", action="store_true")
    args = ap.parse_args()

    if args.list_known:
        print("\n".join(KNOWN))
        return
    if not args.slugs:
        ap.error("name at least one slug, or pass --list-known")
    if not shutil.which("rsvg-convert"):
        ap.error("rsvg-convert not found - install librsvg (Arch: pacman -S librsvg)")

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / ".tmp.svg"
    for slug in args.slugs:
        try:
            with urllib.request.urlopen(CDN.format(slug), timeout=30) as resp:
                svg = resp.read().decode()
        except urllib.error.HTTPError as exc:
            print(f"  ! {slug}: not in Simple Icons ({exc.code})", file=sys.stderr)
            continue

        # Simple Icons ship no fill, so the path defaults to black. White makes
        # the silhouette survive the greyscale step.
        tmp.write_text(svg.replace("<svg ", '<svg fill="#ffffff" ', 1))
        png = OUT / f"{slug}.png"
        rasterise(tmp, png)
        print(f"  {png.relative_to(ROOT)}")

    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
