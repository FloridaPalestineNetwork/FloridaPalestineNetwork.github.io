#!/usr/bin/env python3
"""Build event pages, event listings, and the CSS cache-busting version.

Source of truth: _events/*.md (YAML-ish front matter, filename = page slug).

Usage:
    python3 scripts/build_events.py               # regenerate files in the repo
    python3 scripts/build_events.py --check       # fail if repo output is stale
    python3 scripts/build_events.py --out _site   # build a deployable copy
    python3 scripts/build_events.py --today 2026-12-01   # deterministic run
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS_DIR = ROOT / "_events"
TEMPLATES_DIR = ROOT / "templates"
EVENT_OUT_DIR = ROOT / "event"
CSS_PATH = ROOT / "assets/css/styles.css"

GRID_INDENT = 16
NEXT_INDENT = 20
PAGE_REGIONS = {
    "index.html": ("next",),
    "events.html": ("upcoming", "past"),
    "tickets.html": ("upcoming",),
}
SKIP_WHEN_STAGING = {".git", ".github", ".gitignore", "_events", "templates", "scripts", "_site"}

MARKER_RE = re.compile(
    r"(?P<open>[ \t]*<!-- events:(?P<name>[a-z_]+):start -->\n)"
    r"(?P<body>.*?)"
    r"(?P<close>[ \t]*<!-- events:(?P=name):end -->)",
    re.S,
)
CSS_LINK_RE = re.compile(r'(href="/assets/css/styles\.css)(?:\?v=[0-9a-f]+)?(")')
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED = ("title", "date", "time", "location", "image")
OPTIONAL = {"ticket_url": "", "description": "", "published": "true"}


class BuildError(Exception):
    pass


def esc(value: str) -> str:
    return html.escape(value, quote=False)


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
        when = datetime.strptime(meta["date"], "%Y-%m-%d").date()
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
        raise BuildError(f"{path.name}: image must be an absolute site path")
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
        "description": match.group(2).strip(),
        "published": published_raw == "true",
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
        f'{pad}        <img src="{esc(event["image"])}"\n'
        f'{pad}            alt="{esc(event["title"])} cover image">\n'
        f'{pad}    </a>\n'
        f'{pad}</div>\n'
    )


def render_grid(events: list[dict], indent: int, empty_text: str) -> str:
    if not events:
        return f'{" " * indent}<p>{esc(empty_text)}</p>\n'
    return "\n".join(render_entry(event, indent) for event in events)


def render_event_page(event: dict, template: str, nav: str, footer: str, version: str) -> str:
    description = ""
    if event["description"]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", event["description"]) if p.strip()]
        description = "".join(f"            <p>{esc(p)}</p>\n" for p in paragraphs)

    ticket_block = ""
    if event["ticket_url"]:
        ticket_block = (
            '            <div class="button-container">\n'
            '                <div class="button">\n'
            f'                    <a href="{esc(event["ticket_url"])}" target="_blank">Buy Ticket</a>\n'
            "                </div>\n"
            "            </div>\n"
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
        ("{{TICKET_BLOCK}}", ticket_block),
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


def compute_outputs(version: str, today: date) -> tuple[dict[Path, str], list[dict], list[dict]]:
    events = load_events()
    published = [event for event in events if event["published"]]
    upcoming = sorted(
        (event for event in published if event["date"] >= today),
        key=lambda event: (event["date"], event["slug"]),
    )
    past = sorted(
        (event for event in published if event["date"] < today),
        key=lambda event: (event["date"], event["slug"]),
        reverse=True,
    )

    template = read_template("event.html")
    nav = read_template("nav.html")
    footer = read_template("footer.html")

    outputs: dict[Path, str] = {}
    for event in published:
        outputs[Path("event") / f"{event['slug']}.html"] = render_event_page(
            event, template, nav, footer, version
        )

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

    return outputs, upcoming, past


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
            for path in sorted(event_dir.glob("*.html")):
                if path.name not in expected:
                    path.unlink()
                    removed.append(f"event/{path.name}")
    return changed, removed


def check_outputs(outputs: dict[Path, str]) -> list[str]:
    problems: list[str] = []
    for rel, text in outputs.items():
        target = ROOT / rel
        if not target.is_file():
            problems.append(f"missing: {rel.as_posix()}")
        elif target.read_text(encoding="utf-8") != text:
            problems.append(f"out of date: {rel.as_posix()}")
    expected = {rel.name for rel in outputs if rel.parent == Path("event")}
    if EVENT_OUT_DIR.is_dir():
        for path in sorted(EVENT_OUT_DIR.glob("*.html")):
            if path.name not in expected:
                problems.append(f"stale (no data file): event/{path.name}")
    return problems


def parse_today(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build event pages and listings from _events/*.md")
    parser.add_argument("--check", action="store_true", help="verify generated files are up to date")
    parser.add_argument("--out", type=Path, metavar="DIR", help="write a deployable copy into DIR")
    parser.add_argument("--today", type=parse_today, default=date.today(), metavar="YYYY-MM-DD")
    args = parser.parse_args(argv)

    try:
        version = css_version()
        outputs, upcoming, past = compute_outputs(version, args.today)

        if args.check:
            problems = check_outputs(outputs)
            if problems:
                print("Generated event pages are out of date:", file=sys.stderr)
                for problem in problems:
                    print(f"  - {problem}", file=sys.stderr)
                print("\nRun: python3 scripts/build_events.py", file=sys.stderr)
                return 1
            print(f"OK: {len(outputs)} generated files are up to date.")
            return 0

        if args.out:
            destination = args.out if args.out.is_absolute() else ROOT / args.out
            stage_copy(destination)
            changed, removed = write_outputs(outputs, destination, prune=True)
            print(f"Staged {len(outputs)} files into {destination.relative_to(ROOT)}/")
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
        print(f"Events: {len(upcoming)} upcoming, {len(past)} past, today={args.today.isoformat()}")
        return 0
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
