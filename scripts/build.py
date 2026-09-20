"""Regenerate every asset in the right order, then validate the result.

One command locally, one step in CI:

    python scripts/build.py                  # everything
    python scripts/build.py --skip-cards     # offline, no GitHub API
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CACHE = ROOT / "assets" / "source" / "cache"

MONOGRAM = "LV"

# Repos whose bytes would distort the language card. Large vendored or
# generated files make one project outshout an entire account.
EXCLUDE_LANGS: list[str] = []


EX_TEMPFAIL = 75


def run(*args: str, tolerate: tuple[int, ...] = ()) -> bool:
    """Run a generator. Returns False if it failed in a way we chose to allow."""
    print(f"\n$ {' '.join(args)}")
    result = subprocess.run([sys.executable, *args], cwd=ROOT)
    if result.returncode in tolerate:
        return False
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", default="luviuche")
    ap.add_argument("--skip-cards", action="store_true", help="skip anything needing the API")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)

    # 1. Dot-matrix caches. The monogram is always available as a fallback;
    #    the portrait is rebuilt from whatever banner.json points at.
    run(str(SCRIPTS / "dotify.py"), "--monogram", MONOGRAM, "-o", str(CACHE / "monogram.npy"))

    banner_cfg = json.loads((ROOT / "assets" / "banner.json").read_text(encoding="utf-8"))
    source = banner_cfg["source"]
    opts = source.get("dotify", {})
    frames = source.get("frames") or ([source] if source.get("image") else [])

    for frame in frames:
        image_path = ROOT / frame["image"]
        if not image_path.exists():
            raise SystemExit(
                f"assets/banner.json points at {frame['image']}, which does not exist.\n"
                "Fetch it with scripts/fetch_icons.py, or drop the entry."
            )
        cmd = [str(SCRIPTS / "dotify.py"), str(image_path), "-o", str(ROOT / frame["file"])]
        for flag in ("invert", "no-square", "no-autocontrast"):
            if opts.get(flag):
                cmd.append(f"--{flag}")
        for flag in ("crop", "gamma", "cols", "rows", "vignette"):
            if flag in opts:
                cmd += [f"--{flag}", str(opts[flag])]
        run(*cmd)

    # 2. The hero banner.
    run(str(SCRIPTS / "banner.py"))

    # 3. The skill radar, from hand-authored JSON. A language radar used to
    #    live here too; the measured language card makes it redundant.
    run(str(SCRIPTS / "radar.py"), "--data", "assets/skills.json", "-o", "assets/radar")

    # 4. Stats and language mix, straight from the GitHub API.
    if not args.skip_cards:
        cards = [
            str(SCRIPTS / "cards.py"),
            "--user", args.user,
            "--out", "assets",
        ]
        if EXCLUDE_LANGS:
            cards += ["--exclude-langs", ",".join(EXCLUDE_LANGS)]
        # A rate limit or a network blip must not fail the whole build: the
        # banner and radars are local, and the committed cards stay valid.
        if not run(*cards, tolerate=(EX_TEMPFAIL,)):
            print("  warning: cards were left at their committed versions")

    # 5. Never commit an SVG whose animation a browser would silently drop.
    run(str(SCRIPTS / "validate.py"))
    print("\nbuild complete")


if __name__ == "__main__":
    main()
