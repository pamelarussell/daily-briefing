# Bio + AI Briefing

A personal, AI-generated audio briefing that lands in your podcast app every morning. It covers
biotech and pharma, biology and biomedical research, computational biology and bioinformatics, AI
(in general and applied to biology and medicine), notable breakthroughs in other sciences, and the
occasional high-impact essay.

It deliberately runs **a few weeks behind**: an item only makes it in after it has had time to prove
itself — by being cited, covered by several outlets, or heavily discussed. Every episode's show notes
link the sources, say why each item was picked, and include the full transcript.

Everything runs for free on GitHub (GitHub Actions + GitHub Pages). You pay only for the AI calls:
roughly **$15/month** for a 12-minute daily episode (see [Costs](#costs)).

---

## Setup (about 20 minutes, once)

You need a GitHub account and two API keys.

### 1. Get your API keys

| Key | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | [platform.claude.com](https://platform.claude.com) → API keys | Add a few dollars of credit under Billing. Picks stories and writes the script. |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Add a few dollars of credit. Turns the script into speech. |
| `OPENALEX_API_KEY` *(optional, recommended)* | [openalex.org/settings/api](https://openalex.org/settings/api) | Free. Raises the daily limit for the paper database. The briefing works without it. |

### 2. Create the repository and upload the files

1. On GitHub, click **+** (top right) → **New repository**.
2. Name it, e.g. `bio-ai-briefing`. Choose **Public** (free GitHub Pages requires it — see
   [Privacy](#privacy-and-limits)). Don't add a README. Click **Create repository**.
3. On the next page, click **uploading an existing file**, then drag in **everything** from the
   unzipped folder (including the `.github` folder) and click **Commit changes**.

> **Mac users:** Finder hides folders whose names start with a dot. Press **Cmd + Shift + .** in
> Finder to show `.github` before dragging. If it still gets skipped, add it by hand: **Add file →
> Create new file**, type `.github/workflows/daily.yml` as the name, paste the contents of that
> file, and commit.

### 3. Add your keys as secrets

In the repository: **Settings → Secrets and variables → Actions → New repository secret**.
Add `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` (and `OPENALEX_API_KEY` if you got one), each with the
key as the value. Names must match exactly.

### 4. Turn on GitHub Pages

**Settings → Pages → Build and deployment → Source: GitHub Actions.**

### 5. Make the first episode

1. Open the **Actions** tab. If GitHub asks, click the button to enable workflows.
2. Click **Daily briefing** → **Run workflow** → leave mode as `full` → **Run workflow**.
3. Wait 5–10 minutes. Click the run to watch progress; the **Summary** page shows which sources
   loaded, what was picked and why, and the estimated cost.

Tip: a `dry_run` first (same menu) lists the candidates without spending anything on AI.

### 6. Subscribe in your podcast app

Your feed address is:

```
https://YOUR-GITHUB-USERNAME.github.io/REPOSITORY-NAME/feed.xml
```

(It's also printed at the end of each run summary and on
`https://YOUR-GITHUB-USERNAME.github.io/REPOSITORY-NAME/`.)

- **Apple Podcasts (iPhone):** Library → **⋯** → **Follow a Show by URL** → paste.
- **Apple Podcasts (Mac):** File → **Follow a Show by URL**.
- **Overcast:** **+** → **Add URL**.
- **Pocket Casts:** paste the address into the search box.
- Spotify can't subscribe to personal feeds.

From then on a new episode appears every morning. The workflow is scheduled for 07:23 UTC with a
backup at 10:23 UTC (GitHub sometimes starts scheduled runs late or skips one); the backup does
nothing if the first run already published.

---

## How items are vetted

| Source | What counts as "held up" | Normal age window |
|---|---|---|
| Journals and preprints (OpenAlex) | Citations, with a bonus for fast accumulation (top 200 per stream re-ranked) | 3 – 14 weeks |
| ML papers (Hugging Face Daily Papers) | Community upvotes (≥ 40) | 10 – 30 days |
| News (trade, science, general, and tech press) | Number of distinct outlet *types* covering the story | 10 – 30 days |
| Hacker News | Points (≥ 300 for AI, ≥ 150 for science/biology), attached to news coverage when there is some | 10 – 30 days |
| Blogs and essays (Derek Lowe, Eric Topol, Asimov Press, Owl Posting, …) | Hacker News discussion; the curated list itself | 7 – 30 days |

OpenAlex has dedicated streams for top journals: biomedical and clinical (Nature, Science, Cell,
NEJM, Lancet, JAMA, Nature Medicine, Science Translational Medicine), genomics and computational
biology (Nature Biotechnology, Methods, Genetics, Genome Biology, Genome Research, Cell Genomics, Cell
Systems, Nature Computational Science), and non-biological science (physical-science papers in
Nature, Science, PNAS, PRL, and the Nature physical-science journals).

**Outlet types.** News feeds are grouped as biotech/health trade, science press, general press, and
tech press. Five trade outlets covering the same deal count as one type of coverage; a finding covered
by the science press and the general press counts as two.

**Fast track.** An item as young as 5 days can get in if it has exceptional traction: coverage
across 3 outlet types, 600+ HN points (AI) or 400+ (science), or 150+ Hugging Face upvotes (see
`fast_track` in `config.yaml`). It is labeled as fast-tracked in the show notes.

**Hacker News links.** HN items are clustered with the news, so when HN discussed something the
press also covered, the news article becomes the source and the HN points become a signal. An HN item
linking to a social-media post with no news coverage is left out; one linking to a press release is
kept but presented as the organization's own claim. AI-lab blogs are not fed in directly: every lab's
announcements come in the same way, through HN and news coverage.

The same paper or story showing up in several places is merged, and its signals combined. An editor
model (Claude Sonnet 5) then picks 4–9 items using the brief in `config.yaml` (categories are
strongly preferred but optional), and a writer pass turns them into a script of up to 12 minutes
under strict rules: only facts from the fetched source text (the main source plus up to two other
outlets' articles), preprints, animal studies, and press releases labeled as such, claims attributed,
and the reason each item was picked stated. Nothing already covered is repeated.

**First few weeks:** news sites' feeds only show recent posts, so the briefing builds its own
archive as it runs. News fills in once the archive is 10 days old and reaches the full 30-day window
after a month. Papers, Hacker News, and blogs are unaffected.

---

## Tuning

Edit `config.yaml` on GitHub (open it, click the pencil). Changes apply on the next run.

- `editorial_brief` — plain-English description of what you want; the editor follows it.
- `episode.target_minutes`, `min_items`, `max_items` — length and density.
- `windows` — how old items must be (the "has it held up?" lag).
- `fast_track` — how much traction lets a younger item skip the lag.
- `signals` — thresholds for Hacker News points and Hugging Face upvotes.
- `openalex.streams` — which research areas and journals are searched.
- `feeds` — add or remove news sites and blogs (any RSS/Atom feed works); give news feeds an `outlet_type`.
- `tts.voice` — `marin` (default), `cedar`, `coral`, `sage`, and others.
- `models.effort` — `low` is cheaper; `high` thinks harder.

The model prompts live in `briefing/prompts.py` if you want to change the host's style.

Other run modes (Actions → Run workflow): `script_only` writes the script without making audio
(it appears on the run's Summary page), and `dry_run` lists candidates without AI calls. Every run
also saves a **run-details** download (candidate list, script, show notes) at the bottom of its
Summary page for 14 days.

---

## Costs

Estimated per day for a 12-minute episode:

| Step | Model | Approx. |
|---|---|---|
| Group news headlines into stories | Claude Haiku 4.5 | $0.10 – 0.20 |
| Pick the items | Claude Sonnet 5 | ~$0.10 |
| Write the script | Claude Sonnet 5 | ~$0.12 |
| Speech | OpenAI gpt-4o-mini-tts | ~$0.18 |

About $0.45–0.50/day, ~$15/month. Each run's summary prints its own estimate from actual token
counts. Shorter episodes or `effort: low` reduce it. GitHub hosting is free for public repositories.

---

## Privacy and limits

- **The repository is public** (required for free GitHub Pages). Your API keys stay secret, but
  the code, feed, and audio are readable by anyone who finds them. The feed is marked so Apple
  won't list it in its directory, and it isn't linked from anywhere.
- **AI can get things wrong.** The writer is instructed to use only the fetched source text, and
  every episode includes links and a transcript so you can check details before relying on them.
- **Paywalls:** when an article can't be fetched, the segment is based on the headline and feed
  summary only, and the script is told to keep it brief.
- **Early citations are an early signal**, not a verdict. Blog vetting is the weakest signal.

---

## Troubleshooting

- **The deploy step fails ("Pages site not found")** → Settings → Pages → Source must be
  *GitHub Actions* (step 4).
- **"ANTHROPIC_API_KEY is not set"** (or OPENAI) → check the secret's name in step 3.
- **"Permission denied" when saving or publishing** → Settings → Actions → General → Workflow
  permissions → *Read and write permissions*.
- **A feed shows `FAIL` in the run summary** → the site changed its feed address; fix or delete
  that line in `config.yaml`. One broken feed never stops the episode.
- **No episode today** → the summary says why (usually nothing new cleared the bar).
- **You'll get an email from GitHub** if a run fails; the run's log says which step.
- Episodes older than `keep_episodes` (default 30) are removed automatically.

Run it on your own computer (optional): `pip install -r requirements.txt`, set the same
environment variables, then `python -m briefing --mode script_only`.

---

## What's where

```
config.yaml                 all settings
briefing/collectors/        OpenAlex, Hugging Face, Hacker News, RSS
briefing/triage.py          groups news headlines into stories (outlet counts)
briefing/editor.py          merges duplicates, removes repeats, picks the episode
briefing/writer.py          writes the script      briefing/prompts.py  the prompts
briefing/tts.py             speech + joining audio briefing/feed.py     podcast feed + web page
.github/workflows/daily.yml the daily schedule
docs/                       the published site (feed.xml, index.html, cover.png)
state/                      memory of what's been covered (the news archive is kept as a release file)
```
