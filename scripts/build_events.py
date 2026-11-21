#!/usr/bin/env python3
"""Build event pages, event listings, and the CSS cache-busting version.

Source of truth: _events/*.md (YAML-ish front matter, filename = page slug).

The generated HTML is not committed: CI runs `--out _site` and deploys that.

Usage:
    python3 scripts/build_events.py --out _site   # build a deployable copy
    python3 scripts/build_events.py               # regenerate files in place (optional)
    python3 scripts/build_events.py --check       # validate data/templates, write nothing
    python3 scripts/build_events.py --today 2026-12-01   # deterministic run
"""

from __future__ import annotations

import argparse
import hashlib
import html
import posixpath
import re
import shutil
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # image optimisation is optional; the build still works without Pillow
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - exercised only when Pillow is absent
    Image = ImageOps = None

ROOT = Path(__file__).resolve().parent.parent
EVENTS_DIR = ROOT / "_events"
TEMPLATES_DIR = ROOT / "templates"
EVENT_OUT_DIR = ROOT / "event"
CSS_PATH = ROOT / "assets/css/styles.css"

SITE_TZ = ZoneInfo("America/New_York")
SITE_URL = "https://floridapalestinenetwork.org"
MAX_IMAGE_EDGE = 1600
WEBP_QUALITY = 82
EVENT_DURATION = timedelta(hours=2)

GRID_INDENT = 16
NEXT_INDENT = 20
PAGE_REGIONS = {
    "index.html": ("next",),
    "events.html": ("upcoming", "past"),
    "tickets.html": ("upcoming",),
}
SKIP_WHEN_STAGING = {".git", ".github", ".gitignore", ".pages.yml", "_events", "templates", "scripts", "_site"}

MARKER_RE = re.compile(
    r"(?P<open>[ \t]*<!-- events:(?P<name>[a-z_]+):start -->\n)"
    r"(?P<body>.*?)"
    r"(?P<close>[ \t]*<!-- events:(?P=name):end -->)",
    re.S,
)
CSS_LINK_RE = re.compile(r'(href="/assets/css/styles\.css)(?:\?v=[0-9a-f]+)?(")')
IMG_WITHOUT_ALT_RE = re.compile(r"<img\b(?![^>]*\balt=)", re.I)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED = ("title", "date", "time", "location", "image")
OPTIONAL = {"ticket_url": "", "description": "", "published": "true", "publish_at": ""}


class BuildError(Exception):
    pass


def esc(value: str) -> str:
    return html.escape(value, quote=False)


