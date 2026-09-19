"""Write the spoken script from the chosen items and their source material."""
from __future__ import annotations

from .llm import Claude
from .models import CATEGORY_LABELS, Item
from .prompts import WRITER_SYSTEM

WORDS_PER_MINUTE = 150

SCHEMA = {
    "type": "object",
    "properties": {
        "episode_title": {"type": "string"},
        "episode_summary": {"type": "string"},
        "script": {"type": "string"},
        "blurbs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "blurb": {"type": "string"}},
                "required": ["id", "blurb"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["episode_title", "episode_summary", "script", "blurbs"],
    "additionalProperties": False,
}


def write_script(claude: Claude, cfg: dict, chosen: list[tuple[Item, dict]], materials: dict[str, str],
                 angle: str, ref, date_spoken: str) -> dict:
    words = int(cfg["episode"]["target_minutes"]) * WORDS_PER_MINUTE
    blocks = []
    for n, (it, sel) in enumerate(chosen, 1):
        blocks.append(
            f"=== ITEM {n} — id {it.id}\n"
            f"Segment type: {CATEGORY_LABELS.get(sel['category'], sel['category'])}\n"
            f"Title: {it.title}\n"
            f"Source: {it.source}; published {(it.published or '')[:10]}\n"
            + (f"Authors: {it.extra.get('authors')}" + (f" ({it.extra.get('institutions')})" if it.extra.get('institutions') else "") + "\n"
               if it.extra.get("authors") else "")
            + f"Evidence type: {'preprint (not peer reviewed)' if it.extra.get('is_preprint') else it.kind}\n"
            f"SIGNALS: {it.signals_text(ref)}\n"
            f"Editor's note on why it was chosen: {sel.get('reason', '')}\n"
            f"SOURCE MATERIAL:\n{materials.get(it.id, '(Only the headline is available.)')}\n"
        )
    user = (f"Today's through-line (optional to use): {angle}\n\n"
            f"Present the items in the order given unless another order flows better.\n\n" + "\n".join(blocks))
    return claude.json_call(
        label="writer",
        model=cfg["models"]["editor"],
        system=WRITER_SYSTEM.format(words=words, date_spoken=date_spoken),
        user=user,
        schema=SCHEMA,
        max_tokens=32000,
        effort=cfg["models"].get("effort"),
    )
