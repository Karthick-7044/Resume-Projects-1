"""In-house historical news harvester (Google News RSS, date-windowed).

Method
1. For every ticker and every calendar week in the study window, query the public RSS search
   endpoint with date operators (`after:` / `before:`). No API key, no quota.
2. A response near the ~100-item cap is assumed truncated, so its window is split in half and
   re-queried (down to one day). Only leaf windows are recorded, so coverage is exact.
3. Every raw response is stored (gzip) with its collection time; parsing works offline.
4. Coverage is explicit: a (ticker, day) is covered only if a window containing it was
   successfully fetched. Failed or unfetched windows are NO_COVERAGE, never "no news".

Point-in-time handling of timestamps
- Some feed items carry only a date (reported as HH:00:00 exactly). Those are flagged
  time_precision = DATE_ONLY and treated as available at the END of that calendar day (US/Eastern),
  so they can only count from the next trading day. Items with a real time keep it.
  This is deliberately conservative: it can delay an article, never advance it.
- collected_at is stored per window and published_at must not exceed it (checked by News QA).

Relevance and topics are rule-based and transparent (company aliases, word-boundary matching,
keyword topic tags), so the whole pipeline is auditable and reproducible without any LLM.
"""
import gzip
import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import pandas as pd
import requests

from app.config.settings import (
    COMPANY_ALIASES_FILE, DEFAULT_END_DATE, DEFAULT_NEWS_START_DATE, GNEWS_MIN_SECONDS_BETWEEN_CALLS,
    GNEWS_TRUNCATION_ITEMS, GNEWS_WINDOW_DAYS, MARKET_TIMEZONE, RAW_NEWS_GN_DIR,
)

logger = logging.getLogger(__name__)

ENDPOINT = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; academic-research-harvester)"}
PROVIDER = "google_news_rss"

# Transparent keyword topic tagger (normalized to the topic names used by the feature engine)
TOPIC_RULES = {
    "earnings": r"\b(earnings|eps|quarterly|results|revenue|profit|guidance|outlook|forecast|beats?|misses?)\b",
    "mergers_and_acquisitions": r"\b(acquire[sd]?|acquisition|merger|takeover|buyout|buys?|deal|divest|spin[- ]?off|stake)\b",
    "technology": r"\b(ai|artificial intelligence|chips?|cloud|software|semiconductor|iphone|data cent(er|re)|gpu|cyber|app)\b",
    "economy_macro": r"\b(fed|inflation|interest rates?|recession|tariffs?|gdp|jobs report|economy|treasury|oil prices?)\b",
    "financial_markets": r"\b(stocks?|shares|analyst|price target|upgrade[sd]?|downgrade[sd]?|rally|selloff|sell-off|dividend|buyback|nasdaq|s&p|dow)\b",
}
_TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPIC_RULES.items()}


def tag_topics(title: str) -> str:
    return ";".join(sorted(k for k, rx in _TOPIC_RE.items() if rx.search(title or "")))


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url.strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"


def make_article_id(guid_or_url: str, title: str, publisher: str) -> str:
    """Deterministic ID: SHA-1 of the feed GUID/URL (falls back to publisher+title)."""
    key = normalize_url(guid_or_url) or f"{publisher}|{title}".lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def is_date_only(ts: pd.Timestamp) -> bool:
    """Feed items stamped exactly on the hour carry only a date, not a publication time."""
    return ts.minute == 0 and ts.second == 0


def effective_availability(ts_utc: pd.Timestamp) -> Tuple[pd.Timestamp, str]:
    """Returns (naive-UTC availability time, precision flag)."""
    if is_date_only(ts_utc):
        # End of the calendar day in the market timezone: usable only from the next trading day.
        day = ts_utc.tz_localize("UTC").tz_convert(MARKET_TIMEZONE).normalize()
        eod = (day + pd.Timedelta(hours=23, minutes=59, seconds=59)).tz_convert("UTC").tz_localize(None)
        return eod, "DATE_ONLY"
    return ts_utc, "EXACT"


def load_aliases() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if COMPANY_ALIASES_FILE.exists():
        df = pd.read_csv(COMPANY_ALIASES_FILE)
        for _, r in df.iterrows():
            out[str(r["ticker"]).upper()] = [a.strip() for a in str(r.get("aliases", "")).split(";") if a.strip()]
    return out