def parse_local_datetime(raw: str, name: str, field: str) -> datetime:
    """Parse an ISO date/time; values without an offset are interpreted as Orlando time."""
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace(" ", "T", 1))
        except ValueError:
            raise BuildError(f"{name}: {field} must be an ISO date/time (YYYY-MM-DDTHH:MM), got {raw!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SITE_TZ)
    return parsed


def webp_ref(image: str) -> str:
    root, ext = posixpath.splitext(image)
    if ext.lower() in (".jpg", ".jpeg", ".png"):
        return root + ".webp"
    return image


def human_date(when: date) -> str:
    return f"{when.strftime('%B')} {when.day}, {when.year}"


def css_version() -> str:
    return hashlib.sha256(CSS_PATH.read_bytes()).hexdigest()[:10]


def read_template(name: str) -> str:
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise BuildError(f"missing template: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def parse_event(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not match:
        raise BuildError(f"{path.name}: missing '---' front matter block")
    meta: dict[str, str] = {}
    for lineno, raw in enumerate(match.group(1).splitlines(), start=2):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise BuildError(f"{path.name}:{lineno}: expected 'key: value', got {raw!r}")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if key in meta:
            raise BuildError(f"{path.name}:{lineno}: duplicate key {key!r}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value

    unknown = sorted(set(meta) - set(REQUIRED) - set(OPTIONAL))
    missing = [f for f in REQUIRED if not meta.get(f)]
    if unknown:
        raise BuildError(f"{path.name}: unknown field(s): {', '.join(unknown)}")
    if missing:
        raise BuildError(f"{path.name}: missing required field(s): {', '.join(missing)}")

    try:
        # Accept plain dates and full ISO timestamps (some editors write the latter)
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", meta["date"].strip())
        if not date_match:
            raise ValueError
        when = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
    except ValueError:
        raise BuildError(f"{path.name}: date must be YYYY-MM-DD, got {meta['date']!r}")

    published_raw = meta.get("published", "true").strip().lower()
    if published_raw not in ("true", "false"):
        raise BuildError(f"{path.name}: published must be true or false")

    ticket = meta.get("ticket_url", "").strip()
    if ticket and not ticket.startswith("https://"):
        raise BuildError(f"{path.name}: ticket_url must start with https://")

    image = meta["image"].strip()
    if not image.startswith("/"):
        # Editors such as Pages CMS may write paths without the leading slash
        image = "/" + image
    if not (ROOT / image.lstrip("/")).is_file():
        raise BuildError(f"{path.name}: image not found: {image}")

    if not SLUG_RE.match(path.stem):
        raise BuildError(f"{path.name}: slug may only contain a-z, 0-9, dot, dash, underscore")

    return {
        "slug": path.stem,
        "title": meta["title"].strip(),
        "date": when,
        "date_human": human_date(when),
        "time": meta["time"].strip(),
        "location": meta["location"].strip(),
        "ticket_url": ticket,
        "image": image,
        "image_ref": image,
        "description": match.group(2).strip(),
        "published": published_raw == "true",
        "publish_at": (
            parse_local_datetime(meta["publish_at"], path.name, "publish_at")
            if meta.get("publish_at")
            else None
        ),
        "source": path.name,
    }


def load_events() -> list[dict]:
    if not EVENTS_DIR.is_dir():
        raise BuildError("_events/ directory not found")
    files = sorted(EVENTS_DIR.glob("*.md"))
    if not files:
        raise BuildError("_events/ contains no .md files")
    return [parse_event(path) for path in files]


def render_entry(event: dict, indent: int) -> str:
    pad = " " * indent
    return (
        f'{pad}<div class="event">\n'
        f'{pad}    <p>{event["date_human"]}</p>\n'
        f'{pad}    <a href="/event/{event["slug"]}.html">\n'
        f'{pad}        <img src="{esc(event["image_ref"])}"\n'
        f'{pad}            alt="{esc(event["title"])} cover image">\n'
        f'{pad}    </a>\n'
        f'{pad}</div>\n'
    )


def render_grid(events: list[dict], indent: int, empty_text: str) -> str:
    if not events:
        return f'{" " * indent}<p>{esc(empty_text)}</p>\n'
    return "\n".join(render_entry(event, indent) for event in events)


def ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\r\n", r"\n")
        .replace("\n", r"\n")
    )


def ics_fold(line: str) -> str:
    """Fold a content line to 75 octets, as required by RFC 5545."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts: list[str] = []
    current = ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " " + char
        else:
            current += char
    parts.append(current)
    return "\r\n".join(parts)


def event_start(event: dict) -> datetime | None:
    """Combine the event date with its free-text time; None when the time is unusable."""
    raw = event["time"].strip().upper().replace(".", "")
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M"):
        try:
            return datetime.combine(event["date"], datetime.strptime(raw, fmt).time(), tzinfo=SITE_TZ)
        except ValueError:
            continue
    return None


def render_ics(event: dict, now: datetime) -> str:
    page_url = f"{SITE_URL}/event/{event['slug']}.html"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Florida Palestine Network//Events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event['slug']}@floridapalestinenetwork.org",
        f"DTSTAMP:{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    ]

    start = event_start(event)
    if start:
        end = start + EVENT_DURATION
        lines.append(f"DTSTART:{start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(f"DTEND:{end.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    else:
        # No usable start time: publish an all-day entry rather than dropping the event
        lines.append(f"DTSTART;VALUE=DATE:{event['date']:%Y%m%d}")
        lines.append(f"DTEND;VALUE=DATE:{(event['date'] + timedelta(days=1)):%Y%m%d}")

    lines.append(f"SUMMARY:{ics_escape(event['title'])}")
    lines.append(f"LOCATION:{ics_escape(event['location'])}")

    description_parts: list[str] = []
    if event["description"]:
        description_parts.append(re.sub(r"\n\s*\n", "\n", event["description"]))
    if event["ticket_url"]:
        description_parts.append(f"Tickets: {event['ticket_url']}")
    description_parts.append(f"Details: {page_url}")
    lines.append(f"DESCRIPTION:{ics_escape(' '.join(description_parts))}")
    lines.append(f"URL:{page_url}")
    lines.extend(["STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR"])
    return "".join(f"{ics_fold(line)}\r\n" for line in lines)


def render_event_page(event: dict, template: str, nav: str, footer: str, version: str) -> str:
    description = ""
    if event["description"]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", event["description"]) if p.strip()]
        description = "".join(f"            <p>{esc(p)}</p>\n" for p in paragraphs)

    buttons: list[str] = []
    if event["ticket_url"]:
        buttons.append(
            '                <div class="button">\n'
            f'                    <a href="{esc(event["ticket_url"])}" target="_blank" rel="noopener">Buy Ticket</a>\n'
            "                </div>\n"
        )
    buttons.append(
        '                <div class="button">\n'
        f'                    <a href="/event/{event["slug"]}.ics" type="text/calendar" download>Add to Calendar</a>\n'
        "                </div>\n"
    )
    button_block = '            <div class="button-container">\n' + "".join(buttons) + "            </div>\n"

    image_block = (
        f'            <p><img src="{esc(event["image_ref"])}" '
        f'alt="{esc(event["title"])} cover image"></p>\n'
    )

    page = template
    for token, value in (
        ("{{SLUG}}", event["slug"]),
        ("{{TITLE}}", esc(event["title"])),
        ("{{DATE_HUMAN}}", event["date_human"]),
        ("{{TIME}}", esc(event["time"])),
        ("{{LOCATION}}", esc(event["location"])),
        ("{{CSS_VERSION}}", version),
        ("{{NAV}}", nav),
        ("{{FOOTER}}", footer),
        ("{{DESCRIPTION}}", description),
        ("{{BUTTON_BLOCK}}", button_block),
        ("{{IMAGE_BLOCK}}", image_block),
    ):
        page = page.replace(token, value)
    if "{{" in page:
        raise BuildError(f"{event['source']}: unresolved template token left in output")
    return page


def update_regions(text: str, page_name: str, regions: dict[str, str]) -> str:
    starts = re.findall(r"<!-- events:([a-z_]+):start -->", text)
    ends = re.findall(r"<!-- events:([a-z_]+):end -->", text)
    for name in sorted(set(starts) | set(ends) | set(regions)):
        if starts.count(name) != 1 or ends.count(name) != 1:
            raise BuildError(
                f"{page_name}: marker 'events:{name}' must appear exactly once "
                f"(found {starts.count(name)} start, {ends.count(name)} end)"
            )
        if name not in regions:
            raise BuildError(f"{page_name}: unexpected marker 'events:{name}'")

    seen: set[str] = set()

    def replace(match: re.Match) -> str:
        name = match.group("name")
        seen.add(name)
        return match.group("open") + regions[name] + match.group("close")

    updated = MARKER_RE.sub(replace, text)
    missing = sorted(set(regions) - seen)
    if missing:
        raise BuildError(f"{page_name}: missing marker(s): {', '.join(missing)}")
    return updated


def update_css_link(text: str, version: str, page_name: str) -> str:
    updated, count = CSS_LINK_RE.subn(rf"\1?v={version}\2", text)
    if count != 1:
        raise BuildError(f"{page_name}: expected exactly 1 stylesheet link, found {count}")
    return updated


def split_events(events: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Return (visible, scheduled) events; scheduled ones are unpublished until publish_at."""
    visible: list[dict] = []
    scheduled: list[dict] = []
    for event in events:
        if not event["published"]:
            continue
        if event["publish_at"] and now < event["publish_at"]:
            scheduled.append(event)
            continue
        visible.append(event)
    return visible, scheduled


def compute_outputs(
    version: str,
    now: datetime,
    webp_sources: set[str] | None = None,
) -> tuple[dict[Path, str], list[dict], list[dict], list[dict]]:
    webp_sources = webp_sources or set()
    today = now.astimezone(SITE_TZ).date()
    visible, scheduled = split_events(load_events(), now)

    for event in visible:
        event["image_ref"] = (
            webp_ref(event["image"]) if event["image"] in webp_sources else event["image"]
        )

    upcoming = sorted(
        (event for event in visible if event["date"] >= today),
        key=lambda event: (event["date"], event["slug"]),
    )
    past = sorted(
        (event for event in visible if event["date"] < today),
        key=lambda event: (event["date"], event["slug"]),
        reverse=True,
    )

    template = read_template("event.html")
    nav = read_template("nav.html")
    footer = read_template("footer.html")

    outputs: dict[Path, str] = {}
    for event in visible:
        outputs[Path("event") / f"{event['slug']}.html"] = render_event_page(
            event, template, nav, footer, version
        )
        outputs[Path("event") / f"{event['slug']}.ics"] = render_ics(event, now)

    regions_by_page = {
        "index.html": {
            "next": render_grid(upcoming[:1], NEXT_INDENT, "No upcoming events right now."),
        },
        "events.html": {
            "upcoming": render_grid(upcoming, GRID_INDENT, "No upcoming events right now."),
            "past": render_grid(past, GRID_INDENT, "No past events yet."),
        },
        "tickets.html": {
            "upcoming": render_grid(
                [event for event in upcoming if event["ticket_url"]],
                GRID_INDENT,
                "No tickets on sale right now.",
            ),
        },
    }

    for page_name, regions in regions_by_page.items():
        path = ROOT / page_name
        text = path.read_text(encoding="utf-8")
        outputs[Path(page_name)] = update_css_link(
            update_regions(text, page_name, regions), version, page_name
        )

    for path in sorted(ROOT.glob("*.html")):
        if path.name in regions_by_page:
            continue
        outputs[Path(path.name)] = update_css_link(
            path.read_text(encoding="utf-8"), version, path.name
        )

    for rel, text in outputs.items():
        if rel.suffix.lower() == ".html" and IMG_WITHOUT_ALT_RE.search(text):
            raise BuildError(f"{rel.as_posix()}: <img> without alt text")

    return outputs, upcoming, past, scheduled


def optimize_images(destination: Path, image_paths: list[str]) -> set[str]:
    """Write optimized .webp copies into destination and return the originals converted.

    Images are auto-rotated from EXIF, downscaled to MAX_IMAGE_EDGE, re-encoded as
    WebP (quality WEBP_QUALITY) and saved without any metadata.
    """
    if not image_paths:
        return set()
    if Image is None:
        print(
            "warning: Pillow is not installed - serving original images "
            "(run: pip install -r requirements.txt)",
            file=sys.stderr,
        )
        return set()

    converted: set[str] = set()
    for source in sorted(set(image_paths)):
        ref = webp_ref(source)
        if ref == source:
            continue
        src = ROOT / source.lstrip("/")
        dest = destination / ref.lstrip("/")
        try:
            with Image.open(src) as original:
                image = ImageOps.exif_transpose(original)
                if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                    image = image.convert("RGBA")
                else:
                    image = image.convert("RGB")
                image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.LANCZOS)
                dest.parent.mkdir(parents=True, exist_ok=True)
                # No exif/icc arguments -> metadata is dropped
                image.save(dest, "WEBP", quality=WEBP_QUALITY, method=6)
            if dest.stat().st_size >= src.stat().st_size:
                # Never ship a "compressed" file that is bigger than the original
                dest.unlink()
                continue
            converted.add(source)
        except (OSError, ValueError) as exc:
            print(f"warning: could not convert {source} to WebP: {exc}", file=sys.stderr)
    return converted


def stage_copy(destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if rel.parts and rel.parts[0] in SKIP_WHEN_STAGING:
            continue
        if rel.name == "project_note.md":
            continue
        if path.is_dir():
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

def write_outputs(outputs: dict[Path, str], target_root: Path, prune: bool) -> tuple[list[str], list[str]]:
    changed: list[str] = []
    for rel, text in outputs.items():
        target = target_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
            changed.append(rel.as_posix())

    removed: list[str] = []
    if prune:
        expected = {rel.name for rel in outputs if rel.parent == Path("event")}
        event_dir = target_root / "event"
        if event_dir.is_dir():
            for path in sorted(event_dir.iterdir()):
                if path.is_file() and path.suffix in (".html", ".ics") and path.name not in expected:
                    path.unlink()
                    removed.append(f"event/{path.name}")
    return changed, removed


def parse_today(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")


def parse_now(value: str) -> datetime:
    try:
        return parse_local_datetime(value, "argument", "--now")
    except BuildError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build event pages and listings from _events/*.md")
    parser.add_argument("--check", action="store_true", help="validate data and templates without writing anything")
    parser.add_argument("--out", type=Path, metavar="DIR", help="write a deployable copy into DIR")
    parser.add_argument(
        "--today",
        type=parse_today,
        default=None,
        metavar="YYYY-MM-DD",
        help="pretend it is noon on this date in America/New_York",
    )
    parser.add_argument(
        "--now",
        type=parse_now,
        default=None,
        metavar="ISO-DATETIME",
        help="evaluate publish_at at this instant (default: now in America/New_York)",
    )
    parser.add_argument(
        "--no-webp",
        action="store_true",
        help="keep the original image formats instead of converting covers to WebP",
    )
    args = parser.parse_args(argv)
    if args.check and args.out:
        parser.error("--check and --out cannot be combined")

    try:
        version = css_version()
        if args.now:
            now = args.now
        elif args.today:
            now = datetime.combine(args.today, time(12, 0), tzinfo=SITE_TZ)
        else:
            now = datetime.now(SITE_TZ)
        now_label = now.astimezone(SITE_TZ).strftime("%Y-%m-%d %H:%M %Z")

        destination: Path | None = None
        webp_sources: set[str] = set()
        if args.out:
            destination = args.out if args.out.is_absolute() else ROOT / args.out
            stage_copy(destination)
            if not args.no_webp:
                visible, _ = split_events(load_events(), now)
                webp_sources = optimize_images(destination, [event["image"] for event in visible])

        outputs, upcoming, past, scheduled = compute_outputs(version, now, webp_sources)

        if args.check:
            print(
                f"OK: {len(outputs)} files would be generated "
                f"({len(upcoming)} upcoming, {len(past)} past, {len(scheduled)} scheduled for later, "
                f"now={now_label})."
            )
            return 0

        if destination is not None:
            changed, removed = write_outputs(outputs, destination, prune=True)
            print(f"Staged {len(outputs)} files into {destination.relative_to(ROOT)}/")
            if webp_sources:
                print(f"Optimized {len(webp_sources)} cover image(s) to WebP.")
        else:
            changed, removed = write_outputs(outputs, ROOT, prune=True)
            print(f"Regenerated {len(outputs)} files (css v{version}).")

        if changed:
            print("Updated:")
            for rel in changed:
                print(f"  - {rel}")
        else:
            print("No changes were needed.")
        if removed:
            print("Removed (no matching data file):")
            for rel in removed:
                print(f"  - {rel}")
        print(
            f"Events: {len(upcoming)} upcoming, {len(past)} past, "
            f"{len(scheduled)} hidden until publish_at, now={now_label}"
        )
        return 0
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
