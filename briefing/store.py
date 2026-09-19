"""Persistent state between daily runs.

state/archive.json.gz  – rolling archive of RSS items (kept in a GitHub release, not in git)
state/covered.json     – everything already featured, so nothing repeats
state/episodes.json    – metadata for the episodes currently in the feed
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path

from .models import Item
from .util import age_days, iso, norm_title, parse_date, title_similarity

ARCHIVE_MAX_DAYS = 150
COVERED_MAX_DAYS = 400


# ---------------------------------------------------------------- archive

def load_archive(path: Path) -> dict:
    if path.exists():
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "items" in data:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"meta": {}, "items": {}}


def save_archive(path: Path, archive: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(archive, f, separators=(",", ":"))


def merge_into_archive(archive: dict, items: list[Item], ref: datetime) -> int:
    archive.setdefault("meta", {}).setdefault("first_run", iso(ref))
    added = 0
    store = archive.setdefault("items", {})
    for it in items:
        old = store.get(it.id)
        if old:
            first_seen = old.get("extra", {}).get("first_seen") or iso(ref)
            d = it.to_dict()
            d["extra"]["first_seen"] = first_seen
            d["published"] = old.get("published") or d["published"]
            store[it.id] = d
        else:
            store[it.id] = it.to_dict()
            added += 1
    return added


def _item_date(d: dict) -> datetime | None:
    return parse_date(d.get("published")) or parse_date((d.get("extra") or {}).get("first_seen"))


def prune_archive(archive: dict, ref: datetime) -> int:
    store = archive.get("items", {})
    stale = [k for k, d in store.items()
             if (age_days(_item_date(d), ref) or 0) > ARCHIVE_MAX_DAYS]
    for k in stale:
        store.pop(k, None)
    return len(stale)


def days_of_history(archive: dict, ref: datetime) -> float:
    first = parse_date(archive.get("meta", {}).get("first_run"))
    return age_days(first, ref) or 0.0


def eligible_from_archive(archive: dict, kinds: set[str], window: dict, ref: datetime,
                          warmup: bool = True) -> list[Item]:
    """Archive items of the given kinds whose age is inside the window.

    During the first days (before the archive holds enough history) the minimum age is
    relaxed to the archive's own age, but never below 2 days.
    """
    min_age = float(window["min_age_days"])
    if warmup:
        min_age = min(min_age, max(2.0, days_of_history(archive, ref)))
    max_age = float(window["max_age_days"])
    out = []
    for d in archive.get("items", {}).values():
        if d.get("kind") not in kinds:
            continue
        a = age_days(_item_date(d), ref)
        if a is not None and min_age <= a <= max_age:
            item = Item.from_dict(d)
            if not item.published:
                item.published = (d.get("extra") or {}).get("first_seen", "")
            out.append(item)
    return out


# ---------------------------------------------------------------- covered

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


class Covered:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.keys = {k for e in entries for k in e.get("keys", [])}
        self.titles = [norm_title(e.get("title", "")) for e in entries]
        self.token_sets = [set(t.split()) for t in self.titles]

    @classmethod
    def load(cls, path: Path) -> "Covered":
        return cls(load_json(path, []))

    def contains(self, item: Item, sim: float = 0.88) -> bool:
        if any(k in self.keys for k in item.keys) or item.id in self.keys:
            return True
        t = norm_title(item.title)
        tokens = set(t.split())
        if not tokens:
            return False
        for old, old_tokens in zip(self.titles, self.token_sets):
            if not old_tokens or len(tokens & old_tokens) / len(tokens | old_tokens) < 0.5:
                continue  # cheap pre-filter before the slower character-level comparison
            if title_similarity(t, old) >= sim:
                return True
        return False

    def add(self, items: list[Item], ref: datetime) -> None:
        for it in items:
            keys = list(dict.fromkeys(it.keys + [it.id] + it.extra.get("member_keys", [])))
            self.entries.append({"title": it.title, "keys": keys, "date": ref.date().isoformat()})

    def recent_titles(self, ref: datetime, days: int = 30) -> list[str]:
        cutoff = (ref - timedelta(days=days)).date().isoformat()
        return [e["title"] for e in self.entries if e.get("date", "") >= cutoff]

    def save(self, path: Path, ref: datetime) -> None:
        cutoff = (ref - timedelta(days=COVERED_MAX_DAYS)).date().isoformat()
        save_json(path, [e for e in self.entries if e.get("date", "") >= cutoff])
