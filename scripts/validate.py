"""Sanity-check generated SVGs before they are committed.

SMIL fails silently: a browser that dislikes a keyTimes list just drops the
animation, and the README quietly stops moving. These assertions catch that in
CI instead of in someone's browser.

    python scripts/validate.py assets/*.svg
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = "{http://www.w3.org/2000/svg}"


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"{path}: not well-formed XML - {exc}"]

    if not root.get("viewBox"):
        problems.append(f"{path}: missing viewBox, will not scale in the README")

    for tag in ("animate", "animateTransform"):
        for a in root.iter(SVG + tag):
            name = a.get("attributeName", "?")
            where = f"{path}: <{tag} {name}>"
            values, key_times = a.get("values"), a.get("keyTimes")
            if values is None or key_times is None:
                continue

            vals = values.split(";")
            try:
                times = [float(t) for t in key_times.split(";")]
            except ValueError:
                problems.append(f"{where} keyTimes is not numeric")
                continue

            if len(vals) != len(times):
                problems.append(f"{where} {len(vals)} values vs {len(times)} keyTimes")
            if times[0] != 0.0:
                problems.append(f"{where} keyTimes must start at 0, got {times[0]}")
            if any(b <= a_ for a_, b in zip(times, times[1:])):
                problems.append(f"{where} keyTimes must strictly increase")
            # Only paced/linear timing has to land on 1; discrete may stop short.
            if a.get("calcMode", "linear") != "discrete" and abs(times[-1] - 1.0) > 1e-9:
                problems.append(f"{where} keyTimes must end at 1, got {times[-1]}")

    return problems


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = sorted((Path(__file__).resolve().parent.parent / "assets").glob("*.svg"))

    problems = [p for path in paths for p in check(path)]
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"checked {len(paths)} SVG files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
