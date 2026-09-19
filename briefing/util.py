"""Small shared helpers: HTTP with retries, dates, URL/DOI normalization, text cleanup."""
from __future__ import annotations

import difflib
import hashlib
import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("briefing")

USER_AGENT = "Mozilla/5.0 (compatible; bio-ai-briefing/1.0; personal podcast feed reader)"


# ---------------------------------------------------------------- dates

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value: Any) -> datetime | None:
    """Parse ISO strings, 'YYYY-MM-DD', unix seconds, or time.struct_time into aware UTC datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, time.struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc)
    s = str(value).strip()
    try:
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def age_days(when: datetime | None, ref: datetime) -> float | None:
    if when is None:
        return None
    return (ref - when).total_seconds() / 86400.0


def iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).isoformat() if dt else ""


# ---------------------------------------------------------------- text

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(s: str | None, limit: int | None = None) -> str:
    """Strip HTML tags/entities, collapse whitespace, and truncate at a word boundary."""
    if not s:
        return ""
    s = html.unescape(_TAG_RE.sub(" ", s))
    s = _WS_RE.sub(" ", s).strip()
    if limit and len(s) > limit:
        cut = s[:limit].rsplit(" ", 1)[0]
        s = cut.rstrip(",;:") + "…"
    return s


def norm_title(t: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (t or "").lower()))


def title_similarity(a: str, b: str) -> float:
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def short_hash(s: str, n: int = 10) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


# ---------------------------------------------------------------- URLs and identifiers

_TRACKING_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "cmpid", "src", "source", "rss",
    "utm", "cmp", "ncid", "sr_share", "share", "s", "_hsenc", "_hsmi", "mkt_tok", "trk",
}


def normalize_url(u: str | None) -> str:
    """Canonical form used for de-duplication (not for fetching)."""
    if not u:
        return ""
    u = u.strip()
    try:
        p = urlparse(u)
    except ValueError:
        return u
    if not p.scheme:
        p = urlparse("https://" + u)
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") and host.count(".") >= 2:
        host = host[2:]
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
             if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_KEYS]
    path = p.path.rstrip("/") or ""
    return urlunparse(("https", host, path, "", urlencode(query), ""))


def strip_tracking(u: str) -> str:
    """Remove utm_* and similar tracking parameters but otherwise keep the URL as published."""
    try:
        p = urlparse(u)
    except ValueError:
        return u
    if not p.query:
        return u
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_KEYS]
    return urlunparse(p._replace(query=urlencode(query)))


def domain_of(u: str) -> str:
    try:
        host = (urlparse(u).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s?#\"'<>]+)", re.I)
ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv[:.])(\d{4}\.\d{4,5})(?:v\d+)?", re.I)


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:", "", doi)
    doi = re.sub(r"(\.full|\.abstract|\.pdf)$", "", doi)
    # bioRxiv/medRxiv landing pages add a version suffix (…123456v2)
    doi = re.sub(r"^(10\.1101/\d{4}\.\d{2}\.\d{2}\.\d+)v\d+$", r"\1", doi)
    return doi.rstrip("/.")


def keys_for(url: str = "", doi: str = "", arxiv: str = "") -> list[str]:
    """De-duplication keys for an item: normalized URL, DOI, and arXiv id when they can be found."""
    keys: list[str] = []
    nu = normalize_url(url)
    if nu:
        keys.append("url:" + nu)
    d = normalize_doi(doi)
    if not d and url:
        m = DOI_RE.search(url)
        if m:
            d = normalize_doi(m.group(1))
        elif "nature.com/articles/" in url:
            slug = url.split("nature.com/articles/")[1].split("?")[0].split("#")[0].strip("/")
            if slug:
                d = "10.1038/" + slug.lower()
    if d:
        keys.append("doi:" + d)
        m = re.match(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", d)
        if m:
            arxiv = arxiv or m.group(1)
    a = arxiv
    if not a and url:
        m = ARXIV_RE.search(url)
        if m:
            a = m.group(1)
    if a:
        keys.append("arxiv:" + re.sub(r"v\d+$", "", a))
    return keys


# ---------------------------------------------------------------- HTTP

class Http:
    """requests.Session with polite retries. One instance per run."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=4, connect=3, read=3, status=4, backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = USER_AGENT

    def get(self, url: str, params: dict | None = None, timeout: float | None = None,
            headers: dict | None = None) -> requests.Response:
        r = self.session.get(url, params=params, timeout=timeout or self.timeout, headers=headers)
        r.raise_for_status()
        return r

    def get_json(self, url: str, params: dict | None = None, timeout: float | None = None) -> Any:
        return self.get(url, params=params, timeout=timeout).json()
