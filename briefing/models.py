"""The one data type every stage passes around."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from .util import age_days, parse_date

CATEGORIES = [
    "biotech_pharma_news",
    "bio_biomed_research",
    "compbio_bioinformatics",
    "ai_for_bio_med",
    "ai_general",
    "science_breakthroughs",
    "blog_post",
]

CATEGORY_LABELS = {
    "biotech_pharma_news": "Biotech & pharma",
    "bio_biomed_research": "Biology & biomedical research",
    "compbio_bioinformatics": "Computational biology & bioinformatics",
    "ai_for_bio_med": "AI for biology & medicine",
    "ai_general": "AI",
    "science_breakthroughs": "Science beyond biology",
    "blog_post": "Worth reading",
}


@dataclass
class Item:
    id: str                      # stable id, e.g. "oa:W123", "hn:456", "rss:ab12cd"
    kind: str                    # paper | ai_paper | news | lab | blog | hn | story
    title: str
    url: str
    source: str                  # journal, outlet, or domain
    published: str               # ISO datetime string ("" if unknown)
    summary: str = ""
    category_hint: str = ""
    signals: dict = field(default_factory=dict)
    keys: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def published_dt(self) -> datetime | None:
        return parse_date(self.published)

    def age(self, ref: datetime) -> float | None:
        return age_days(self.published_dt(), ref)

    def signals_text(self, ref: datetime) -> str:
        """Human-readable evidence that the item has 'held up' — shown to the editor and in show notes."""
        s = self.signals
        parts = []
        a = self.age(ref)
        if a is not None:
            weeks = a / 7
            parts.append(f"{a:.0f} days old" if a < 21 else f"{weeks:.0f} weeks old")
        if s.get("citations") is not None:
            parts.append(f"{s['citations']} citations")
        if s.get("altmetric"):
            parts.append(f"Altmetric score {s['altmetric']:.0f}")
        if s.get("news_mentions"):
            parts.append(f"{s['news_mentions']} news mentions (Altmetric)")
        if s.get("outlets"):
            t = f"covered by {s['outlets']} outlet" + ("s" if s["outlets"] != 1 else "")
            if s.get("outlet_types"):
                names = self.extra.get("outlet_type_names") or []
                t += (f" across {s['outlet_types']} outlet type" + ("s" if s["outlet_types"] != 1 else "")
                      + (f" ({', '.join(names)})" if names else ""))
            parts.append(t)
        if s.get("hf_upvotes"):
            parts.append(f"{s['hf_upvotes']} Hugging Face upvotes")
        if s.get("hn_points"):
            parts.append(f"{s['hn_points']} Hacker News points / {s.get('hn_comments', 0)} comments")
        if self.extra.get("is_preprint"):
            parts.append("preprint")
        if self.extra.get("fast_track"):
            parts.append("fast-tracked: younger than the usual waiting period, admitted on exceptional traction")
        if self.extra.get("link_type") == "press_release":
            parts.append("source is a press release (the organization's own claim), no independent news coverage found")
        return "; ".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Item":
        return Item(**{k: d.get(k) for k in Item.__dataclass_fields__ if k in d})