def mentions_company(title: str, ticker: str, aliases: List[str]) -> bool:
    t = title or ""
    for a in aliases:
        if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", t, re.I):
            return True
    return len(ticker) >= 3 and re.search(rf"(?<![A-Za-z]){re.escape(ticker)}(?![A-Za-z])", t) is not None


def parse_feed(xml_bytes: bytes, ticker: str, aliases: List[str], collected_at: pd.Timestamp) -> pd.DataFrame:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return pd.DataFrame()
    rows = []
    for it in root.findall(".//item"):
        raw_title = (it.findtext("title") or "").strip()
        src_el = it.find("source")
        publisher = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        title = raw_title
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(f" - {publisher}")].strip()
        pub_raw = it.findtext("pubDate") or ""
        try:
            ts = pd.to_datetime(pub_raw, utc=True).tz_localize(None)
        except (ValueError, TypeError):
            continue
        if not title:
            continue
        avail, precision = effective_availability(ts)
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link).strip()
        rel = mentions_company(title, ticker, aliases)
        rows.append({
            "article_id": make_article_id(guid, title, publisher), "ticker": ticker, "title": title, "summary": "",
            "publisher": publisher, "source_domain": urlsplit(src_el.get("url")).netloc if src_el is not None and src_el.get("url") else "",
            "url": link, "published_raw": pub_raw, "published_reported": ts, "published_at": avail,
            "time_precision": precision, "collected_at": collected_at, "source": PROVIDER,
            "topics": tag_topics(title), "relevance_score": 1.0 if rel else 0.0, "title_mentions_company": rel,
            "ticker_mapping": "QUERY_ALIAS_MATCH" if rel else "QUERY_ONLY",
        })
    return pd.DataFrame(rows)


