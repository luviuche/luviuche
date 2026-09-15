# Maintaining this profile

Nothing in `assets/*.svg` is written by hand. The JSON files are the input, the
scripts are the renderer, and the `Assets` workflow keeps the two in sync.

```
assets/theme.json      colours for both themes, and the accent
assets/banner.json     the terminal lines in the hero banner
assets/skills.json     the self-rated skill radar
assets/langmix.json    the hand-authored language radar
assets/projects.json   which repos appear as project cards
```

## What updates itself, and what does not

This matters: half the charts are live and half are not.

| Asset | Source | Updates by itself? |
|---|---|---|
| `card-stats-*` | GitHub API | Yes, daily |
| `card-languages-*` | GitHub API | Yes, daily |
| `card-<repo>-*` | GitHub API + `projects.json` | Stars, forks and dates yes; the blurb is yours |
| `radar-*` | `skills.json` | **No - a human writes these numbers** |
| `radar-langs-*` | `langmix.json` | **No - a human writes these numbers** |
| `banner-*` | `banner.json` | No |

The two radars are a self-assessment. The daily workflow redraws the picture but
never touches the values, so they stay exactly as written until someone edits
the JSON. Treat them like a CV line: worth revisiting every few months, and
stale if you finish a Spring course and the Java number never moves.

That is the point of having both. The radar says what you reach for; the
language card, computed from real code, says what you have actually written.
When those two disagree, the disagreement is the interesting part.

If you would rather the language radar be automatic, `scripts/cards.py` already
computes the numbers - `langmix.json` could be generated from the same call
instead of hand-written.

## Changing something

Edit a JSON file, commit, push. The workflow redraws every affected SVG and
commits the result. To preview before pushing:

```bash
pip install -r scripts/requirements.txt
python scripts/build.py              # everything
python scripts/build.py --skip-cards # offline: no GitHub API calls
open preview.html                    # both themes, animations running
```

## Using a real photo in the banner

The dot panel currently renders an `LV` monogram. To use a portrait:

1. Save the photo as `assets/source/portrait.jpg` (or `.png`). Front-facing
   with strong contrast works best - the image is reduced to roughly 1,900
   dots, so fine detail disappears.
2. In `assets/banner.json`, set:
   ```json
   "source": { "file": "assets/source/cache/portrait.npy", "mode": "photo", "field": 0.1 }
   ```
3. Push. `scripts/build.py` regenerates the dot cache and both banners.

`mode` matters. `photo` inverts on the light theme so ink lands where the
picture is dark, the way a printed halftone works. `glyph` keeps the same
shape in both themes, which is what a monogram or a logo wants.

## Why the charts are self-hosted

`github-readme-stats`, `streak-stats` and `github-profile-trophy` are shared
public instances. When they rate-limit or go down, every README pointing at
them shows a broken image, and there is nothing you can do about it from here.
`scripts/cards.py` produces the same information as committed SVG files, so
this profile renders from this repository alone.

The one deliberate exception is the typing line in the header, which comes from
`readme-typing-svg`. It degrades to nothing rather than to a broken layout.

## The language card counts by repo, not by bytes

A single repo with a vendored or generated bundle can be two thirds of an
account by file size. Counting raw bytes here reported 49% JavaScript for a
profile whose actual work is Java and Python.

`--lang-metric balanced` (the default) converts each repo's languages to
percentages of that repo first, then averages across repos, so every project
gets an equal vote. `--lang-metric bytes` restores the raw sum. For repos that
should not count at all, list them in `EXCLUDE_LANGS` in `scripts/build.py`.

## If an image looks stale on GitHub

GitHub proxies README images and caches them. A regenerated SVG at the same
path usually refreshes on push, but if one sticks, bump a version into the
filename (`banner-dark.v2.svg`) and update the README reference.

## Token

The stat card shows contribution totals and streaks only with a personal access
token, because the REST API does not expose the contribution graph. Add one as
a repository secret named `METRICS_TOKEN` (scope: `read:user`). Without it the
card falls back to tiles the public API does provide.
