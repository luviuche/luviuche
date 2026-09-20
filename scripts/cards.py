"""Generate the stats card and the featured-project cards as local SVGs.

These replace github-readme-stats, streak-stats and github-profile-trophy on
purpose. Those are shared public instances: when they rate-limit or fall over,
every README pointing at them shows a broken image. Committing our own SVGs
means the profile renders from this repo alone.

    python scripts/cards.py --user luviuche --out assets
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

from theme import FONT_SANS, Palette, esc, fmt, load_theme, write_pair

API = "https://api.github.com"

# Exit code for "GitHub was unreachable or rate-limited". The build treats it
# as a warning: yesterday's committed cards are better than a failed run and
# a README full of broken images.
EX_TEMPFAIL = 75


class GitHubUnavailable(RuntimeError):
    pass

STREAK_FLOOR_CURRENT = 7
STREAK_FLOOR_LONGEST = 14

CARD_W, CARD_H = 470, 168
STAT_W = 470
STAT_ROW_H = 46

# Enough of GitHub's language palette to cover what shows up here; anything
# unknown falls back to the accent colour.
LANG_COLOURS = {
    "Java": "#b07219",
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "C#": "#178600",
    "Shell": "#89e051",
    "Dockerfile": "#384d54",
    "Jupyter Notebook": "#DA5B0B",
    "TeX": "#3D6117",
    "Makefile": "#427819",
    "PLpgSQL": "#336790",
}

# Anything outside the table above still needs a distinct colour, or adjacent
# bar segments merge into one block.
FALLBACK_COLOURS = ["#9d7cd8", "#6ab7a3", "#d98c5f", "#5f8cd9", "#c96f9b"]


def language_colour(name: str, pal: Palette) -> str:
    if name in LANG_COLOURS:
        return LANG_COLOURS[name]
    if name == "Other":
        return pal.grid
    return FALLBACK_COLOURS[sum(map(ord, name)) % len(FALLBACK_COLOURS)]


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
def _request(url: str, token: str | None, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-card-generator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            reset = exc.headers.get("X-RateLimit-Reset")
            when = (
                datetime.fromtimestamp(int(reset), UTC).strftime("%H:%M UTC")
                if reset and reset.isdigit()
                else "shortly"
            )
            raise GitHubUnavailable(
                f"rate-limited by the GitHub API, resets at {when}."
                + ("" if token else " Set GITHUB_TOKEN to raise the limit from 60/hour to 5,000.")
            ) from exc
        raise
    except urllib.error.URLError as exc:
        raise GitHubUnavailable(f"could not reach the GitHub API: {exc.reason}") from exc


def fetch_user(user: str, token: str | None) -> dict:
    return _request(f"{API}/users/{user}", token)


def fetch_repos(user: str, token: str | None) -> list[dict]:
    repos, page = [], 1
    while page <= 5:
        batch = _request(f"{API}/users/{user}/repos?per_page=100&page={page}", token)
        if not batch:
            break
        repos += batch
        page += 1
    return repos


def fetch_contributions(user: str, token: str | None) -> dict | None:
    """Contribution calendar via GraphQL. Needs a token; returns None without one."""
    if not token:
        return None
    query = """
    query($login:String!) {
      user(login:$login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }"""
    try:
        payload = _request(
            "https://api.github.com/graphql", token, {"query": query, "variables": {"login": user}}
        )
        cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except (urllib.error.HTTPError, KeyError, TypeError):
        # A token without the contribution scope just means fewer tiles.
        return None

    days = [d for week in cal["weeks"] for d in week["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    return {"total": cal["totalContributions"], "days": days}


def fetch_languages(
    repos: list[dict], token: str | None, metric: str = "balanced"
) -> list[tuple[str, float]]:
    """Language shares across the account, biggest first.

    Two ways to count, because raw bytes lie. One repo carrying a vendored or
    generated bundle can be two thirds of an entire account by size, which
    would report someone as a JavaScript developer on the strength of a file
    they never typed.

    "balanced" gives every repo an equal vote: each repo's languages are
    converted to percentages of that repo first, then averaged. It answers
    "what does a typical project of mine look like".

    "bytes" is the plain sum, kept for when volume really is the question.
    """
    totals: dict[str, float] = {}
    counted = 0
    for repo in repos:
        try:
            sizes = _request(repo["languages_url"], token)
        except urllib.error.HTTPError:
            # A single unreadable repo is fine to skip; a rate limit is not,
            # and GitHubUnavailable deliberately propagates.
            continue
        if not sizes:
            continue
        counted += 1
        repo_total = sum(sizes.values()) or 1
        for language, size in sizes.items():
            share = size / repo_total if metric == "balanced" else size
            totals[language] = totals.get(language, 0.0) + share

    if metric == "balanced" and counted:
        totals = {k: v / counted for k, v in totals.items()}
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def streaks(days: list[dict]) -> tuple[int, int]:
    """Current and longest daily streak, ignoring a still-empty today."""
    today = date.today()
    longest = run = 0
    for day in days:
        when = datetime.strptime(day["date"], "%Y-%m-%d").date()
        if when > today:
            continue
        if day["contributionCount"] > 0:
            run += 1
            longest = max(longest, run)
        elif when != today:
            # Today counts as pending, not as a break.
            run = 0
    # `run` is whatever streak is still open at the end of the calendar,
    # which is exactly the current streak.
    return run, longest


# --------------------------------------------------------------------------- #
# drawing
# --------------------------------------------------------------------------- #
def wrap(text: str, width_px: float, font_size: float) -> list[str]:
    """Greedy wrap using an average glyph width - good enough for a card."""
    per_char = font_size * 0.515
    limit = max(8, int(width_px / per_char))
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) <= limit:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def shell(width: int, height: int, pal: Palette, label: str) -> tuple[str, str]:
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" role="img" aria-label="{esc(label)}" font-family="{FONT_SANS}">'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="11" '
        f'fill="{pal.bg}" stroke="{pal.border}"/>'
    )
    return head, "</svg>"


def stats_card(user: str, stats: dict, pal: Palette) -> str:
    # Height follows the number of tiles so a short card never leaves a band
    # of empty space under the last row.
    rows = max(1, -(-len(stats["tiles"]) // 3))
    height = 58 + rows * STAT_ROW_H + 12
    head, tail = shell(STAT_W, height, pal, f"{user} GitHub statistics")
    out = [
        head,
        f'<text x="22" y="36" font-size="15.5" font-weight="700" fill="{pal.accent}">{esc(user)}</text>',
        f'<text x="{STAT_W - 22}" y="36" font-size="11" text-anchor="end" fill="{pal.muted}">at a glance</text>',
        f'<line x1="22" y1="49" x2="{STAT_W - 22}" y2="49" stroke="{pal.border}"/>',
    ]

    tiles = [(label, value) for label, value in stats["tiles"]]
    for i, (label, value) in enumerate(tiles):
        col, row = i % 3, i // 3
        x = 22 + col * ((STAT_W - 44) / 3)
        y = 78 + row * 46
        out.append(
            f'<text x="{fmt(x)}" y="{y}" font-size="23" font-weight="700" fill="{pal.text}">{esc(value)}</text>'
            f'<text x="{fmt(x)}" y="{y + 17}" font-size="10.5" fill="{pal.muted}">{esc(label)}</text>'
        )

    out.append(tail)
    return "".join(out)


def languages_card(
    languages: list[tuple[str, float]], pal: Palette, metric: str = "balanced", top: int = 8
) -> str:
    """A stacked bar of language bytes, with a two-column legend under it."""
    head_items = languages[:top]
    rest = sum(size for _, size in languages[top:])
    if rest:
        head_items = head_items + [("Other", rest)]
    total = sum(size for _, size in head_items) or 1

    rows = -(-len(head_items) // 2)
    height = 96 + rows * 21
    head, tail = shell(STAT_W, height, pal, "Most used languages")
    out = [
        head,
        f'<text x="22" y="34" font-size="15.5" font-weight="700" fill="{pal.accent}">Language mix</text>',
        f'<text x="{STAT_W - 22}" y="34" font-size="11" text-anchor="end" fill="{pal.muted}">{"averaged per repo" if metric == "balanced" else "by bytes written"}</text>',
    ]

    # The bar, drawn as clipped segments so the rounded ends stay rounded.
    bar_x, bar_y, bar_w, bar_h = 22, 50, STAT_W - 44, 13
    out.append(
        f'<clipPath id="bar-{pal.name}"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" '
        f'height="{bar_h}" rx="{bar_h / 2}"/></clipPath>'
        f'<g clip-path="url(#bar-{pal.name})">'
    )
    x = float(bar_x)
    for name, size in head_items:
        width = bar_w * size / total
        colour = language_colour(name, pal)
        out.append(f'<rect x="{fmt(x)}" y="{bar_y}" width="{fmt(width + 0.6)}" height="{bar_h}" fill="{colour}"/>')
        x += width
    out.append("</g>")

    for i, (name, size) in enumerate(head_items):
        col, row = i % 2, i // 2
        lx = 22 + col * ((STAT_W - 44) / 2)
        ly = 92 + row * 21
        colour = language_colour(name, pal)
        pct = 100 * size / total
        out.append(
            f'<circle cx="{fmt(lx + 5)}" cy="{fmt(ly - 4)}" r="5" fill="{colour}"/>'
            f'<text x="{fmt(lx + 16)}" y="{ly}" font-size="11.5" fill="{pal.text}">{esc(name)}</text>'
            f'<text x="{fmt(lx + (STAT_W - 44) / 2 - 12)}" y="{ly}" font-size="11.5" '
            f'text-anchor="end" fill="{pal.muted}">{pct:.1f}%</text>'
        )

    out.append(tail)
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--lang-metric",
        choices=("balanced", "bytes"),
        default="balanced",
        help="balanced gives every repo an equal vote; bytes sums raw file sizes",
    )
    ap.add_argument(
        "--exclude-langs",
        default="",
        help="comma-separated repos to leave out of the language card - use it for "
        "repos with vendored or generated files, which skew a byte count badly",
    )
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or None
    themes = load_theme()

    user = fetch_user(args.user, token)
    repos = fetch_repos(args.user, token)
    own = [r for r in repos if not r["fork"]]
    stars = sum(r["stargazers_count"] for r in own)

    languages = {r["language"] for r in own if r["language"]}
    joined = datetime.strptime(user["created_at"], "%Y-%m-%dT%H:%M:%SZ").date()

    # Candidates in priority order, each with the threshold below which it is
    # not worth showing. A wall of zeroes reads worse than a smaller card.
    candidates: list[tuple[str, int, int]] = []
    contributions = fetch_contributions(args.user, token)
    if contributions:
        current, longest = streaks(contributions["days"])
        candidates += [
            ("Contributions (1y)", contributions["total"], 1),
            # Streaks only earn their tile once they are worth reporting. A
            # "longest streak: 7" tells the reader you have never coded eight
            # days running, which is the opposite of what the tile is for.
            ("Current streak", current, STREAK_FLOOR_CURRENT),
            ("Longest streak", longest, STREAK_FLOOR_LONGEST),
        ]
    candidates += [
        ("Public repos", user["public_repos"], 1),
        ("Sources, not forks", len(own), 1),
        ("Languages used", len(languages), 2),
        ("Years on GitHub", max(1, (date.today() - joined).days // 365), 1),
        ("Total stars", stars, 1),
        ("Followers", user["followers"], 5),
    ]
    tiles = [(label, str(value)) for label, value, floor_ in candidates if value >= floor_][:6]

    args.out.mkdir(parents=True, exist_ok=True)
    written = write_pair(
        args.out / "card-stats",
        {n: stats_card(args.user, {"tiles": tiles}, p) for n, p in themes.items()},
    )

    skip = {name.strip().lower() for name in args.exclude_langs.split(",") if name.strip()}
    langs = fetch_languages(
        [r for r in own if r["name"].lower() not in skip], token, args.lang_metric
    )
    if langs:
        written += write_pair(
            args.out / "card-languages",
            {n: languages_card(langs, p, args.lang_metric) for n, p in themes.items()},
        )

    for path in written:
        print(f"{path}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    try:
        main()
    except GitHubUnavailable as exc:
        print(f"  ! {exc}\n  ! keeping the cards already committed", file=sys.stderr)
        raise SystemExit(EX_TEMPFAIL) from exc
