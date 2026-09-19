"""Run the whole pipeline:  python -m briefing [--mode full|script_only|dry_run]

full         collect → pick → write → speak → publish (what the daily schedule runs)
script_only  everything except audio and publishing; writes the script to out/ (for testing prompts)
dry_run      collect and rank only; no AI calls, nothing saved (for checking sources)
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import feed, publish, store
from .collectors import hackernews, hf_papers, openalex, rss
from .config import load_config
from .editor import build_pool, candidate_line, choose
from .enrich import add_hn_points, material_for
from .llm import Claude, LLMError, Usage
from .models import Item
from .shownotes import build_notes
from .triage import cluster_news
from .tts import synthesize
from .util import Http, iso, log, now_utc
from .writer import write_script


class Report:
    """Collects everything worth showing in the GitHub Actions run summary."""

    def __init__(self):
        self.lines: list[str] = []

    def section(self, title: str, rows: list[str]) -> None:
        self.lines.append(f"\n### {title}\n")
        self.lines.extend(f"- {r}" for r in rows)
        for r in rows:
            log.info("  %s", r)

    def text(self, s: str) -> None:
        self.lines.append(s)
        log.info(s)

    def write(self, out_dir: Path) -> None:
        body = "\n".join(self.lines) + "\n"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "run_summary.md").write_text(body, encoding="utf-8")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(body)


def local_now(cfg: dict, ref: datetime) -> datetime:
    try:
        return ref.astimezone(ZoneInfo(cfg["show"].get("timezone") or "UTC"))
    except ZoneInfoNotFoundError:
        return ref.astimezone(ZoneInfo("UTC"))


def trim_blogs(blogs: list[Item], per_source: int = 5, total: int = 40) -> list[Item]:
    """Most-discussed first, then most recent; a few per blog so one prolific writer can't dominate."""
    blogs = sorted(blogs, key=lambda i: (i.signals.get("hn_points", 0), i.published or ""), reverse=True)
    counts: dict[str, int] = {}
    out = []
    for b in blogs:
        if counts.get(b.source, 0) >= per_source:
            continue
        counts[b.source] = counts.get(b.source, 0) + 1
        out.append(b)
        if len(out) >= total:
            break
    return out