class GoogleNewsHarvester:
    def __init__(self, raw_dir: Path = RAW_NEWS_GN_DIR, start_date: str = DEFAULT_NEWS_START_DATE,
                 end_date: str = DEFAULT_END_DATE, window_days: int = GNEWS_WINDOW_DAYS,
                 min_interval: float = GNEWS_MIN_SECONDS_BETWEEN_CALLS, session: Optional[requests.Session] = None,
                 split_truncated: bool = True):
        self.split_truncated = split_truncated   # False = sample mode: keep a capped window (flagged truncated) unsplit
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.start = pd.Timestamp(start_date).normalize()
        self.end = pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)   # exclusive
        self.window_days = window_days
        self.min_interval = min_interval
        self.session = session or requests.Session()
        self._last = 0.0
        self.aliases = load_aliases()
        self.log_path = self.raw_dir / "fetch_log.json"
        self.log: Dict[str, List[Dict[str, Any]]] = self._load_log()
        self.requests_made = 0

    # ------------------------------------------------------------------ log
    def _load_log(self) -> Dict[str, List[Dict[str, Any]]]:
        if self.log_path.exists():
            try:
                return json.loads(self.log_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Unreadable fetch log; starting a new one")
        return {}

    def _save_log(self):
        self.log_path.write_text(json.dumps(self.log), encoding="utf-8")

    def _done(self, ticker: str) -> set:
        return {(e["from"], e["to"]) for e in self.log.get(ticker, []) if e["status"] == "OK"}

    # ------------------------------------------------------------------ query
    def query_for(self, ticker: str) -> str:
        al = self.aliases.get(ticker, [])
        name = al[0] if al else ticker
        return f"{name} {ticker} stock"

    def _get(self, ticker: str, a: pd.Timestamp, b: pd.Timestamp) -> Optional[bytes]:
        q = f"{self.query_for(ticker)} after:{a.date()} before:{b.date()}"
        for attempt in range(1, 5):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.session.get(ENDPOINT, params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                                     headers=HEADERS, timeout=30)
                self.requests_made += 1
                if r.status_code == 200:
                    return r.content
                if r.status_code in (429, 503):
                    time.sleep(10.0 * attempt)
                    continue
                logger.warning(f"{ticker} {a.date()}: HTTP {r.status_code}")
                return None
            except requests.RequestException as e:
                logger.warning(f"{ticker} {a.date()}: {e}")
                time.sleep(3.0 * attempt)
        return None

    def _fetch_window(self, ticker: str, a: pd.Timestamp, b: pd.Timestamp):
        """Fetches [a, b); splits when the response looks capped. Records leaf windows only."""
        content = self._get(ticker, a, b)
        collected = datetime.now(timezone.utc)
        if content is None:
            self.log.setdefault(ticker, []).append({"from": str(a.date()), "to": str(b.date()), "status": "FAILED",
                                                    "items": 0, "fetched_at": collected.isoformat()})
            return
        n = len(ET.fromstring(content).findall(".//item")) if content else 0
        if self.split_truncated and n >= GNEWS_TRUNCATION_ITEMS and (b - a).days > 1:
            mid = a + (b - a) // 2
            self._fetch_window(ticker, a, mid.normalize())
            self._fetch_window(ticker, mid.normalize(), b)
            return
        d = self.raw_dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        fname = f"{a.date()}_{b.date()}_{collected.strftime('%Y%m%dT%H%M%S')}.xml.gz"
        (d / fname).write_bytes(gzip.compress(content))
        self.log.setdefault(ticker, []).append({
            "from": str(a.date()), "to": str(b.date()), "status": "OK", "items": n, "file": fname,
            "truncated": bool(n >= GNEWS_TRUNCATION_ITEMS), "fetched_at": collected.isoformat()})

    def harvest(self, ticker: str, max_windows: Optional[int] = None) -> int:
        """Fetches every not-yet-covered weekly window for a ticker (resumable). Returns windows fetched."""
        ticker = ticker.upper()
        done = self._done(ticker)
        covered = self._covered_days(ticker)
        fetched, cur = 0, self.start
        while cur < self.end:
            nxt = min(cur + pd.Timedelta(days=self.window_days), self.end)
            days = pd.date_range(cur, nxt - pd.Timedelta(days=1))
            if not all(d in covered for d in days):
                self._fetch_window(ticker, cur, nxt)
                fetched += 1
                if fetched % 10 == 0:
                    self._save_log()
                    logger.info(f"[gnews] {ticker}: {fetched} windows, up to {cur.date()}")
                if max_windows and fetched >= max_windows:
                    break
            cur = nxt
        self._save_log()
        return fetched

    def _covered_days(self, ticker: str) -> set:
        out = set()
        for e in self.log.get(ticker, []):
            if e["status"] == "OK":
                out.update(pd.date_range(e["from"], pd.Timestamp(e["to"]) - pd.Timedelta(days=1)))
        return out

    # ------------------------------------------------------------------ read back
    def coverage_intervals(self, ticker: str) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """Covered [from, to) windows as US/Eastern wall-clock intervals (adjacent windows merge later)."""
        return [(pd.Timestamp(e["from"]), pd.Timestamp(e["to"])) for e in self.log.get(ticker.upper(), [])
                if e["status"] == "OK"]

    def load_articles(self, ticker: str) -> pd.DataFrame:
        ticker = ticker.upper()
        d = self.raw_dir / ticker
        if not d.exists():
            return pd.DataFrame()
        aliases = self.aliases.get(ticker, [])
        frames = []
        for f in sorted(d.glob("*.xml.gz")):
            stamp = f.name.rsplit("_", 1)[-1].replace(".xml.gz", "")
            collected = pd.Timestamp(datetime.strptime(stamp, "%Y%m%dT%H%M%S"))
            df = parse_feed(gzip.decompress(f.read_bytes()), ticker, aliases, collected)
            if not df.empty:
                df["raw_file"] = f.name
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values("collected_at").drop_duplicates(subset=["article_id", "ticker"], keep="first")
        return out.sort_values("published_at").reset_index(drop=True)

    def coverage_table(self, tickers: List[str]) -> pd.DataFrame:
        rows = []
        for t in tickers:
            ent = self.log.get(t.upper(), [])
            ok = [e for e in ent if e["status"] == "OK"]
            rows.append({"ticker": t.upper(), "provider": PROVIDER, "requests": len(ent),
                         "articles_returned": int(sum(e["items"] for e in ok)),
                         "failed_windows": len([e for e in ent if e["status"] == "FAILED"]),
                         "truncated_windows": len([e for e in ok if e.get("truncated")]),
                         "coverage_start": min((pd.Timestamp(e["from"]) for e in ok), default=None),
                         "coverage_end": max((pd.Timestamp(e["to"]) for e in ok), default=None),
                         "complete": len(self._covered_days(t.upper())) >= (self.end - self.start).days})
        return pd.DataFrame(rows)
