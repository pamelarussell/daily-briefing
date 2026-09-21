"""Fetch readable text for the few chosen items so the writer works from real material, not headlines."""
from __future__ import annotations

import trafilatura

from .collectors.hackernews import points_for_url
from .models import Item
from .util import Http, clean_text, log

MAX_CHARS = {"paper": 3500, "ai_paper": 3500, "story": 7000, "news": 7000, "blog": 9000, "hn": 7000}
EXTRA_ARTICLE_CHARS = 3500      # each additional outlet's article
EXTRA_ARTICLES = 2              # how many other outlets' articles to fetch per item


def fetch_text(http: Http, url: str, limit: int) -> str:
    try:
        r = http.session.get(url, timeout=25, allow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
            return ""
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True)
        return clean_text(text or "", limit)
    except Exception as e:  # noqa: BLE001 — paywalls and bot-blocks are normal
        log.info("Could not fetch %s: %s", url, e)
        return ""


def material_for(http: Http, item: Item) -> str:
    """Source material block handed to the writer for one item.

    Besides the main source, fetch up to EXTRA_ARTICLES articles from other outlets that covered it:
    more independent material means fuller, better-attributed segments, and a second outlet often
    gets through when the first is paywalled.
    """
    limit = MAX_CHARS.get(item.kind, 6000)
    parts = []
    if item.kind in ("paper", "ai_paper"):
        if item.summary:
            parts.append("Abstract: " + item.summary)
        else:
            body = fetch_text(http, item.url, limit)
            if body:
                parts.append("Landing page text: " + body)
    else:
        body = fetch_text(http, item.url, limit)
        if body:
            parts.append(f"Article text from {item.source.split(',')[0]} (may be partial): " + body)
        elif item.summary:
            parts.append("Summary from the feed: " + item.summary)
    members = item.extra.get("members") or []
    others = [m for m in members if m.get("url") and m["url"] != item.url]
    got, used_sources = 0, set()
    for m in others:
        if got >= EXTRA_ARTICLES:
            break
        if m["source"] in used_sources:
            continue
        text = fetch_text(http, m["url"], EXTRA_ARTICLE_CHARS)
        if text:
            parts.append(f"Coverage by {m['source']} (may be partial): " + text)
            used_sources.add(m["source"])
            got += 1
    if len(members) > 1:
        parts.append("Other coverage of this story: " +
                     "; ".join(f"{m['source']}: \"{m['title']}\"" for m in members[:8] if m["url"] != item.url))
    for other in item.extra.get("also", [])[:4]:
        parts.append(f"Also appeared as: {other['source']}: \"{other['title']}\"")
    return "\n".join(parts) if parts else "(Only the headline is available.)"


def add_hn_points(http: Http, items: list[Item], limit: int = 80) -> int:
    """Look up Hacker News discussion for news/blog items that don't have it yet."""
    n = 0
    for it in items[:limit]:
        if it.kind in ("news", "blog", "story") and "hn_points" not in it.signals:
            pts, comments = points_for_url(http, it.url)
            if pts:
                it.signals["hn_points"] = pts
                it.signals["hn_comments"] = comments
                n += 1
    return n