def run(mode: str = "full") -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config()
    paths = cfg["_paths"]
    ref = now_utc()
    local = local_now(cfg, ref)
    date_slug = local.date().isoformat()
    date_spoken = local.strftime("%A, %B ") + str(local.day)
    report = Report()
    report.text(f"## {cfg['show']['title']} — {date_slug} ({mode})")
    http = Http()

    # ------------------------------------------------------------------ state
    archive_path = paths["state"] / "archive.json.gz"
    publish.download_state(paths["state"])       # read-only in dry runs; nothing is written back
    archive = store.load_archive(archive_path)
    covered = store.Covered.load(paths["state"] / "covered.json")
    episodes = store.load_json(paths["state"] / "episodes.json", [])

    # ------------------------------------------------------------------ collect
    log.info("Collecting…")
    rss_items, feed_health = rss.collect(cfg, http, ref)
    added = store.merge_into_archive(archive, rss_items, ref)
    pruned = store.prune_archive(archive, ref)
    history = store.days_of_history(archive, ref)
    report.section("Feeds", feed_health + [
        f"archive: {len(archive['items'])} items ({added} new, {pruned} expired); {history:.0f} days of history"])

    papers, notes_oa = openalex.collect(cfg, http, ref)
    note_alt = openalex.enrich_altmetric(papers, http)
    hf, notes_hf = hf_papers.collect(cfg, http, ref)
    hn, notes_hn = hackernews.collect(cfg, http, ref)
    news = store.eligible_from_archive(archive, {"news", "lab"}, cfg["windows"]["news"], ref)
    blogs = store.eligible_from_archive(archive, {"blog"}, cfg["windows"]["blogs"], ref, warmup=False)
    report.section("Sources", notes_oa + ([note_alt] if note_alt else []) + notes_hf + notes_hn + [
        f"News in window: {len(news)} headlines" + (" (warm-up: archive still filling)"
                                                    if history < cfg['windows']['news']['min_age_days'] else ""),
        f"Blog posts in window: {len(blogs)}",
    ])

    usage = Usage()
    claude = None
    stories: list[Item] = []
    if mode == "dry_run":
        stories = sorted(news, key=lambda i: i.published or "", reverse=True)[:40]
    else:
        try:
            claude = Claude(usage)
        except LLMError as e:
            report.text(f"**Stopped:** {e}")
            report.write(paths["out"])
            return 1
        try:
            stories = cluster_news(claude, cfg["models"]["triage"], news, int(cfg["signals"]["max_news_headlines"]))
            report.text(f"News triage: {len(news)} headlines → {len(stories)} stories")
        except Exception as e:  # noqa: BLE001 — fall back to raw headlines rather than failing the day
            report.text(f"News triage failed ({e}); using the most recent headlines instead")
            stories = sorted(news, key=lambda i: i.published or "", reverse=True)[:40]

    looked_up = add_hn_points(http, stories + blogs, limit=150)
    blogs = trim_blogs(blogs)
    pool, dropped = build_pool([papers, hf, hn, stories, blogs], covered)
    report.text(f"Candidate pool: {len(pool)} (after merging duplicates; {dropped} already covered; "
                f"HN points found for {looked_up} news/blog links)")

    paths["out"].mkdir(parents=True, exist_ok=True)
    (paths["out"] / "candidates.md").write_text(
        "\n\n".join(candidate_line(i, ref) for i in pool), encoding="utf-8")

    if mode == "dry_run":
        report.text("Dry run: see out/candidates.md (also printed below). Nothing was saved.")
        for i in pool[:60]:
            log.info(candidate_line(i, ref))
        report.write(paths["out"])
        return 0

    # From here on the archive is worth keeping even if a later step fails.
    store.save_archive(archive_path, archive)
    publish.upload_state(archive_path)

    if not pool:
        report.text("No eligible candidates today; no episode.")
        report.write(paths["out"])
        return 0

    # ------------------------------------------------------------------ edit + write
    chosen, angle = choose(claude, cfg, pool, covered, ref, date_spoken)
    if not chosen:
        report.text("The editor found nothing strong enough today; no episode.")
        report.write(paths["out"])
        return 0
    report.section("Chosen", [f"**{it.title}** ({it.source}) — {it.signals_text(ref)}. _{sel.get('reason', '')}_"
                              for it, sel in chosen])

    materials = {it.id: material_for(http, it) for it, _ in chosen}
    written = write_script(claude, cfg, chosen, materials, angle, ref, date_spoken)
    script = written["script"].strip()
    blurbs = {b["id"]: b["blurb"] for b in written.get("blurbs", [])}
    title = f"{local.strftime('%b')} {local.day}: {written['episode_title'].strip()}"
    notes_html, notes_text, notes_md = build_notes(chosen, blurbs, written["episode_summary"].strip(), script, ref)
    (paths["out"] / f"script-{date_slug}.txt").write_text(f"{title}\n\n{script}\n", encoding="utf-8")
    (paths["out"] / f"notes-{date_slug}.md").write_text(f"# {title}\n\n{notes_md}\n", encoding="utf-8")
    report.text(f"Script: {len(script.split())} words — “{title}”")

    pricing = cfg.get("pricing", {})
    if mode == "script_only":
        report.text(f"Script-only run (no audio, feed unchanged). Estimated model cost: ${usage.cost(pricing):.2f}")
        report.text(f"\n<details><summary>Script: {title}</summary>\n\n{script}\n\n</details>\n")
        report.write(paths["out"])
        return 0

    # ------------------------------------------------------------------ speak + publish
    audio_name = f"briefing-{date_slug}.mp3"
    audio_path = paths["out"] / audio_name
    info = synthesize(script, cfg["tts"], audio_path)
    minutes = info["seconds"] / 60
    tag = f"ep-{date_slug}"
    if publish.on_github():
        publish.publish_audio(tag, audio_path, title, notes_md)
        audio_url = f"{cfg['_site']['release_base']}/{tag}/{audio_name}"
    else:   # local preview: serve the audio next to the feed
        (paths["docs"] / "audio").mkdir(parents=True, exist_ok=True)
        shutil.copy(audio_path, paths["docs"] / "audio" / audio_name)
        audio_url = cfg["_site"]["site_url"] + "audio/" + audio_name

    record = {
        "date": date_slug, "tag": tag, "title": title, "published": iso(ref),
        "guid": f"{cfg['_site']['repo'] or 'local'}:{date_slug}",
        "audio_url": audio_url, "bytes": info["bytes"], "seconds": round(info["seconds"], 1),
        "description_text": notes_text, "notes_html": notes_html,
        "items": [{"id": it.id, "title": it.title, "url": it.url, "category": sel.get("category")}
                  for it, sel in chosen],
    }
    episodes = [e for e in episodes if e.get("date") != date_slug] + [record]
    episodes.sort(key=lambda e: e["date"])
    keep = int(cfg["episode"]["keep_episodes"])
    for old in episodes[:-keep]:
        publish.delete_release(old.get("tag", f"ep-{old['date']}"))
    episodes = episodes[-keep:]

    feed.write_site(cfg, episodes)
    covered.add([it for it, _ in chosen], ref)
    covered.save(paths["state"] / "covered.json", ref)
    store.save_json(paths["state"] / "episodes.json", episodes)

    cost = usage.cost(pricing) + minutes * float(pricing.get("tts_per_minute", 0))
    report.text(f"\n**Published:** {title} — {minutes:.1f} min, {info['bytes'] / 1e6:.1f} MB. "
                f"Estimated cost of this run: ${cost:.2f}")
    report.text(f"Feed: {cfg['_site']['feed_url']}")
    report.write(paths["out"])
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Make today's briefing.")
    parser.add_argument("--mode", choices=["full", "script_only", "dry_run"],
                        default=(os.environ.get("MODE") or "full").strip() or "full")
    args = parser.parse_args()
    sys.exit(run(args.mode))


if __name__ == "__main__":
    main()
