# Managing events

Event pages and the event listings are **generated** from small data files. You never
edit `event/*.html` by hand — edit or add a file in `_events/` and run the build.

```
_events/2026-12-05-film_night_the_battle_of_algiers.md   ← one file per event
templates/event.html                                     ← page layout
templates/nav.html, templates/footer.html                ← shared chrome
scripts/build_events.py                                  ← the generator (stdlib only)
event/*.html                                             ← GENERATED — do not edit
```

`index.html` ("Next Event"), `events.html` (upcoming + past grids) and `tickets.html`
are filled between `<!-- events:...:start -->` / `<!-- events:...:end -->` markers.
Do not remove those markers.

## Add an event

Create `_events/<slug>.md`. The filename (without `.md`) **is the URL**:
`_events/2026-12-05-film_night_foo.md` → `/event/2026-12-05-film_night_foo.html`.

```markdown
---
title: Film Night - The Battle of Algiers
date: 2026-12-05          # YYYY-MM-DD; drives sorting, upcoming/past and "Next Event"
time: 7:00 PM
location: Drunken Monkey
ticket_url: https://givebutter.com/palestine-film-night-Battle-of-Algiers
image: /assets/images/2026-11-20-film_night_the_battle_of_algiers/1.png
published: true
---

Optional description. Blank lines separate paragraphs and are shown on the event page.
```

| Field | Required | Notes |
|---|---|---|
| `title` | yes | Shown as the page `<h1>` and as `alt="<title> cover image"` in listings |
| `date` | yes | `YYYY-MM-DD`. Use the **real event date**; filenames may keep older dates |
| `time` | yes | Free text, e.g. `7:00 PM` |
| `location` | yes | Venue name |
| `image` | yes | Site-absolute path (`/assets/images/...`). Must exist in the repo |
| `ticket_url` | no | Must start with `https://`. Omit for free events (no Buy Ticket button) |
| `published` | no | `true` (default) or `false` to hide everywhere |
| description | no | Markdown body after the front matter; plain paragraphs |

## Edit / remove an event

- **Edit:** change the data file, run the build.
- **Hide without deleting:** set `published: false`.
- **Delete:** delete the data file, run the build (the generated page is removed).

## Build

```bash
python3 scripts/build_events.py            # regenerate event pages + listings
python3 scripts/build_events.py --check    # exit 1 if anything is out of date
python3 scripts/build_events.py --out _site  # build a deployable copy (local preview)
python3 scripts/build_events.py --today 2026-12-06   # testing: pretend it is that date
```

Local preview:

```bash
python3 scripts/build_events.py --out _site
python3 -m http.server 8765 --directory _site
```

The build also stamps every page's stylesheet link with `?v=<sha256 of styles.css>`,
so a CSS change always busts browser caches — no manual version bump needed.

Validation fails the build (exit code 2) on: missing/unknown front-matter fields,
invalid dates, non-`https` ticket URLs, missing image files, broken or duplicate
`events:` markers, and unresolved template tokens.

## How it publishes

- `main` currently deploys with **Settings → Pages → Deploy from a branch**, so the
  generated HTML committed in the repo is what goes live. Always run the build before
  committing (CI runs `--check` and fails if you forget).
- The `Build events` workflow (`.github/workflows/build.yml`) runs `--check` on every
  push/PR, and has a daily scheduled build so "upcoming" becomes "past" on time.
- To switch to building on GitHub's side (needed for a future phone admin UI that only
  commits `_events/*.md`): set **Settings → Pages → Source** to **GitHub Actions**, then
  add the repository variable `DEPLOY_TO_PAGES=true`. The `deploy` job in
  `build.yml` then builds `_site/` and publishes it. Re-check that the custom domain
  (`floridapalestinenetwork.org`) is still listed under Settings → Pages afterwards.
