"""RSS/Atom feeds. Feeds only show recent posts, so every run adds them to a rolling archive;
the lag window is applied to that archive (see store.py)."""
from __future__ import annotations

import re
from datetime import timedelta

import feedparser

from ..classify import has_ai, has_bio
from ..models import Item
from ..util import Http, clean_text, iso, keys_for, normalize_url, parse_date, short_hash, strip_tracking

MAX_ENTRY_AGE_DAYS = 150


BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")


def _download(http: Http, url: str):
    accept = {"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"}
    try:
        return http.get(url, timeout=30, headers=accept)
    except Exception as e:  # noqa: BLE001
        if "403" not in str(e):
            raise
        return http.get(url, timeout=30, headers={**accept, "User-Agent": BROWSER_UA})


def fetch_feed(http: Http, feed: dict, ref) -> list[Item]:
    r = _download(http, feed["url"])
    parsed = feedparser.parse(r.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unreadable feed ({parsed.bozo_exception})")
    items = []
    for e in parsed.entries:
        link = strip_tracking(e.get("link") or "")
        title = clean_text(e.get("title"), 300)
        if not link or not title:
            continue
        if feed.get("exclude") and re.search(feed["exclude"], link):
            continue
        when = parse_date(e.get("published_parsed") or e.get("updated_parsed"))
        if when and (ref - when) > timedelta(days=MAX_ENTRY_AGE_DAYS):
            continue
        summary = clean_text(e.get("summary") or e.get("description") or "", 600)
        if feed.get("filter") == "bio_ai" and not (has_bio(title + " " + summary) or has_ai(title + " " + summary)):
            continue
        nu = normalize_url(link)
        items.append(Item(
            id="rss:" + short_hash(nu),
            kind=feed.get("kind", "news"),
            title=title,
            url=link,
            source=feed["name"],
            published=iso(when) if when else "",
            summary=summary,
            category_hint="blog_post" if feed.get("kind") == "blog" else "",
            keys=keys_for(url=link),
            extra={"first_seen": iso(ref)},
        ))
    return items


def collect(cfg: dict, http: Http, ref) -> tuple[list[Item], list[str]]:
    """Fetch every feed. Returns new/updated items and a feed-health report."""
    all_items: list[Item] = []
    health = []
    for feed in cfg.get("feeds", []):
        try:
            items = fetch_feed(http, feed, ref)
            all_items.extend(items)
            health.append(f"OK    {feed['name']}: {len(items)} items")
        except Exception as e:  # noqa: BLE001
            health.append(f"FAIL  {feed['name']}: {str(e)[:160]}  ({feed['url']})")
    return all_items, health
