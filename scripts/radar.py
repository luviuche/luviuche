"""Draw a radar chart from a JSON file of labelled 0-100 values.

Deliberately hand-authored data: pulling these from GitHub language bytes makes
coursework and one-off assignments outweigh the work that actually represents
someone, so the numbers live in assets/*.json and a human edits them.

    python scripts/radar.py --data assets/skills.json -o assets/radar
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from theme import FONT_SANS, Palette, esc, fmt, load_theme, write_pair

# Wider than tall: the side labels need the horizontal room, and wrapping
# early keeps the longest of them from running off the canvas.
WIDTH, HEIGHT = 470, 440
CX, CY = WIDTH / 2, HEIGHT / 2 + 8
RADIUS = 124
RINGS = 4
LABEL_GAP = 22
WRAP_AT = 12


def point(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def wrap(label: str) -> list[str]:
    """Break a long label onto two lines at the nearest space to the middle."""
    if len(label) <= WRAP_AT or " " not in label:
        return [label]
    mid = len(label) / 2
    split = min(
        (i for i, ch in enumerate(label) if ch == " "), key=lambda i: abs(i - mid)
    )
    return [label[:split], label[split + 1 :]]


def render(data: dict, pal: Palette, show_values: bool) -> str:
    axes = data["axes"]
    n = len(axes)
    angles = [(-math.pi / 2) + i * (2 * math.pi / n) for i in range(n)]

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" '
        f'height="{HEIGHT}" role="img" aria-label="{esc(data.get("title", "radar"))}" '
        f'font-family="{FONT_SANS}">',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" '
        f'fill="{pal.bg}" stroke="{pal.border}"/>',
    ]

    if title := data.get("title"):
        out.append(
            f'<text x="{CX}" y="30" text-anchor="middle" font-size="13.5" font-weight="700" '
            f'fill="{pal.accent}" letter-spacing="1.4">{esc(title.upper())}</text>'
        )

    # Concentric rings, outermost solid so the chart has a clear boundary.
    for ring in range(1, RINGS + 1):
        r = RADIUS * ring / RINGS
        pts = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in (point(CX, CY, r, a) for a in angles))
        width = "1.2" if ring == RINGS else "1"
        out.append(
            f'<polygon points="{pts}" fill="none" stroke="{pal.grid}" stroke-width="{width}"/>'
        )

    for a in angles:
        x, y = point(CX, CY, RADIUS, a)
        out.append(
            f'<line x1="{CX}" y1="{CY}" x2="{fmt(x)}" y2="{fmt(y)}" stroke="{pal.grid}" stroke-width="1"/>'
        )

    # The value polygon.
    vertices = [
        point(CX, CY, RADIUS * max(0.0, min(100.0, float(ax["value"]))) / 100, a)
        for ax, a in zip(axes, angles)
    ]
    pts = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in vertices)
    out.append(
        f'<polygon points="{pts}" fill="{pal.accent}" fill-opacity="0.18" '
        f'stroke="{pal.accent}" stroke-width="2.2" stroke-linejoin="round"/>'
    )
    for x, y in vertices:
        out.append(
            f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="3.4" fill="{pal.bg}" '
            f'stroke="{pal.accent}" stroke-width="2.2"/>'
        )

    # Labels, pushed just outside the outer ring.
    for ax, angle, (vx, vy) in zip(axes, angles, vertices):
        lx, ly = point(CX, CY, RADIUS + LABEL_GAP, angle)
        cos = math.cos(angle)
        anchor = "middle" if abs(cos) < 0.25 else ("start" if cos > 0 else "end")
        lines = wrap(str(ax["label"]))
        # Nudge up so a two-line label stays centred on its spoke.
        ly -= (len(lines) - 1) * 6.5
        for j, chunk in enumerate(lines):
            out.append(
                f'<text x="{fmt(lx)}" y="{fmt(ly + j * 13.5)}" text-anchor="{anchor}" '
                f'font-size="11.5" font-weight="600" fill="{pal.text}">{esc(chunk)}</text>'
            )
        if show_values:
            ox, oy = point(CX, CY, RADIUS * float(ax["value"]) / 100 - 14, angle)
            out.append(
                f'<text x="{fmt(ox)}" y="{fmt(oy + 4)}" text-anchor="middle" font-size="10" '
                f'font-weight="700" fill="{pal.muted}">{int(ax["value"])}</text>'
            )

    out.append("</svg>")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    ap.add_argument("--values", action="store_true", help="print each score on its spoke")
    args = ap.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    svgs = {name: render(data, pal, args.values) for name, pal in load_theme().items()}
    for path in write_pair(args.out, svgs):
        print(f"{path}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
