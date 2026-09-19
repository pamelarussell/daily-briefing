"""Turn weeks of raw news headlines into a short list of stories, using breadth of coverage as a signal."""
from __future__ import annotations

from .llm import Claude
from .models import CATEGORIES, Item
from .prompts import TRIAGE_SYSTEM
from .util import short_hash

MAX_STORIES = 30

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


def build_stories(result: dict, index: dict[str, Item]) -> list[Item]:
    """Convert the model's clusters into 'story' items with an outlet count."""
    stories = []
    for s in result.get("stories", [])[:MAX_STORIES]:
        members = [index[m] for m in dict.fromkeys(s.get("member_ids", [])) if m in index]
        if not members:
            continue
        members.sort(key=lambda i: i.published or "9999")
        outlets = list(dict.fromkeys(m.source for m in members))
        lead = next((m for m in members if m.summary), members[0])
        story = Item(
            id="story:" + short_hash(lead.url),
            kind="story",
            title=s.get("headline") or lead.title,
            url=lead.url,
            source=", ".join(outlets[:5]) + (f" +{len(outlets) - 5} more" if len(outlets) > 5 else ""),
            published=members[0].published,
            summary=lead.summary,
            category_hint=(s.get("category") or "").lower(),
            signals={"outlets": len(outlets)},
            keys=list(dict.fromkeys(k for m in members for k in m.keys)),
            extra={"why": s.get("why", ""),
                   "members": [{"source": m.source, "title": m.title, "url": m.url, "published": m.published}
                               for m in members[:8]],
                   "member_keys": [k for m in members for k in m.keys]},
        )
        stories.append(story)
    return stories


def cluster_news(claude: Claude, model: str, news: list[Item], cap: int) -> list[Item]:
    if not news:
        return []
    news = sorted(news, key=lambda i: i.published or "", reverse=True)[:cap]
    index: dict[str, Item] = {}
    lines = []
    for n, it in enumerate(news, 1):
        sid = f"n{n}"
        index[sid] = it
        lines.append(f"{sid} | {it.source} | {(it.published or '')[:10]} | {it.title}")
    result = claude.json_call(
        label="news triage",
        model=model,
        system=TRIAGE_SYSTEM.format(max_stories=MAX_STORIES),
        user="Headlines:\n" + "\n".join(lines),
        schema=SCHEMA,
        max_tokens=12000,
    )
    return build_stories(result, index)
