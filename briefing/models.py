"""The one data type every stage passes around."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from .util import age_days, parse_date

# Every category, defined once: id -> (label for the script and show notes, meaning given to the models).
# The prompts (prompts.category_guide), the output schemas, and the show notes all read this table.
CATEGORY_INFO = {
    "biotech_pharma_news": ("Biotech & pharma", "industry, regulatory, clinical-trial and health-policy news."),
    "bio_biomed_research": ("Biology & biomedical research", "research findings in biology and biomedicine."),
    "compbio_bioinformatics": ("Computational biology & bioinformatics",
                               "computational biology, genomics methods, bioinformatics tools and resources."),
    "ai_for_bio_med": ("AI for biology & medicine", "AI applied to biology, medicine, biotech or pharma."),
    "ai_general": ("AI", "major general AI developments (models, research, policy)."),
    "mathematics": ("Mathematics",
                    "results and developments in mathematics itself, pure or applied (including probability and "
                    "statistics): new theorems and proofs, settled conjectures, major prizes. A result found or "
                    "checked by computer or AI belongs here when the mathematics is the story; when the AI system "
                    "is the story, use ai_general."),
    "science_breakthroughs": ("Science beyond biology",
                              "the non-biological sciences other than mathematics: physics, astronomy, chemistry, "
                              "materials, earth and climate science, and similar. Anything about biology or "
                              "medicine never goes here."),
    "blog_post": ("Worth reading", "essays and blog posts only (not papers, preprints or news articles)."),
}
CATEGORIES = list(CATEGORY_INFO)
CATEGORY_LABELS = {c: label for c, (label, _) in CATEGORY_INFO.items()}


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
