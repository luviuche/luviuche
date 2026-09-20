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

W, H = 1180, 462
CHROME_H = 42

# Square, because logos are square. A portrait would want this taller.
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 48, 76, 352, 352

TEXT_X = 452
TEXT_Y0 = 140
LINE_H = 42
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
def _dots(grid: np.ndarray, pal: Palette, field: float, geom: tuple[float, float, float]) -> str:
    """Tone-grouped circles for one frame."""
    if field > 0:
        # Every cell keeps a faint dot, so the panel reads as a lit matrix.
        grid = np.maximum(grid, field)

    cell, ox, oy = geom
    r_max = cell * 0.52
    rows, cols = grid.shape

    # One group per tone rather than per dot: the fill is written seven times
    # instead of several thousand, which is what keeps this to a sane size.
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

    return "".join(
        f'<g fill="{colour}">' + "".join(dots) + "</g>"
        for colour, dots in zip(ramp, buckets)
        if dots
    )


def tone_ramp(pal: Palette, steps: int) -> list[str]:
    """Colours from dim to bright, for mapping ink intensity onto.

    An earlier version filled every dot from one diagonal gradient, so a dot's
    colour said where it sat on the panel rather than how bright it was. That
    flattens an image: the shading carries the shape, and a positional
    gradient throws exactly that away.
    """
    low = mix(pal.accent, pal.bg, 0.62)
    high = mix(pal.accent, pal.text, 0.6)
    ramp = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        ramp.append(mix(low, pal.accent, t * 2) if t < 0.5 else mix(pal.accent, high, (t - 0.5) * 2))
    return ramp


def dot_panel(
    grids: list[np.ndarray], pal: Palette, total: float, field: float, frame_seconds: float
) -> str:
    """Draw the dot panel: one still image, or several cross-fading.

    The grids are ink, and the same ink is drawn in both themes - light dots
    on the dark background, dark dots on the light one. Which pixels became
    ink was decided once, by dotify, because that depends on the picture
    rather than on the reader's theme.

    A single frame gets a wipe reveal tied to the terminal's cycle. Several
    frames cross-fade on a cycle of their own, deliberately not locked to the
    typing: two loops of different lengths keep the banner from looking like
    it restarts on a beat.
    """
    rows, cols = grids[0].shape
    cell = min(PANEL_W / cols, PANEL_H / rows)
    geom = (cell, PANEL_X + (PANEL_W - cell * cols) / 2, PANEL_Y + (PANEL_H - cell * rows) / 2)

    if len(grids) == 1:
        wipe = f"wipe-{pal.name}"
        reveal, times = keyframes(
            [(LEAD_IN * 0.2, 0.0), (LEAD_IN * 0.2 + 2.1, PANEL_W),
             (total - FADE, PANEL_W), (total, 0.0)],
            total,
        )
        return (
            f'<clipPath id="{wipe}"><rect x="{PANEL_X}" y="{PANEL_Y}" height="{PANEL_H}" '
            f'width="{PANEL_W}"><animate attributeName="width" dur="{fmt(total)}s" '
            f'repeatCount="indefinite" values="{reveal}" keyTimes="{times}"/></rect></clipPath>'
            f'<g clip-path="url(#{wipe})">{_dots(grids[0], pal, field, geom)}</g>'
        )

    cycle = frame_seconds * len(grids)
    fade = min(0.5, frame_seconds * 0.28)

    # The lit-matrix background is drawn once, behind everything. Giving each
    # frame its own copy would make the whole grid pulse every time the icons
    # cross-fade, which reads as a flicker rather than as a panel.
    #
    # Every one of its cells is the same dot, so it is a <pattern> tile rather
    # than several thousand identical <circle> elements - worth about 190 KB.
    out = []
    if field > 0:
        cell, ox, oy = geom
        t = (field - INK_FLOOR) / (1.0 - INK_FLOOR)
        radius = 0.35 + t * (cell * 0.52 - 0.35)
        colour = tone_ramp(pal, TONES)[min(int(t * TONES), TONES - 1)]
        out.append(
            f'<pattern id="grid-{pal.name}" x="{fmt(ox)}" y="{fmt(oy)}" width="{fmt(cell, 4)}" '
            f'height="{fmt(cell, 4)}" patternUnits="userSpaceOnUse">'
            f'<circle cx="{fmt(cell / 2, 4)}" cy="{fmt(cell / 2, 4)}" r="{fmt(radius)}" fill="{colour}"/>'
            f'</pattern>'
            f'<rect x="{fmt(ox)}" y="{fmt(oy)}" width="{fmt(cell * cols)}" '
            f'height="{fmt(cell * rows)}" fill="url(#grid-{pal.name})"/>'
        )
        field = 0.0

    for i, grid in enumerate(grids):
        begin, stop = i * frame_seconds, (i + 1) * frame_seconds
        vals, times = keyframes(
            [(begin, 0.0), (begin + fade, 1.0), (stop - fade, 1.0), (stop, 0.0)], cycle
        )
        # The first frame is visible in the base attributes so a renderer with
        # no SMIL support shows an icon rather than an empty panel.
        out.append(
            f'<g opacity="{1 if i == 0 else 0}"><animate attributeName="opacity" dur="{fmt(cycle)}s" '
            f'repeatCount="indefinite" values="{vals}" keyTimes="{times}"/>'
            + _dots(grid, pal, field, geom)
            + "</g>"
        )
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
def render(cfg: dict, grids: list[np.ndarray], pal: Palette) -> str:
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
{dot_panel(grids, pal, total, cfg["source"].get("field", 0.0), cfg["source"].get("frame_seconds", 2.8))}
{terminal(spans, pal, total)}
</svg>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=ROOT / "assets" / "banner.json")
    ap.add_argument("--out", type=Path, default=ROOT / "assets" / "banner")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text())
    source = cfg["source"]
    # Either one still image, or a list of frames that cross-fade.
    files = [f["file"] for f in source["frames"]] if "frames" in source else [source["file"]]
    grids = [np.load(ROOT / f) for f in files]
    shapes = {g.shape for g in grids}
    if len(shapes) > 1:
        raise SystemExit(f"frames must share one grid shape, got {sorted(shapes)}")
    themes = load_theme()

    svgs = {name: render(cfg, grids, pal) for name, pal in themes.items()}
    for path in write_pair(args.out, svgs):
        print(f"{path}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
