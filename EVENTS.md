# Managing events

Event pages and the event listings are **generated** from small data files. Never edit
`event/*.html` (it is not even committed) — edit or add a file in `_events/`.

```
_events/2026-12-05-film_night_the_battle_of_algiers.md   ← one file per event
templates/event.html                                     ← page layout
templates/nav.html, templates/footer.html                ← shared chrome
scripts/build_events.py                                  ← the generator (stdlib only)
event/*.html                                             ← generated at build time, gitignored
event/*.ics                                              ← generated calendar files, gitignored
```

`index.html` ("Next Event"), `events.html` (upcoming + past grids) and `tickets.html`
are filled between `<!-- events:...:start -->` / `<!-- events:...:end -->` markers when
the site is built. Do not remove those markers.

## Add an event

Create `_events/<date>-<slug>.md`. The filename (without `.md`) **is the URL**, and it
must start with the event's date: `_events/2026-12-05-film_night_foo.md` →
`/event/2026-12-05-film_night_foo.html`. The build fails if the filename date and the
`date:` field disagree.

```markdown
---
title: Film Night - The Battle of Algiers
date: 2026-12-05          # YYYY-MM-DD; must match the filename prefix
time: 7:00 PM
location: Drunken Monkey
ticket_url: https://givebutter.com/palestine-film-night-Battle-of-Algiers
image: /assets/images/2026-12-05-film_night_the_battle_of_algiers.png
published: true
---

Optional description. Blank lines separate paragraphs and are shown on the event page.
```

Covers live **flat in `assets/images/`** and are named after the event file:
`assets/images/<date>-<slug>.jpg|png`. For a new event, upload any photo (the build
converts it to WebP, rotates and strips metadata).

| Field | Required | Notes |
|---|---|---|
| `title` | yes | Shown as the page `<h1>` and as `alt="<title> cover image"` in listings |
| `date` | yes | `YYYY-MM-DD`. Must equal the filename prefix |
| `time` | yes | Free text, e.g. `7:00 PM` |
| `location` | yes | Venue name |
| `image` | yes | Site-absolute path (`/assets/images/<date>-<slug>.ext`). Must exist in the repo |
| `ticket_url` | no | Must start with `https://`. Omit for free events (no Buy Ticket button) |
| `published` | no | `true` (default) or `false` to hide everywhere |
| `publish_at` | no | ISO date/time (`YYYY-MM-DDTHH:MM`, Orlando time) before which the event stays hidden |
| description | no | Markdown body after the front matter; plain paragraphs |

### Renaming an event

If you correct an event's date (and therefore its filename), add the old slug to
`_data/legacy_slugs.json` so the old URL keeps working:

```json
{
  "2026-11-20-film_night_the_battle_of_algiers": "2026-12-05-film_night_the_battle_of_algiers"
}
```

The build then emits a small redirect page at the old URL (meta refresh + `canonical`).
Entries whose target event no longer exists are skipped with a warning.

## What visitors see on an event page

- Title, date, time and venue
- **Buy Ticket** (only when `ticket_url` is set) and **Add to Calendar** buttons
- The cover image below the buttons

**Add to Calendar** downloads `/event/<slug>.ics`, a standard iCalendar file that opens
in Apple Calendar, Google Calendar, Outlook, etc. It uses the event date and `time`
(entries are 2 hours long — change `EVENT_DURATION` in `scripts/build_events.py` to
adjust). If `time` cannot be parsed the entry is created as an **all-day** event. The
file includes the venue, the ticket link and a link back to the event page.

## Scheduled publishing

`publish_at` keeps an event completely hidden (no page, no listings) until that moment,
then it appears automatically — handy for announcing on a set day/time.

```yaml
published: true
publish_at: 2026-12-01T09:00
```

- Times **without an offset are Orlando/Eastern**; `2026-12-01T14:00:00Z` is also accepted.
- `published: false` always wins (a manual hide beats the schedule).
- The site rebuilds **every 15 minutes**, so an event goes live on the next run after
  `publish_at` (GitHub's scheduler can occasionally run a few minutes late).
- The build reports how many events are waiting: `Events: … N hidden until publish_at`.
- Leave the field empty to publish immediately.

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
4. Create / edit / delete events, upload a cover image, toggle **Published**, and
   optionally set **Publish automatically at** to prepare an announcement in advance.
   Choose **Save** — Pages CMS commits `_events/<slug>.md` (and any uploaded image).
5. The **Build events** GitHub Action rebuilds the pages and deploys — live in about
   a minute or two. Check the Actions tab (or the site) if it does not appear.

Notes for editors:

- The filename (and therefore the event URL) is generated automatically from the date and
  title, and renaming is disabled so published links never change.
- **Description** is plain text; leave a blank line between paragraphs.
- **Ticket link** must be a full `https://` URL. Leave it empty for free events.
- **Published** off = hidden everywhere (page, home page, events, tickets) without
  deleting the data. **Publish automatically at** delays that visibility to a set time.
- Uploaded images land in `assets/images/` and the field stores `/assets/images/<file>`;
  the build converts covers to WebP automatically (see below), so upload the original.

## Build

```bash
python3 scripts/build_events.py --out _site     # build the site into _site/ (normal use)
python3 scripts/build_events.py --check         # validate data + templates, write nothing
python3 scripts/build_events.py                 # optional: regenerate in place
python3 scripts/build_events.py --today 2026-12-06        # pretend it is noon ET that day
python3 scripts/build_events.py --now 2026-12-01T09:00Z   # test publish_at boundaries
python3 scripts/build_events.py --out _site --no-webp     # skip image conversion
```

All date logic (upcoming/past and `publish_at`) uses **America/New_York**.

### Images

On `--out` builds, each visible event's cover is converted with Pillow
(`pip install -r requirements.txt`):

- **Rotation baked in** from EXIF (phone photos display the right way up)
- **Metadata stripped** (EXIF/GPS/camera notes are dropped)
- **Resized** to at most 1600px on the long edge and encoded as **WebP** (quality 82)
- **Never bigger:** if the WebP would be larger than the original (e.g. an already
  optimised PNG), the original is kept and referenced instead
- The listing **and the event page** are rewritten to the `.webp` path; originals stay
  in the repository
- Every `<img>` must have descriptive alt text — covers read "<event title> cover image",
  the logo "Florida Palestine Network logo", and social icons
  "Florida Palestine Network on Instagram / on X (Twitter) / on Facebook". **The build
  fails** if any generated page has an `<img>` without `alt`.

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
  **every 15 minutes**, so `publish_at` events appear on time and events roll from
  "upcoming" to "past" at Eastern midnight. It then publishes `_site/` with GitHub Pages
  (Settings → Pages → Source: **GitHub Actions**).
- Because of that, **generated HTML is never committed** (see `.gitignore`) and editing
  `_events/*.md` — including from Pages CMS on your phone — is enough to publish.
  Pull requests run the same build so broken data fails before merge.
- The custom domain is configured in Settings → Pages (the `CNAME` file is just a
  leftover convenience and is harmless).
