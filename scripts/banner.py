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

from theme import FONT_MONO, ROOT, Palette, esc, fmt, load_theme, mix, write_pair

W, H = 1180, 560
CHROME_H = 42

# A portrait needs portrait proportions. A square panel either crops the hair
# or the chin, and shrinks the face until nothing survives the reduction.
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 48, 78, 340, 452

TEXT_X = 444
TEXT_Y0 = 172
LINE_H = 46
FONT_SIZE = 18

# Ink below this is background noise, not picture. Skipping it is what lets
# the portrait sit on the panel instead of inside a rectangle of grey dots.
INK_FLOOR = 0.10
TONES = 7
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
def tone_ramp(pal: Palette, steps: int) -> list[str]:
    """Colours from dim to bright, for mapping ink intensity onto.

    The previous version filled every dot from one diagonal gradient, so a
    dot's colour said where it sat on the panel rather than how bright it was.
    That flattens a face: the shading carries the likeness, and a positional
    gradient throws exactly that away.
    """
    low = mix(pal.accent, pal.bg, 0.62)
    high = mix(pal.accent, pal.text, 0.6)
    ramp = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        ramp.append(mix(low, pal.accent, t * 2) if t < 0.5 else mix(pal.accent, high, (t - 0.5) * 2))
    return ramp


def dot_panel(grid: np.ndarray, pal: Palette, total: float, field: float) -> str:
    """Render the ink grid as dots, grouped by tone and wiped in from the left.

    The grid is ink, and the same ink is drawn in both themes - light dots on
    the dark background, dark dots on the light one. Which pixels became ink
    was decided once, by dotify's --invert, because that depends on the
    picture rather than on the reader's theme.
    """
    if field > 0:
        # Every cell keeps a faint dot, so the panel reads as a lit matrix.
        # A monogram or a logo wants this; a portrait does not, because the
        # grid then competes with the face for attention.
        grid = np.maximum(grid, field)

    rows, cols = grid.shape
    cell = min(PANEL_W / cols, PANEL_H / rows)
    ox = PANEL_X + (PANEL_W - cell * cols) / 2
    oy = PANEL_Y + (PANEL_H - cell * rows) / 2
    r_max = cell * 0.52

    # One group per tone rather than per dot: the fill is written seven times
    # instead of several thousand, which is what keeps a high-resolution
    # portrait to a sane file size.
    ramp = tone_ramp(pal, TONES)
    buckets: list[list[str]] = [[] for _ in range(TONES)]
    for r in range(rows):
        for c in range(cols):
            v = float(grid[r, c])
            if v < INK_FLOOR:
                continue
            t = (v - INK_FLOOR) / (1.0 - INK_FLOOR)
            buckets[min(int(t * TONES), TONES - 1)].append(
                f'<circle cx="{fmt(ox + (c + 0.5) * cell, 1)}" cy="{fmt(oy + (r + 0.5) * cell, 1)}"'
                f' r="{fmt(0.35 + t * (r_max - 0.35))}"/>'
            )

    wipe = f"wipe-{pal.name}"
    reveal, times = keyframes(
        [(LEAD_IN * 0.2, 0.0), (LEAD_IN * 0.2 + 2.1, PANEL_W), (total - FADE, PANEL_W), (total, 0.0)],
        total,
    )
    out = [
        f'<clipPath id="{wipe}"><rect x="{PANEL_X}" y="{PANEL_Y}" height="{PANEL_H}" width="{PANEL_W}">'
        f'<animate attributeName="width" dur="{fmt(total)}s" repeatCount="indefinite" '
        f'values="{reveal}" keyTimes="{times}"/></rect></clipPath>',
        f'<g clip-path="url(#{wipe})">',
    ]
    for colour, dots in zip(ramp, buckets):
        if dots:
            out.append(f'<g fill="{colour}">' + "".join(dots) + "</g>")
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
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="{pal.bg}" stroke="{pal.border}"/>
<path d="M1 15a14 14 0 0 1 14-14h{W - 30}a14 14 0 0 1 14 14v{CHROME_H - 15}H1z" fill="{pal.panel}"/>
<line x1="1" y1="{CHROME_H}" x2="{W - 1}" y2="{CHROME_H}" stroke="{pal.border}"/>
{chrome}
<text x="94" y="{CHROME_H / 2 + 4.5}" font-family="{FONT_MONO}" font-size="12.5" fill="{pal.muted}">{title}</text>
{dot_panel(grid, pal, total, cfg["source"].get("field", 0.0))}
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
