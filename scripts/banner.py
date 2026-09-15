"""Draw the hero banner: a terminal window that types itself, next to a
dot-matrix panel built from assets/source/cache/*.npy.

Two SVGs come out, one per theme, and the README picks between them with
<picture media="(prefers-color-scheme: ...)">.

Everything animates through SMIL, never script: GitHub serves README images
through a proxy that runs animation but blocks JavaScript.

    python scripts/banner.py --config assets/banner.json --out assets/banner
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from theme import FONT_MONO, ROOT, Palette, esc, fmt, load_theme, write_pair

W, H = 1080, 400
CHROME_H = 40

PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 44, 68, 300, 300

TEXT_X = 392
TEXT_Y0 = 98
LINE_H = 38
FONT_SIZE = 18
CHAR_W = FONT_SIZE * 0.6  # every monospace fallback in the stack is 0.6em

TYPE_SPEED = 0.042  # seconds per character
LINE_GAP = 0.22
LEAD_IN = 0.7
FADE = 0.55

PROMPT = "$ "


# --------------------------------------------------------------------------- #
# timeline
# --------------------------------------------------------------------------- #
MAX_CHARS = int((W - TEXT_X - 24) / CHAR_W)


def build_timeline(lines: list[dict], hold: float) -> tuple[list[dict], float]:
    """Assign each line a start/end second, and return the total cycle length."""
    t = LEAD_IN
    spans = []
    for line in lines:
        text = PROMPT + line["text"] if line["style"] == "cmd" else line["text"]
        if len(text) > MAX_CHARS:
            # Text is clipped, not wrapped, so an over-long line would simply
            # run off the edge of the window with no other warning.
            raise SystemExit(
                f"banner line is {len(text)} characters, the window fits {MAX_CHARS}:\n"
                f"  {text!r}\nShorten it in assets/banner.json."
            )
        dur = max(0.28, len(text) * TYPE_SPEED)
        spans.append({**line, "full": text, "start": t, "end": t + dur, "chars": len(text)})
        t += dur + LINE_GAP
    return spans, t + hold


def keyframes(points: list[tuple[float, float]], total: float) -> tuple[str, str]:
    """Turn (time, value) pairs into SMIL values/keyTimes, clamped and sorted."""
    pts = sorted(points, key=lambda p: p[0])
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < total:
        pts.append((total, pts[-1][1]))

    times, values, last = [], [], -1.0
    for t, v in pts:
        k = min(max(t / total, 0.0), 1.0)
        # SMIL rejects a keyTimes list that is not strictly increasing.
        if k <= last:
            k = min(last + 1e-4, 1.0)
        last = k
        times.append(fmt(k, 5))
        values.append(fmt(v, 2))
    return ";".join(values), ";".join(times)


# --------------------------------------------------------------------------- #
# dot panel
# --------------------------------------------------------------------------- #
def dot_panel(grid: np.ndarray, pal: Palette, mode: str, total: float, field: float) -> str:
    """Render the .npy grid as circles, revealed column by column."""
    if mode == "photo" and not pal.is_dark:
        # Ink goes where the picture is dark, the way a printed halftone works.
        grid = 1.0 - grid
    if field > 0:
        # Every cell keeps a faint dot, so the panel reads as a lit matrix
        # rather than as a shape floating in empty space.
        grid = np.maximum(grid, field)

    rows, cols = grid.shape
    cell = min(PANEL_W / cols, PANEL_H / rows)
    ox = PANEL_X + (PANEL_W - cell * cols) / 2
    oy = PANEL_Y + (PANEL_H - cell * rows) / 2
    r_max = cell * 0.46

    # One <animate> per column instead of per dot: ~42 animations rather than
    # ~1900, which is the difference between a 70 KB file and a 2 MB one.
    sweep = 1.9
    buckets: list[list[str]] = [[] for _ in range(cols)]
    for r in range(rows):
        for c in range(cols):
            v = float(grid[r, c])
            if v < 0.07:
                continue
            radius = 0.55 + v * (r_max - 0.55)
            cx = ox + (c + 0.5) * cell
            cy = oy + (r + 0.5) * cell
            buckets[c].append(
                f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" opacity="{fmt(v * 0.92 + 0.08)}"/>'
            )

    out = [f'<g fill="url(#dots-{pal.name})">']
    for c, dots in enumerate(buckets):
        if not dots:
            continue
        appear = LEAD_IN * 0.3 + (c / max(cols - 1, 1)) * sweep
        vals, times = keyframes(
            [(appear, 0.0), (appear + 0.35, 1.0), (total - FADE, 1.0), (total, 0.0)], total
        )
        # Base attributes hold the FINISHED state on purpose: a renderer with
        # no SMIL support then shows the completed banner instead of a blank
        # box, while browsers animate straight over these values.
        out.append(
            f'<g opacity="1"><animate attributeName="opacity" dur="{fmt(total)}s" '
            f'repeatCount="indefinite" values="{vals}" keyTimes="{times}"/>'
            + "".join(dots)
            + "</g>"
        )
    out.append("</g>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# terminal text
# --------------------------------------------------------------------------- #
def terminal(spans: list[dict], pal: Palette, total: float) -> str:
    """Lines revealed by widening a clip rect, with a cursor riding the edge."""
    colours = {"cmd": pal.text, "hi": pal.accent, "out": pal.muted}
    parts, cursor_x, cursor_y = [], [], []

    for i, s in enumerate(spans):
        y = TEXT_Y0 + i * LINE_H
        width = s["chars"] * CHAR_W
        clip = f"type-{pal.name}-{i}"

        vals, times = keyframes([(s["start"], 0.0), (s["end"], width)], total)
        parts.append(
            f'<clipPath id="{clip}"><rect x="{TEXT_X}" y="{y - FONT_SIZE}" height="{LINE_H}" width="{fmt(width)}">'
            f'<animate attributeName="width" dur="{fmt(total)}s" repeatCount="indefinite" '
            f'values="{vals}" keyTimes="{times}"/></rect></clipPath>'
        )

        body = esc(s["text"])
        weight = ' font-weight="700"' if s["style"] == "hi" else ""
        if s["style"] == "cmd":
            text = (
                f'<text x="{TEXT_X}" y="{y}" xml:space="preserve" clip-path="url(#{clip})">'
                f'<tspan fill="{pal.accent}" font-weight="700">$ </tspan>'
                f'<tspan fill="{colours["cmd"]}">{body}</tspan></text>'
            )
        else:
            text = (
                f'<text x="{TEXT_X}" y="{y}" fill="{colours[s["style"]]}"{weight} '
                f'clip-path="url(#{clip})">{body}</text>'
            )
        parts.append(text)

        # The cursor sits at the start of a line while it types, rides to the
        # end, waits there, then jumps down to the next line.
        nxt = spans[i + 1]["start"] if i + 1 < len(spans) else total
        cursor_x += [(s["start"], TEXT_X), (s["end"], TEXT_X + width), (nxt - 0.02, TEXT_X + width)]
        # y is the text baseline; the block sits above it, not hanging below.
        top = y - FONT_SIZE + 2.5
        cursor_y += [(s["start"], top), (s["end"], top), (nxt - 0.02, top)]

    cx_vals, cx_times = keyframes(cursor_x, total)
    cy_vals, _ = keyframes(cursor_y, total)
    parts.append(
        f'<rect width="{fmt(CHAR_W * 0.82)}" height="{FONT_SIZE + 3}" fill="{pal.accent}" '
        f'x="{fmt(cursor_x[-1][1])}" y="{fmt(cursor_y[-1][1])}">'
        f'<animate attributeName="x" dur="{fmt(total)}s" repeatCount="indefinite" values="{cx_vals}" keyTimes="{cx_times}"/>'
        f'<animate attributeName="y" dur="{fmt(total)}s" repeatCount="indefinite" values="{cy_vals}" keyTimes="{cx_times}"/>'
        f'<animate attributeName="opacity" dur="1.06s" repeatCount="indefinite" '
        f'values="1;0" keyTimes="0;0.5" calcMode="discrete"/></rect>'
    )

    fade_v, fade_t = keyframes([(0, 1.0), (total - FADE, 1.0), (total, 0.0)], total)
    return (
        f'<g font-family="{FONT_MONO}" font-size="{FONT_SIZE}">'
        + "".join(p for p in parts if p.startswith("<clipPath"))
        + f'<g opacity="1"><animate attributeName="opacity" dur="{fmt(total)}s" '
        f'repeatCount="indefinite" values="{fade_v}" keyTimes="{fade_t}"/>'
        + "".join(p for p in parts if not p.startswith("<clipPath"))
        + "</g></g>"
    )


# --------------------------------------------------------------------------- #
def render(cfg: dict, grid: np.ndarray, pal: Palette) -> str:
    spans, total = build_timeline(cfg["lines"], cfg.get("cycle_hold", 3.0))
    title = esc(cfg.get("title", "profile.sh"))

    dots = ["#f87171", "#fbbf24", "#34d399"] if pal.is_dark else ["#ff5f57", "#febc2e", "#28c840"]
    chrome = "".join(
        f'<circle cx="{26 + i * 19}" cy="{CHROME_H / 2}" r="5.5" fill="{c}"/>'
        for i, c in enumerate(dots)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" \
role="img" aria-label="{title} - Luis Viuche">
<defs>
<linearGradient id="dots-{pal.name}" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{pal.accent}"/><stop offset="1" stop-color="{pal.text}"/>
</linearGradient>
</defs>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="{pal.bg}" stroke="{pal.border}"/>
<path d="M1 15a14 14 0 0 1 14-14h{W - 30}a14 14 0 0 1 14 14v{CHROME_H - 15}H1z" fill="{pal.panel}"/>
<line x1="1" y1="{CHROME_H}" x2="{W - 1}" y2="{CHROME_H}" stroke="{pal.border}"/>
{chrome}
<text x="94" y="{CHROME_H / 2 + 4.5}" font-family="{FONT_MONO}" font-size="12.5" fill="{pal.muted}">{title}</text>
{dot_panel(grid, pal, cfg["source"].get("mode", "glyph"), total, cfg["source"].get("field", 0.0))}
{terminal(spans, pal, total)}
</svg>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=ROOT / "assets" / "banner.json")
    ap.add_argument("--out", type=Path, default=ROOT / "assets" / "banner")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text())
    grid = np.load(ROOT / cfg["source"]["file"])
    themes = load_theme()

    svgs = {name: render(cfg, grid, pal) for name, pal in themes.items()}
    for path in write_pair(args.out, svgs):
        print(f"{path}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
