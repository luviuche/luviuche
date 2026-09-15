"""Shared palette + SVG helpers for every generator in scripts/.

Colours live in assets/theme.json so a single hex change repaints the whole
profile on the next workflow run.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_MONO = "JetBrains Mono,SFMono-Regular,Consolas,Liberation Mono,monospace"
FONT_SANS = "ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"


class Palette:
    """One theme's colours, plus the accent shared by both themes."""

    def __init__(self, name: str, colours: dict, accent: str):
        self.name = name
        self.accent = accent
        self.bg = colours["bg"]
        self.panel = colours["panel"]
        self.border = colours["border"]
        self.text = colours["text"]
        self.muted = colours["muted"]
        self.grid = colours["grid"]

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


def load_theme(path: Path | None = None) -> dict[str, Palette]:
    data = json.loads((path or ROOT / "assets" / "theme.json").read_text())
    accent = data["accent"]
    return {name: Palette(name, data[name], accent) for name in ("dark", "light")}


def esc(text: str) -> str:
    """Escape text for an SVG text node."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt(value: float, places: int = 2) -> str:
    """Trim float noise so the generated SVG stays small and diffs stay clean."""
    out = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return out if out not in ("", "-0") else "0"


def write_pair(out_stem: Path, svgs: dict[str, str]) -> list[Path]:
    """Write the dark/light pair as <stem>-dark.svg / <stem>-light.svg."""
    written = []
    for name, svg in svgs.items():
        path = out_stem.with_name(f"{out_stem.name}-{name}.svg")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    return written
