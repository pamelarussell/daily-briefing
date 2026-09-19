"""Host audio files and the rolling archive as GitHub Release assets (via the preinstalled `gh` CLI)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .util import log

STATE_TAG = "state"


def on_github() -> bool:
    return bool(os.environ.get("GITHUB_REPOSITORY")) and shutil.which("gh") is not None


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {res.stderr.strip()[:400]}")
    return res


def download_state(state_dir: Path) -> bool:
    if not on_github():
        return False
    state_dir.mkdir(parents=True, exist_ok=True)
    res = _gh("release", "download", STATE_TAG, "--pattern", "archive.json.gz",
              "--dir", str(state_dir), "--clobber", check=False)
    if res.returncode != 0:
        log.info("No saved archive yet (first run?): %s", res.stderr.strip()[:200])
        return False
    return True


def upload_state(archive_path: Path) -> None:
    if not on_github():
        return
    if _gh("release", "view", STATE_TAG, check=False).returncode != 0:
        _gh("release", "create", STATE_TAG, "--title", "Pipeline state (do not delete)",
            "--notes", "Rolling archive of feed items used by the daily briefing. Safe to ignore.",
            "--prerelease")
    _gh("release", "upload", STATE_TAG, str(archive_path), "--clobber")


def publish_audio(tag: str, audio: Path, title: str, notes_md: str) -> None:
    if not on_github():
        log.info("Not on GitHub Actions; leaving audio at %s", audio)
        return
    notes = audio.with_suffix(".notes.md")
    notes.write_text(notes_md, encoding="utf-8")
    if _gh("release", "view", tag, check=False).returncode == 0:      # re-run on the same day
        _gh("release", "upload", tag, str(audio), "--clobber")
    else:
        _gh("release", "create", tag, str(audio), "--title", title, "--notes-file", str(notes))


def delete_release(tag: str) -> None:
    if on_github():
        _gh("release", "delete", tag, "--yes", "--cleanup-tag", check=False)
