"""Papers and preprints from OpenAlex, ranked by citations accumulated inside the lag window."""
from __future__ import annotations

import math
import os
import re
from datetime import timedelta

from ..models import Item
from ..util import Http, clean_text, keys_for, log, normalize_doi

BASE = "https://api.openalex.org/works"
SELECT = ",".join([
    "id", "doi", "display_name", "publication_date", "cited_by_count", "type",
    "primary_location", "abstract_inverted_index", "primary_topic", "authorships", "ids",
])


def reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _people(authorships: list) -> tuple[str, str]:
    """('First Author et al.', 'Institution A; Institution B') — enough context for a spoken intro."""
    if not authorships:
        return "", ""
    names = [(a.get("author") or {}).get("display_name", "") for a in authorships]
    first = names[0] if names else ""
    who = f"{first} et al." if len(names) > 1 else first
    insts = []
    for a in (authorships[0], authorships[-1]):
        for inst in a.get("institutions", []) or []:
            n = inst.get("display_name")
            if n and n not in insts:
                insts.append(n)
    return who, "; ".join(insts[:3])


def work_to_item(w: dict, stream: dict) -> Item:
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {}).get("display_name") or ""
    doi = normalize_doi(w.get("doi"))
    url = f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or w.get("id", ""))
    arxiv = ""
    ids = w.get("ids") or {}
    if doi.startswith("10.48550/arxiv."):
        arxiv = doi.split("arxiv.", 1)[1]
    who, insts = _people(w.get("authorships") or [])
    topic = (w.get("primary_topic") or {}).get("display_name", "")
    item = Item(
        id="oa:" + w.get("id", "").rsplit("/", 1)[-1],
        kind="paper",
        title=clean_text(w.get("display_name"), 300),
        url=url,
        source=src or ("preprint" if w.get("type") == "preprint" else "journal"),
        published=(w.get("publication_date") or "") + ("T00:00:00+00:00" if w.get("publication_date") else ""),
        summary=clean_text(reconstruct_abstract(w.get("abstract_inverted_index")), 2500),
        category_hint=stream.get("category", ""),
        signals={"citations": int(w.get("cited_by_count") or 0)},
        keys=keys_for(url=url, doi=doi, arxiv=arxiv) + ([f"pmid:{ids['pmid']}"] if ids.get("pmid") else []),
        extra={"authors": who, "institutions": insts, "topic": topic, "stream": stream.get("name", ""),
               "is_preprint": w.get("type") == "preprint"},
    )
    return item


def paper_score(item: Item, ref) -> float:
    """Citations, with a bonus for citation *velocity* so a 3-week-old paper isn't crowded out by 3-month-old ones."""
    cites = item.signals.get("citations", 0)
    age = max(item.age(ref) or 30, 14)
    velocity = cites / (age / 30.0)
    return math.log1p(cites) + 0.6 * math.log1p(velocity)


def collect(cfg: dict, http: Http, ref) -> tuple[list[Item], list[str]]:
    win = cfg["windows"]["papers"]
    start = (ref - timedelta(days=win["max_age_days"])).date().isoformat()
    end = (ref - timedelta(days=win["min_age_days"])).date().isoformat()
    per_stream = int(cfg["signals"]["papers_per_stream"])
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    types = cfg["openalex"].get("types", "article|preprint")
    out: dict[str, Item] = {}
    notes: list[str] = []
    for stream in cfg["openalex"].get("streams", []):
        filt = (f"from_publication_date:{start},to_publication_date:{end},type:{types},"
                f"is_retracted:false,{stream['filter']}")
        # Fetch a deep slice (200 = OpenAlex's page maximum) so the velocity re-ranking below can
        # surface young, fast-rising papers that aren't yet in the raw top by total citations.
        params = {"filter": filt, "sort": "cited_by_count:desc", "per_page": 200, "select": SELECT}
        if stream.get("search"):
            if not api_key:
                notes.append(f"OpenAlex '{stream['name']}': skipped (search queries need OPENALEX_API_KEY)")
                continue
            params["search"] = stream["search"]
        if api_key:
            params["api_key"] = api_key
        try:
            data = http.get_json(BASE, params=params, timeout=60)
        except Exception as e:  # noqa: BLE001 — one bad stream shouldn't sink the run
            notes.append(f"OpenAlex '{stream['name']}': FAILED ({e})")
            log.warning("OpenAlex stream %s failed: %s", stream.get("name"), e)
            continue
        items = [work_to_item(w, stream) for w in data.get("results", []) if w.get("display_name")]
        items = [i for i in items if (i.age(ref) or 0) >= 0]
        items.sort(key=lambda i: paper_score(i, ref), reverse=True)
        kept = 0
        for it in items:
            if it.id in out:
                continue
            out[it.id] = it
            kept += 1
            if kept >= per_stream:
                break
        note = f"OpenAlex '{stream['name']}': {len(items)} found, {kept} kept"
        missing = _unmatched_issns(stream["filter"], data.get("results", []))
        if missing:
            note += f" — no results for ISSN(s) {', '.join(missing)} (check the ISSN, or the journal had nothing in the window)"
        notes.append(note)
    return list(out.values()), notes


def _unmatched_issns(filt: str, works: list[dict]) -> list[str]:
    """ISSNs named in a journal filter that no returned work came from (usually a typo)."""
    m = re.search(r"primary_location\.source\.issn:([0-9Xx|\-]+)", filt)
    if not m:
        return []
    wanted = [i.upper() for i in m.group(1).split("|") if i]
    seen = set()
    for w in works:
        src = (w.get("primary_location") or {}).get("source") or {}
        seen.update(i.upper() for i in (src.get("issn") or []))
        if src.get("issn_l"):
            seen.add(src["issn_l"].upper())
    return [i for i in wanted if i not in seen]


def enrich_altmetric(items: list[Item], http: Http, limit: int = 60) -> str:
    """Optional: attention scores for papers. Needs an Altmetric API key (institutional/licensed)."""
    key = os.environ.get("ALTMETRIC_API_KEY", "").strip()
    if not key:
        return ""
    n = 0
    for it in items[:limit]:
        doi = next((k[4:] for k in it.keys if k.startswith("doi:")), "")
        if not doi:
            continue
        try:
            r = http.session.get(f"https://api.altmetric.com/v1/doi/{doi}", params={"key": key}, timeout=20)
            if r.status_code != 200:
                continue
            d = r.json()
            it.signals["altmetric"] = float(d.get("score") or 0)
            if d.get("cited_by_msm_count"):
                it.signals["news_mentions"] = int(d["cited_by_msm_count"])
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return f"Altmetric: scores added for {n} papers"
