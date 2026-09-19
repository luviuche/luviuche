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
python scripts/build.py --skip-cards # what you normally want
open preview.html                    # both themes, animations running
```

Use `--skip-cards` locally. A plain `python scripts/build.py` rebuilds the stat
and language cards too, and without a token on your machine they come out
worse than the ones CI committed - the stat card loses its contribution and
streak tiles. Committing that would downgrade the live profile until the next
nightly run. Those two files belong to the schedule; leave them alone.

### One consequence worth knowing

Because pushes skip the API-backed cards, editing `projects.json` does not
redraw the project cards straight away. Either wait for the nightly run, or
trigger it by hand: Actions -> Assets -> Run workflow. Edits to `banner.json`,
`skills.json`, `langmix.json` and `theme.json` are unaffected and redraw on
push as usual.

## The banner portrait

`assets/banner.json` describes the whole picture pipeline. `build.py` reads the
`source` block, runs the original photo through `dotify.py`, and redraws both
themes:

```json
"source": {
  "image": "assets/source/portrait.jpeg",
  "file":  "assets/source/cache/portrait.npy",
  "field": 0,
  "dotify": { "invert": true, "crop": "...", "no-square": true,
              "cols": 84, "rows": 112, "gamma": 0.8, "vignette": 0.55 }
}
```

Drop `image` and it falls back to the `LV` monogram cache. Swapping in a new
photo means replacing the file and retuning four numbers:

**`invert`** — the grid stores *ink*, not brightness, and the same ink is drawn
in both themes. `invert: true` puts ink where the photo is dark, which is right
for a dark-haired subject against a pale wall. A face lit against a dark
background wants `false`. Get this backwards and you get a negative.

**`crop`** — `left,top,right,bottom` as fractions. Frame the head. A centre
crop of a phone photo keeps half a room, and at a couple of thousand dots there
is no resolution to waste on a wall. With `no-square`, the crop's aspect must
match `cols:rows` or the face stretches.

**`cols` / `rows`** — resolution, and the setting that matters most. 34x46 gave
a silhouette with no face in it, 48x64 a blocky approximation; 84x112 is where
it reads as a photograph. Aim for about three screen pixels per dot at the
width GitHub renders the README, which for this panel is 84 columns. Higher is
not better - past that the dots stop resolving and turn to mush.

**`field`** (outside the `dotify` block) — minimum ink in every cell. Keep it
at `0` for a portrait: a faint background grid competes with the face for
attention. A monogram or a logo wants about `0.1`, which gives the panel its
lit-matrix look.

**`vignette`** — where the edge falloff starts, 0 to disable. It fades the room
away so the face is what is lit, and costs nothing compared to running a
segmentation model.

Dots are coloured by intensity, through a seven-step ramp from a dimmed accent
up to a near-white one, and grouped so the fill is written seven times rather
than seven thousand. An earlier version filled them from one diagonal
gradient, which made a dot's colour depend on where it sat rather than how
bright it was - and since the shading is what carries a likeness, it flattened
the face.

When a photo will not read, the order to try things in is: resolution first,
then crop, then polarity, then gamma. Render both themes and look - a portrait
that works on dark can be mud on light.

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

Contribution totals and streaks come from the GraphQL API, which the REST API
does not expose. In practice the `GITHUB_TOKEN` that Actions injects on its own
is enough - the first scheduled run produced all six tiles without any secret
being configured.

If those tiles ever disappear from the card, add a personal access token as a
repository secret named `METRICS_TOKEN` (scope: `read:user`); the workflow
prefers it over the default token. Running `scripts/cards.py` on a laptop with
no token at all is the case that falls back to fewer tiles, which is why local
builds and CI disagree about that file.
