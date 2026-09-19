"""Text-to-speech with OpenAI, stitched into one MP3 with ffmpeg."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from .util import log

API = "https://api.openai.com/v1/audio/speech"
MAX_CHARS = 3000   # the API allows 4,096 characters / 2,000 tokens per request; stay well under


def split_for_tts(script: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split on paragraph boundaries, falling back to sentences, so chunks sound natural when joined."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]
    pieces: list[str] = []
    for p in paragraphs:
        if len(p) <= max_chars:
            pieces.append(p)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", p)
        buf = ""
        for s in sentences:
            if len(s) > max_chars:             # pathological run-on sentence: hard-split it
                if buf.strip():
                    pieces.append(buf.strip())
                    buf = ""
                pieces.extend(s[i:i + max_chars] for i in range(0, len(s), max_chars))
                continue
            if buf and len(buf) + len(s) + 1 > max_chars:
                pieces.append(buf.strip())
                buf = ""
            buf += s + " "
        if buf.strip():
            pieces.append(buf.strip())
    chunks: list[str] = []
    buf = ""
    for p in pieces:
        if buf and len(buf) + len(p) + 2 > max_chars:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def _speak(text: str, cfg: dict, api_key: str, dest: Path) -> None:
    body = {"model": cfg["model"], "voice": cfg["voice"], "input": text, "response_format": "mp3"}
    if cfg.get("instructions") and not cfg["model"].startswith("tts-1"):
        body["instructions"] = cfg["instructions"].strip()
    last = ""
    for attempt in range(8):
        r = requests.post(API, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=300)
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            return
        last = f"{r.status_code}: {r.text[:300]}"
        if r.status_code == 429 and "insufficient_quota" in r.text:
            raise RuntimeError(
                "OpenAI says this account has no available credit (insufficient_quota). Add prepaid "
                "credit at platform.openai.com → Settings → Billing, then re-run. Details: " + last)
        if r.status_code in (401, 403):
            raise RuntimeError("OpenAI rejected the API key (check the OPENAI_API_KEY secret). Details: " + last)
        if r.status_code in (429, 500, 502, 503, 504):
            try:
                wait = float(r.headers.get("retry-after", "")) + 1
            except ValueError:
                wait = min(20 * (attempt + 1), 120)
            log.warning("TTS %s, retrying in %.0fs — %s", r.status_code, wait, r.text[:200])
            time.sleep(wait)
            continue
        raise RuntimeError(f"OpenAI TTS error {last}")
    raise RuntimeError(f"OpenAI TTS kept failing after retries. Last response {last}")


def _duration_seconds(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def join_mp3s(parts: list[Path], dest: Path, bitrate: str = "64k") -> None:
    if shutil.which("ffmpeg"):
        listing = dest.with_suffix(".txt")
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
               "-ac", "1", "-ar", "24000", "-codec:a", "libmp3lame", "-b:a", bitrate, str(dest)]
        subprocess.run(cmd, check=True)
        listing.unlink(missing_ok=True)
    else:   # MP3 frames can be concatenated directly; players handle it fine
        with open(dest, "wb") as out:
            for p in parts:
                out.write(p.read_bytes())


def synthesize(script: str, tts_cfg: dict, dest: Path) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set (add it under Settings → Secrets and variables → Actions).")
    chunks = split_for_tts(script)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for n, chunk in enumerate(chunks):
            part = Path(tmp) / f"part{n:03d}.mp3"
            _speak(chunk, tts_cfg, api_key, part)
            parts.append(part)
        join_mp3s(parts, dest, tts_cfg.get("bitrate", "64k"))
    seconds = _duration_seconds(dest)
    if seconds is None:   # estimate from word count
        seconds = len(script.split()) / 150 * 60
    return {"chunks": len(chunks), "seconds": seconds, "bytes": dest.stat().st_size}
