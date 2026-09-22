"""Load config.yaml, fill defaults, and work out where the feed lives."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

from .models import CATEGORIES

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "show": {"title": "Bio + AI Briefing", "author": "Personal briefing", "description": "",
             "language": "en-us", "timezone": "UTC", "site_url": ""},
    "editorial_brief": "",
    "episode": {"target_minutes": 12, "min_items": 4, "max_items": 9, "keep_episodes": 30,
                "required_categories": []},
    "windows": {
        "papers": {"min_age_days": 21, "max_age_days": 100},
        "ai_papers": {"min_age_days": 10, "max_age_days": 30},
        "news": {"min_age_days": 10, "max_age_days": 30},
        "blogs": {"min_age_days": 7, "max_age_days": 30},
        "hacker_news": {"min_age_days": 10, "max_age_days": 30},
    },
    "fast_track": {"enabled": True, "min_age_days": 5, "min_outlet_types": 3, "hn_min_points_ai": 600,
                   "hn_min_points_science": 400, "hf_min_upvotes": 150},
    "signals": {"hn_min_points_ai": 300, "hn_min_points_science": 150, "hf_min_upvotes": 40,
                "papers_per_stream": 25, "max_news_headlines": 4500},
    "openalex": {"types": "article|preprint", "streams": []},
    "feeds": [],
    "models": {"editor": "claude-sonnet-5", "triage": "claude-haiku-4-5-20251001", "effort": "medium"},
    "tts": {"model": "gpt-4o-mini-tts", "voice": "marin", "instructions": "", "bitrate": "64k"},
    "pricing": {},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, user)
    _check_required_categories(cfg["episode"])
    cfg["_paths"] = {
        "root": ROOT,
        "docs": ROOT / "docs",
        "state": ROOT / "state",
        "out": ROOT / "out",
    }
    cfg["_site"] = site_info(cfg)
    return cfg


def _check_required_categories(episode: dict) -> None:
    """Accept a single name or a list, and stop at startup on a mistyped name (it could never be satisfied)."""
    req = episode.get("required_categories") or []
    if isinstance(req, str):
        req = [req]
    episode["required_categories"] = list(req)
    unknown = [c for c in req if c not in CATEGORIES]
    if unknown:
        raise ValueError(f"episode.required_categories in config.yaml: unknown {unknown}; "
                         f"valid names are {', '.join(CATEGORIES)}")


def site_info(cfg: dict) -> dict:
    """Public URLs. On GitHub Actions these come from the repository name automatically."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")          # "owner/name"
    site_url = (cfg["show"].get("site_url") or "").strip()
    if not site_url and repo:
        owner, name = repo.split("/", 1)
        owner = owner.lower()
        if name.lower() == f"{owner}.github.io":
            site_url = f"https://{owner}.github.io/"
        else:
            site_url = f"https://{owner}.github.io/{name}/"
    if site_url and not site_url.endswith("/"):
        site_url += "/"
    return {
        "repo": repo,
        "site_url": site_url or "http://localhost:8000/",
        "feed_url": (site_url or "http://localhost:8000/") + "feed.xml",
        "release_base": f"https://github.com/{repo}/releases/download" if repo else "",
    }
