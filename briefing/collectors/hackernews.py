"""Hacker News (via the Algolia HN Search API): what the technical community discussed heavily."""
from __future__ import annotations

from datetime import timedelta

from ..classify import classify_story
from ..models import Item
from ..util import Http, domain_of, keys_for, log, normalize_url

SEARCH = "https://hn.algolia.com/api/v1/search"
SEARCH_BY_DATE = "https://hn.algolia.com/api/v1/search_by_date"


def collect(cfg: dict, http: Http, ref) -> tuple[list[Item], list[str]]:
    win = cfg["windows"]["hacker_news"]
    sig = cfg["signals"]
    min_ai, min_sci = int(sig["hn_min_points_ai"]), int(sig["hn_min_points_science"])
    start = ref - timedelta(days=win["max_age_days"])
    end = ref - timedelta(days=win["min_age_days"])
    hits: dict[str, dict] = {}
    notes = []
    # Walk the window in 7-day chunks so no single query hits the API's 1,000-result cap.
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=7), end)
        params = {
            "tags": "story",
            "numericFilters": (f"created_at_i>={int(chunk_start.timestamp())},"
                               f"created_at_i<{int(chunk_end.timestamp())},points>={min(min_ai, min_sci)}"),
            "hitsPerPage": 1000,
        }
        try:
            data = http.get_json(SEARCH_BY_DATE, params=params)
            for h in data.get("hits", []):
                hits[h["objectID"]] = h
        except Exception as e:  # noqa: BLE001
            notes.append(f"Hacker News chunk {chunk_start.date()}: FAILED ({e})")
        chunk_start = chunk_end

    items: list[Item] = []
    for h in hits.values():
        url = h.get("url") or ""
        title = h.get("title") or ""
        if not url or not title:
            continue
        dom = domain_of(url)
        cat = classify_story(title, dom)
        if cat is None:
            continue
        points = int(h.get("points") or 0)
        if cat == "ai_general" and points < min_ai:
            continue
        if cat != "ai_general" and points < min_sci:
            continue
        items.append(Item(
            id=f"hn:{h['objectID']}",
            kind="hn",
            title=title,
            url=url,
            source=dom,
            published=h.get("created_at", ""),
            category_hint=cat,
            signals={"hn_points": points, "hn_comments": int(h.get("num_comments") or 0)},
            keys=keys_for(url=url) + [f"hn:{h['objectID']}"],
            extra={"hn_url": f"https://news.ycombinator.com/item?id={h['objectID']}"},
        ))
    # Keep the most-discussed stories per category so AI doesn't swamp everything else.
    caps = {"ai_general": 30, "ai_for_bio_med": 15, "bio_biomed_research": 20, "science_breakthroughs": 15}
    kept: list[Item] = []
    for cat, cap in caps.items():
        group = sorted((i for i in items if i.category_hint == cat),
                       key=lambda i: i.signals["hn_points"], reverse=True)
        kept.extend(group[:cap])
    notes.append(f"Hacker News: {len(hits)} stories ≥ threshold, {len(kept)} kept after topic filter")
    return kept, notes


def points_for_url(http: Http, url: str) -> tuple[int, int]:
    """Best (points, comments) for any HN submission of this exact URL, or (0, 0)."""
    target = normalize_url(url)
    if not target:
        return 0, 0
    query = target.split("://", 1)[-1]
    try:
        data = http.get_json(SEARCH, params={"query": query, "restrictSearchableAttributes": "url",
                                             "tags": "story", "hitsPerPage": 10}, timeout=20)
    except Exception as e:  # noqa: BLE001
        log.debug("HN lookup failed for %s: %s", url, e)
        return 0, 0
    best = (0, 0)
    for h in data.get("hits", []):
        if normalize_url(h.get("url") or "") == target:
            pts = int(h.get("points") or 0)
            if pts > best[0]:
                best = (pts, int(h.get("num_comments") or 0))
    return best
