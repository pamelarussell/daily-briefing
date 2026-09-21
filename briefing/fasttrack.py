"""Fast track: let an item in before its normal waiting period ends if it has exceptional traction.

Every source has a window (config `windows`) whose min_age_days is the normal "has it held up?" wait.
Collectors fetch down to `fast_track.min_age_days` instead; anything younger than its normal minimum
survives only if one of its signals clears the fast-track bar.
"""
from __future__ import annotations

from .models import Item

WINDOW_FOR_KIND = {"paper": "papers", "ai_paper": "ai_papers", "story": "news", "news": "news",
                   "hn": "hacker_news", "blog": "blogs"}


def _ft(cfg: dict) -> dict:
    return cfg.get("fast_track") or {}


def enabled(cfg: dict) -> bool:
    return bool(_ft(cfg).get("enabled", False))


def lower_bound(cfg: dict, window_name: str) -> float:
    """Youngest age (days) a collector should fetch for this window."""
    normal = float(cfg["windows"][window_name]["min_age_days"])
    if not enabled(cfg) or window_name == "papers":
        return normal
    return min(normal, float(_ft(cfg).get("min_age_days", normal)))


def normal_min(cfg: dict, item: Item) -> float:
    return float(cfg["windows"][WINDOW_FOR_KIND.get(item.kind, "news")]["min_age_days"])


def has_traction(item: Item, cfg: dict) -> bool:
    ft = _ft(cfg)
    s = item.signals
    hn_bar = ft.get("hn_min_points_ai", 600) if item.category_hint == "ai_general" else ft.get("hn_min_points_science", 400)
    return ((s.get("outlet_types") or 0) >= int(ft.get("min_outlet_types", 3))
            or (s.get("hn_points") or 0) >= int(hn_bar)
            or (s.get("hf_upvotes") or 0) >= int(ft.get("hf_min_upvotes", 150)))


def allowed(item: Item, cfg: dict, ref) -> bool:
    """True if the item is old enough, or young but fast-tracked (marks it so)."""
    age = item.age(ref)
    if age is None or age >= normal_min(cfg, item):
        item.extra.pop("fast_track", None)
        return True
    if enabled(cfg) and has_traction(item, cfg):
        item.extra["fast_track"] = True
        return True
    return False


def apply(items: list[Item], cfg: dict, ref) -> tuple[list[Item], int, int]:
    """Returns (kept, number fast-tracked, number held back as too young)."""
    kept = [i for i in items if allowed(i, cfg, ref)]
    fast = sum(1 for i in kept if i.extra.get("fast_track"))
    return kept, fast, len(items) - len(kept)
