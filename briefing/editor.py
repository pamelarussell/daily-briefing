"""Pool candidates from every source, merge duplicates, and let the editor model choose today's items."""
from __future__ import annotations

from .llm import Claude
from .models import CATEGORIES, Item
from .prompts import EDITOR_SYSTEM
from .store import Covered
from .util import clean_text, norm_title, title_similarity

# When the same thing shows up from several sources, keep the richest record as the base.
PRIORITY = {"paper": 0, "ai_paper": 1, "story": 2, "news": 3, "blog": 3, "hn": 4}
NUMERIC_SIGNALS = ("citations", "altmetric", "news_mentions", "outlets", "outlet_types", "hf_upvotes", "hn_points",
                   "hn_comments")

SCHEMA = {
    "type": "object",
    "properties": {
        "selections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "reason": {"type": "string"},
                },
                "required": ["id", "category", "reason"],
                "additionalProperties": False,
            },
        },
        "angle": {"type": "string"},
    },
    "required": ["selections", "angle"],
    "additionalProperties": False,
}


def _absorb(base: Item, other: Item) -> None:
    for k in NUMERIC_SIGNALS:
        if other.signals.get(k) is not None:
            base.signals[k] = max(base.signals.get(k) or 0, other.signals[k])
    base.keys = list(dict.fromkeys(base.keys + other.keys))
    also = base.extra.setdefault("also", [])
    also.append({"source": other.source, "title": other.title, "url": other.url})
    if not base.summary and other.summary:
        base.summary = other.summary
    if other.extra.get("hn_url"):
        base.extra.setdefault("hn_url", other.extra["hn_url"])
    if not base.category_hint:
        base.category_hint = other.category_hint
    if other.extra.get("outlet_type_names") and len(other.extra["outlet_type_names"]) > len(base.extra.get("outlet_type_names") or []):
        base.extra["outlet_type_names"] = other.extra["outlet_type_names"]
    if other.kind == "story" and other.extra.get("members") and not base.extra.get("members"):
        base.extra["members"] = other.extra["members"]


def _similar_titles(a: str, b: str) -> bool:
    ta, tb = set(norm_title(a).split()), set(norm_title(b).split())
    if not ta or not tb or len(ta & tb) / len(ta | tb) < 0.5:
        return False
    return title_similarity(a, b) >= 0.85


def merge_duplicates(items: list[Item]) -> list[Item]:
    items = sorted(items, key=lambda i: PRIORITY.get(i.kind, 9))
    kept: list[Item] = []
    key_owner: dict[str, Item] = {}
    for it in items:
        owner = next((key_owner[k] for k in it.keys if k in key_owner), None)
        if owner is None:
            owner = next((k for k in kept if _similar_titles(k.title, it.title)), None)
        if owner is not None:
            _absorb(owner, it)
            for k in it.keys:
                key_owner.setdefault(k, owner)
            continue
        kept.append(it)
        for k in it.keys:
            key_owner.setdefault(k, it)
    return kept


def build_pool(sources: list[list[Item]], covered: Covered) -> tuple[list[Item], int]:
    merged = merge_duplicates([i for group in sources for i in group])
    fresh = [i for i in merged if not covered.contains(i)]
    return fresh, len(merged) - len(fresh)


KIND_LABEL = {"paper": "paper", "ai_paper": "ML paper", "story": "news story", "news": "news",
              "blog": "blog/essay", "hn": "HN-discussed link"}


def candidate_line(it: Item, ref) -> str:
    who = it.extra.get("authors", "")
    where = it.extra.get("institutions", "")
    meta = " | ".join(x for x in [
        it.category_hint or "?", KIND_LABEL.get(it.kind, it.kind), it.source, (it.published or "")[:10],
        it.signals_text(ref), (who + (f" ({where})" if where else "")) if who else "",
    ] if x)
    summary = clean_text(it.summary or it.extra.get("why", ""), 300)
    return f"[{it.id}] {meta}\n    {it.title}" + (f" — {summary}" if summary else "")


def choose(claude: Claude, cfg: dict, pool: list[Item], covered: Covered, ref, date_spoken: str) -> tuple[list[tuple[Item, dict]], str]:
    ep = cfg["episode"]
    by_id = {i.id: i for i in pool}
    recent = covered.recent_titles(ref, days=45)
    user = (
        f"Today is {date_spoken}.\n\n"
        f"Recently covered (avoid repeats):\n" + ("\n".join(f"- {t}" for t in recent[-150:]) or "- (nothing yet)") +
        f"\n\nCandidates ({len(pool)}):\n\n" + "\n".join(candidate_line(i, ref) for i in pool)
    )
    result = claude.json_call(
        label="editor",
        model=cfg["models"]["editor"],
        system=EDITOR_SYSTEM.format(brief=cfg["editorial_brief"].strip(), min_items=ep["min_items"],
                                    max_items=ep["max_items"]),
        user=user,
        schema=SCHEMA,
        max_tokens=16000,
        effort=cfg["models"].get("effort"),
    )
    chosen: list[tuple[Item, dict]] = []
    seen = set()
    for sel in result.get("selections", []):
        it = by_id.get(sel.get("id", ""))
        if not it or it.id in seen:
            continue
        seen.add(it.id)
        sel["category"] = (sel.get("category") or it.category_hint or "science_breakthroughs").lower()
        chosen.append((it, sel))
        if len(chosen) >= int(ep["max_items"]):
            break
    return chosen, result.get("angle", "")
