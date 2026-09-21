"""Turn weeks of raw news headlines into a short list of stories, using breadth of coverage as a signal.

Hacker News items are clustered alongside the headlines. When HN discussed something a news outlet also
covered, the HN points attach to the news story and the story's lead link is a news article, not the
tweet or press release that happened to be submitted to HN.
"""
from __future__ import annotations

from .collectors.rss import OUTLET_TYPE_LABELS
from .llm import Claude
from .models import CATEGORIES, Item
from .prompts import TRIAGE_SYSTEM
from .util import domain_of, short_hash

MAX_STORIES = 45

SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "member_ids": {"type": "array", "items": {"type": "string"}},
                    "category": {"type": "string", "enum": [c for c in CATEGORIES if c != "blog_post"]},
                    "why": {"type": "string"},
                },
                "required": ["headline", "member_ids", "category", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}


def build_stories(result: dict, index: dict[str, Item], outlets_map: dict[str, tuple[str, str]]) -> list[Item]:
    """Convert the model's clusters into 'story' items with outlet and outlet-type counts."""
    stories = []
    for s in result.get("stories", [])[:MAX_STORIES]:
        members = [index[m] for m in dict.fromkeys(s.get("member_ids", [])) if m in index]
        news = sorted((m for m in members if m.kind != "hn"), key=lambda i: i.published or "9999")
        hn = [m for m in members if m.kind == "hn"]
        if not news:
            continue            # HN-only clusters stay as plain HN items in the pool
        outlets = list(dict.fromkeys(outlets_map.get(m.source, (m.source, ""))[0] for m in news))
        types = [t for t in dict.fromkeys(outlets_map.get(m.source, ("", ""))[1] for m in news) if t]
        lead = next((m for m in news if m.summary), news[0])
        signals = {"outlets": len(outlets), "outlet_types": len(types)}
        extra = {"why": s.get("why", ""),
                 "outlet_type_names": [OUTLET_TYPE_LABELS.get(t, t) for t in types],
                 "members": [{"source": m.source, "title": m.title, "url": m.url, "published": m.published}
                             for m in news[:8]],
                 "member_keys": [k for m in members for k in m.keys]}
        if hn:
            top = max(hn, key=lambda i: i.signals.get("hn_points", 0))
            signals["hn_points"] = top.signals.get("hn_points", 0)
            signals["hn_comments"] = top.signals.get("hn_comments", 0)
            extra["hn_url"] = top.extra.get("hn_url", "")
        stories.append(Item(
            id="story:" + short_hash(lead.url),
            kind="story",
            title=s.get("headline") or lead.title,
            url=lead.url,
            source=", ".join(outlets[:5]) + (f" +{len(outlets) - 5} more" if len(outlets) > 5 else ""),
            published=news[0].published,
            summary=lead.summary,
            category_hint=(s.get("category") or "").lower(),
            signals=signals,
            keys=list(dict.fromkeys(k for m in members for k in m.keys)),
            extra=extra,
        ))
    return stories


def cluster_news(claude: Claude, model: str, news: list[Item], hn_items: list[Item], cap: int,
                 outlets_map: dict[str, tuple[str, str]]) -> list[Item]:
    if not news:
        return []
    news = sorted(news, key=lambda i: i.published or "", reverse=True)[:cap]
    index: dict[str, Item] = {}
    lines = []
    for n, it in enumerate(news, 1):
        sid = f"n{n}"
        index[sid] = it
        otype = OUTLET_TYPE_LABELS.get(outlets_map.get(it.source, ("", ""))[1], "")
        lines.append(f"{sid} | {it.source}" + (f" ({otype})" if otype else "") +
                     f" | {(it.published or '')[:10]} | {it.title}")
    for n, it in enumerate(hn_items, 1):
        sid = f"h{n}"
        index[sid] = it
        lines.append(f"{sid} | Hacker News, {it.signals.get('hn_points', 0)} points, links to {domain_of(it.url)} "
                     f"| {(it.published or '')[:10]} | {it.title}")
    result = claude.json_call(
        label="news triage",
        model=model,
        system=TRIAGE_SYSTEM.format(max_stories=MAX_STORIES),
        user="Headlines:\n" + "\n".join(lines),
        schema=SCHEMA,
        max_tokens=16000,
    )
    return build_stories(result, index, outlets_map)
