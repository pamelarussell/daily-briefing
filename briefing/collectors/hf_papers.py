"""Machine-learning papers from Hugging Face's community-curated Daily Papers, ranked by upvotes."""
from __future__ import annotations

import time
from datetime import timedelta

from ..classify import BIO
from ..models import Item
from ..util import Http, clean_text, keys_for

API = "https://huggingface.co/api/daily_papers"

# Stricter than the general BIO pattern: ML papers say "cell" and "health" loosely.
BIO_STRICT = (
    "protein", "molecul", "drug", "genom", "gene ", "genes", "single-cell", "clinical", "medical",
    "biomedical", "patholog", "radiolog", "biolog", "enzyme", "antibod", "dna", "rna", "chemistry",
    "chemical", "patient", "disease", "virtual cell", "biomolecul", "ehr", "microscop", "neuroscience",
)


def _is_bio(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in BIO_STRICT) and bool(BIO.search(t))


def collect(cfg: dict, http: Http, ref) -> tuple[list[Item], list[str]]:
    win = cfg["windows"]["ai_papers"]
    min_up = int(cfg["signals"]["hf_min_upvotes"])
    seen: dict[str, Item] = {}
    failures = 0
    day = ref - timedelta(days=win["max_age_days"])
    end = ref - timedelta(days=win["min_age_days"])
    while day <= end:
        try:
            data = http.get_json(API, params={"date": day.date().isoformat()}, timeout=30)
        except Exception:  # noqa: BLE001
            failures += 1
            data = []
        for e in data or []:
            p = e.get("paper") or {}
            arxiv_id = p.get("id") or ""
            up = int(p.get("upvotes") or 0)
            if not arxiv_id or up < min_up:
                continue
            title = clean_text(p.get("title") or e.get("title"), 300)
            summary = clean_text(p.get("summary") or e.get("summary"), 2500)
            cat = "ai_for_bio_med" if _is_bio(title + " " + summary) else "ai_general"
            it = Item(
                id=f"hf:{arxiv_id}",
                kind="ai_paper",
                title=title,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                source="arXiv (Hugging Face Daily Papers)",
                published=p.get("publishedAt") or e.get("publishedAt") or "",
                summary=summary,
                category_hint=cat,
                signals={"hf_upvotes": up},
                keys=keys_for(url=f"https://arxiv.org/abs/{arxiv_id}", arxiv=arxiv_id),
                extra={"hf_url": f"https://huggingface.co/papers/{arxiv_id}", "is_preprint": True,
                       "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])},
            )
            if arxiv_id not in seen or up > seen[arxiv_id].signals["hf_upvotes"]:
                seen[arxiv_id] = it
        day += timedelta(days=1)
        time.sleep(0.2)
    items = sorted(seen.values(), key=lambda i: i.signals["hf_upvotes"], reverse=True)
    bio = [i for i in items if i.category_hint == "ai_for_bio_med"][:15]
    gen = [i for i in items if i.category_hint == "ai_general"][:20]
    note = f"Hugging Face papers: {len(items)} ≥ {min_up} upvotes; kept {len(gen)} general + {len(bio)} bio/med"
    if failures:
        note += f" ({failures} day(s) failed to load)"
    return gen + bio, [note]
