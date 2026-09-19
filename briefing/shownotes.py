"""Show notes: every source link, the evidence it was picked on, and the full transcript."""
from __future__ import annotations

import html

from .models import CATEGORY_LABELS, Item


def _links(it: Item) -> list[tuple[str, str]]:
    links = [("source", it.url)]
    if it.extra.get("hf_url"):
        links.append(("Hugging Face", it.extra["hf_url"]))
    if it.extra.get("hn_url"):
        links.append(("Hacker News discussion", it.extra["hn_url"]))
    for m in (it.extra.get("members") or [])[1:4]:
        links.append((m["source"], m["url"]))
    return links


def build_notes(chosen: list[tuple[Item, dict]], blurbs: dict[str, str], summary: str,
                script: str, ref) -> tuple[str, str, str]:
    """Returns (html, plain_text, markdown)."""
    h = [f"<p>{html.escape(summary)}</p>", "<ol>"]
    t = [summary, ""]
    md = [summary, ""]
    for n, (it, sel) in enumerate(chosen, 1):
        label = CATEGORY_LABELS.get(sel.get("category", ""), "")
        blurb = blurbs.get(it.id, "")
        why = it.signals_text(ref)
        links = _links(it)
        h.append(
            "<li>"
            f"<strong>{html.escape(it.title)}</strong> — {html.escape(it.source)}"
            f"{' · ' + html.escape(label) if label else ''}<br>"
            f"{html.escape(blurb)}<br>"
            f"<em>Why it's here:</em> {html.escape(why)}<br>"
            + " · ".join(f'<a href="{html.escape(u)}">{html.escape(name)}</a>' for name, u in links)
            + "</li>"
        )
        t.append(f"{n}. {it.title} ({it.source})")
        if blurb:
            t.append(f"   {blurb}")
        t.append(f"   Why it's here: {why}")
        t.append(f"   {it.url}")
        md.append(f"{n}. **{it.title}** — {it.source}  \n   {blurb}  \n   _Why it's here:_ {why}  \n   "
                  + " · ".join(f"[{name}]({u})" for name, u in links))
    h.append("</ol>")
    paragraphs = [p.strip() for p in script.split("\n") if p.strip()]
    h.append("<h3>Transcript</h3>")
    h.extend(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    h.append("<p><em>AI-generated summary. Check the linked sources before relying on any detail.</em></p>")
    t.append("")
    t.append("AI-generated summary; check the linked sources before relying on any detail. "
             "Full transcript in the episode notes.")
    md.append("")
    md.append("<details><summary>Transcript</summary>\n\n" + "\n\n".join(paragraphs) + "\n\n</details>")
    return "\n".join(h), "\n".join(t), "\n".join(md)
