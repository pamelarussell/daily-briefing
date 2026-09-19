"""Podcast RSS feed (with iTunes tags) plus a small index.html listing episodes."""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from pathlib import Path

from .util import parse_date

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("content", CONTENT)
ET.register_namespace("atom", ATOM)


def _sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = str(text)
    return el


def hms(seconds: float) -> str:
    s = int(round(seconds or 0))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_feed(cfg: dict, episodes: list[dict]) -> bytes:
    show, site = cfg["show"], cfg["_site"]
    rss = ET.Element("rss", {"version": "2.0"})
    ch = _sub(rss, "channel")
    _sub(ch, "title", show["title"])
    _sub(ch, "link", site["site_url"])
    _sub(ch, "language", show.get("language", "en-us"))
    _sub(ch, "description", show.get("description", "").strip())
    _sub(ch, f"{{{ATOM}}}link", href=site["feed_url"], rel="self", type="application/rss+xml")
    _sub(ch, f"{{{ITUNES}}}author", show.get("author", ""))
    _sub(ch, f"{{{ITUNES}}}image", href=site["site_url"] + "cover.png")
    cat = _sub(ch, f"{{{ITUNES}}}category", text="Science")
    _sub(cat, f"{{{ITUNES}}}category", text="Life Sciences")
    _sub(ch, f"{{{ITUNES}}}explicit", "false")
    _sub(ch, f"{{{ITUNES}}}type", "episodic")
    _sub(ch, f"{{{ITUNES}}}block", "Yes")   # keeps this personal feed out of public directories
    for ep in sorted(episodes, key=lambda e: e["date"], reverse=True):
        it = _sub(ch, "item")
        _sub(it, "title", ep["title"])
        _sub(it, "description", ep["description_text"])
        _sub(it, f"{{{CONTENT}}}encoded", ep["notes_html"])
        _sub(it, "enclosure", url=ep["audio_url"], length=ep["bytes"], type="audio/mpeg")
        _sub(it, "guid", ep["guid"], isPermaLink="false")
        _sub(it, "pubDate", format_datetime(parse_date(ep["published"])))
        _sub(it, f"{{{ITUNES}}}duration", hms(ep.get("seconds", 0)))
        _sub(it, f"{{{ITUNES}}}episodeType", "full")
        _sub(it, f"{{{ITUNES}}}explicit", "false")
    ET.indent(rss, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="utf-8")


def build_index(cfg: dict, episodes: list[dict]) -> str:
    show, site = cfg["show"], cfg["_site"]
    rows = []
    for ep in sorted(episodes, key=lambda e: e["date"], reverse=True):
        rows.append(
            f"<article><h2>{html.escape(ep['title'])}</h2>"
            f"<audio controls preload=\"none\" src=\"{html.escape(ep['audio_url'])}\"></audio>"
            f"{ep['notes_html']}</article>"
        )
    body = "\n".join(rows) or "<p>No episodes yet — the first one appears after the workflow runs.</p>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(show['title'])}</title>
<link rel="alternate" type="application/rss+xml" href="{site['feed_url']}">
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1f;--muted:#666;--line:#e6e2da;--accent:#2f6f5e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141414;--fg:#eee;--muted:#aaa;--line:#333;--accent:#7cc3ad}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 Georgia,serif;max-width:760px;margin:2rem auto;padding:0 1rem}}
h1{{font-family:system-ui,sans-serif}} h2{{font-family:system-ui,sans-serif;font-size:1.15rem}}
code{{background:var(--line);padding:.15rem .35rem;border-radius:4px;word-break:break-all}}
article{{border-top:1px solid var(--line);padding:1rem 0}} audio{{width:100%}} a{{color:var(--accent)}}
.muted{{color:var(--muted)}}
</style></head><body>
<h1>{html.escape(show['title'])}</h1>
<p class="muted">{html.escape(show.get('description', '').strip())}</p>
<p>Podcast feed (paste into your podcast app): <code>{site['feed_url']}</code></p>
{body}
</body></html>"""


def write_site(cfg: dict, episodes: list[dict]) -> None:
    docs: Path = cfg["_paths"]["docs"]
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "feed.xml").write_bytes(build_feed(cfg, episodes))
    (docs / "index.html").write_text(build_index(cfg, episodes), encoding="utf-8")
