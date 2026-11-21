# Managing events

Event pages and the event listings are **generated** from small data files. Never edit
`event/*.html` (it is not even committed) — edit or add a file in `_events/`.

```
_events/2026-12-05-film_night_the_battle_of_algiers.md   ← one file per event
templates/event.html                                     ← page layout
templates/nav.html, templates/footer.html                ← shared chrome
scripts/build_events.py                                  ← the generator (stdlib only)
event/*.html                                             ← generated at build time, gitignored
```

`index.html` ("Next Event"), `events.html` (upcoming + past grids) and `tickets.html`
are filled between `<!-- events:...:start -->` / `<!-- events:...:end -->` markers when
the site is built. Do not remove those markers.

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

## Edit from your phone (Pages CMS)

The `.pages.yml` file in this repo configures [Pages CMS](https://pagescms.org), a hosted
editor that commits to this repository for you — no Git, no local build.

1. On your phone, open **https://app.pagescms.org** and sign in with GitHub.
2. Authorize/install the **Pages CMS GitHub App** on the `FloridaPalestineNetwork`
   account and grant it access to this repository (one-time).
3. Pick the repository, keep the branch on `main`, and open **Events**.
4. Create / edit / delete events, upload a cover image, and toggle **Published**.
   Choose **Save** — Pages CMS commits `_events/<slug>.md` (and any uploaded image).
5. The **Build events** GitHub Action rebuilds the pages and deploys — live in about
   a minute or two. Check the Actions tab (or the site) if it does not appear.

Notes for editors:

- The filename (and therefore the event URL) is generated automatically from the title,
  and renaming is disabled so published links never change.
- **Description** is plain text; leave a blank line between paragraphs.
- **Ticket link** must be a full `https://` URL. Leave it empty for free events.
- **Published** off = hidden everywhere (page, home page, events, tickets) without
  deleting the data.
- Uploaded images land in `assets/images/` and the field stores `/assets/images/<file>`;
  JPEG is best for photos, and keeping files under ~1&nbsp;MB keeps the site fast.

## Build

```bash
python3 scripts/build_events.py --out _site     # build the site into _site/ (normal use)
python3 scripts/build_events.py --check         # validate data + templates, write nothing
python3 scripts/build_events.py                 # optional: regenerate in place
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

- **GitHub Actions builds and deploys the site.** `.github/workflows/build.yml` runs
  `python3 scripts/build_events.py --out _site` on every push to `main`, on demand, and
  once a day (06:00 UTC) so events move from "upcoming" to "past" on time, then publishes
  `_site/` with GitHub Pages (Settings → Pages → Source: **GitHub Actions**).
- Because of that, **generated HTML is never committed** (see `.gitignore`) and editing
  `_events/*.md` — including from Pages CMS on your phone — is enough to publish.
  Pull requests run the same build so broken data fails before merge.
- The custom domain is configured in Settings → Pages (the `CNAME` file is just a
  leftover convenience and is harmless).
