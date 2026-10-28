"""Finnhub company-news provider: backfill (2024-01-01 -> today) and append-only daily updates.

Writes the same unified schema as the FNSPID provider with provider = "finnhub":
    article_hash, ticker, published_at (UTC), fetched_at (UTC, actual fetch time), title, summary,
    source (publisher), url, provider, provider_fetch_kind = "api"
(+ provider_article_id, source_domain, time_precision, topics, relevance_weight, article_type...).

Rules
- API key from FINNHUB_API_KEY (environment / .env) only; never in code. 1 call/second pacing and
  exponential backoff on 429/5xx (Finnhub free tier: 60 calls/min).
- Every raw JSON response is saved to data/raw/news_finnhub_raw/{TICKER}/{YYYY-MM}.json BEFORE processing;
  windows already saved are skipped (idempotent, resumable). A window returning `per_call_cap` articles or
  more is split in halves automatically; split windows are saved as {YYYY-MM}__{from}_{to}.json.
- Daily update fetches the last N days for every ticker, de-duplicates by article_hash and APPENDS only new
  rows; existing rows are never edited or deleted.
- Missing coverage is never imputed: a month with no saved raw response simply has no coverage.
Response fields used (Finnhub docs): headline, summary, source, url, datetime (unix seconds), id, related,
category, image. The code reads them defensively; the real response shape is verified by
scripts/probe_news_sources.py once a working key is available.
"""
import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

import pandas as pd
import requests

from app.config.news_config import load_news_config
from app.config.settings import DATA_DIR
from app.features.news_enrich import enrich
from app.data.providers.gnews_provider import tag_topics

logger = logging.getLogger(__name__)

URL = "https://finnhub.io/api/v1/company-news"
FINNHUB_RAW_DIR = DATA_DIR / "raw" / "news_finnhub_raw"
FINNHUB_UNIFIED_DIR = DATA_DIR / "raw" / "news_finnhub"
UNIFIED_COLUMNS = ["article_hash", "article_id", "ticker", "published_at", "fetched_at", "title", "summary", "source",
                   "url", "provider", "provider_fetch_kind", "provider_article_id", "source_domain", "time_precision",
                   "section", "topics", "title_mentions_company", "relevance_weight", "article_type"]


class FinnhubAuthError(RuntimeError):
    """The API key is missing or rejected (HTTP 401/403)."""


def article_hash(ticker: str, title: str, published_at: pd.Timestamp) -> str:
    key = f"{ticker}|{title}|{pd.Timestamp(published_at).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def month_windows(start: date, end: date) -> List[Tuple[date, date]]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((max(cur, start), min(nxt - timedelta(days=1), end)))
        cur = nxt
    return out


def to_unified(ticker: str, items: List[Dict], fetched_at: pd.Timestamp, cfg: Optional[Dict] = None) -> pd.DataFrame:
    rows = []
    for it in items or []:
        title = (it.get("headline") or "").strip()
        ts = it.get("datetime")
        if not title or not ts:
            continue
        pub = pd.Timestamp(int(ts), unit="s", tz="UTC")
        url = (it.get("url") or "").strip()
        h = article_hash(ticker, title, pub)
        rows.append({
            "article_hash": h, "article_id": h[:20], "ticker": ticker, "published_at": pub, "fetched_at": fetched_at,
            "title": title, "summary": (it.get("summary") or "").strip(), "source": (it.get("source") or "").strip(),
            "url": url, "provider": "finnhub", "provider_fetch_kind": "api",
            "provider_article_id": str(it.get("id", "")), "source_domain": urlsplit(url).netloc.lower().replace("www.", ""),
            "time_precision": "EXACT", "section": "finnhub_api", "topics": tag_topics(title),
        })
    if not rows:
        return pd.DataFrame(columns=UNIFIED_COLUMNS)
    df = pd.DataFrame(rows).drop_duplicates("article_hash")
    return enrich(df, cfg)[UNIFIED_COLUMNS]


class FinnhubNewsProvider:
    def __init__(self, api_key: Optional[str] = None, raw_dir: Path = FINNHUB_RAW_DIR,
                 unified_dir: Path = FINNHUB_UNIFIED_DIR, session: Optional[requests.Session] = None,
                 sleep: Callable[[float], None] = time.sleep, cfg: Optional[Dict] = None):
        self.cfg = cfg or load_news_config()
        self.api_key = api_key if api_key is not None else os.getenv("FINNHUB_API_KEY")
        self.raw_dir, self.unified_dir = Path(raw_dir), Path(unified_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.unified_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.sleep = sleep
        self.pacing = float(self.cfg["finnhub"]["pacing_seconds"])
        self.cap = int(self.cfg["finnhub"]["per_call_cap"])
        self._last_call = 0.0
        self.calls = 0

    # ------------------------------------------------------------------ HTTP
    def _request(self, ticker: str, a: date, b: date) -> List[Dict]:
        if not self.api_key:
            raise FinnhubAuthError("FINNHUB_API_KEY is not set")
        last = None
        for attempt in range(1, 7):
            wait = self.pacing - (time.time() - self._last_call)
            if wait > 0:
                self.sleep(wait)
            self._last_call = time.time()
            try:
                r = self.session.get(URL, params={"symbol": ticker, "from": a.isoformat(), "to": b.isoformat()},
                                     headers={"X-Finnhub-Token": self.api_key}, timeout=30)
                self.calls += 1
            except requests.RequestException as e:
                last = str(e)
                self.sleep(min(60, 2 ** attempt))
                continue
            if r.status_code == 200:
                body = r.json()
                return body if isinstance(body, list) else []
            if r.status_code in (401, 403):
                raise FinnhubAuthError(f"HTTP {r.status_code}: {r.text[:100]}")
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                self.sleep(min(120, 2 ** (attempt + 1)))
                continue
            raise RuntimeError(f"Finnhub HTTP {r.status_code}: {r.text[:100]}")
        raise RuntimeError(f"Finnhub request failed after retries: {last}")

    def _request_split(self, ticker: str, a: date, b: date) -> List[Dict]:
        """Items for [a, b]; a response at/over the per-call cap is split in halves (down to one day) and merged."""
        items = self._request(ticker, a, b)
        if len(items) >= self.cap and (b - a).days >= 1:
            mid = a + (b - a) // 2
            merged = self._request_split(ticker, a, mid) + self._request_split(ticker, mid + timedelta(days=1), b)
            seen, out = set(), []
            for it in merged:
                k = (it.get("id"), it.get("datetime"), it.get("headline"))
                if k not in seen:
                    seen.add(k)
                    out.append(it)
            return out
        return items

    # ------------------------------------------------------------------ raw storage
    def _raw_path(self, ticker: str, a: date, b: date, month_window: bool) -> Path:
        d = self.raw_dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        return d / (f"{a:%Y-%m}.json" if month_window else f"{a:%Y-%m}__{a.isoformat()}_{b.isoformat()}.json")

    def fetch_window(self, ticker: str, a: date, b: date, month_window: bool = True) -> int:
        """Fetches [a, b], saving the raw JSON before anything else. Returns the number of articles."""
        path = self._raw_path(ticker, a, b, month_window)
        if path.exists():
            return len(json.loads(path.read_text(encoding="utf-8"))["articles"])
        items = self._request(ticker, a, b)
        path.write_text(json.dumps({"ticker": ticker, "from": a.isoformat(), "to": b.isoformat(),
                                    "fetched_at": datetime.now(timezone.utc).isoformat(), "articles": items}),
                        encoding="utf-8")
        if len(items) >= self.cap and (b - a).days >= 1:       # response looks capped: split into halves
            mid = a + (b - a) // 2
            self.fetch_window(ticker, a, mid, month_window=False)
            self.fetch_window(ticker, mid + timedelta(days=1), b, month_window=False)
        return len(items)

    def backfill(self, tickers: Iterable[str], start: Optional[date] = None, end: Optional[date] = None) -> Dict[str, int]:
        cfg_p = self.cfg["providers"]["finnhub"]
        start = start or date.fromisoformat(cfg_p["start"])
        end = end or (date.fromisoformat(cfg_p["end"]) if cfg_p.get("end") else date.today())
        counts = {}
        for t in tickers:
            n = 0
            for a, b in month_windows(start, end):
                n += self.fetch_window(t.upper(), a, b)
            counts[t.upper()] = n
            logger.info(f"[finnhub] backfill {t}: {n} articles in saved windows")
        return counts

    # ------------------------------------------------------------------ unified table
    def load_raw_articles(self, ticker: str) -> pd.DataFrame:
        frames = []
        for f in sorted((self.raw_dir / ticker).glob("*.json")) if (self.raw_dir / ticker).exists() else []:
            blob = json.loads(f.read_text(encoding="utf-8"))
            df = to_unified(ticker, blob["articles"], pd.Timestamp(blob["fetched_at"]), self.cfg)
            if not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame(columns=UNIFIED_COLUMNS)
        # the same article returned by overlapping/split windows keeps its FIRST fetch time
        return pd.concat(frames, ignore_index=True).sort_values("fetched_at").drop_duplicates("article_hash", keep="first")

    def unified_path(self, ticker: str) -> Path:
        return self.unified_dir / f"{ticker}_news.parquet"

    def append_new(self, ticker: str, new: pd.DataFrame) -> int:
        """Append-only: writes rows whose article_hash is not stored yet. Existing rows are never changed."""
        path = self.unified_path(ticker)
        old = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=UNIFIED_COLUMNS)
        fresh = new[~new["article_hash"].isin(set(old["article_hash"]))]
        if fresh.empty:
            return 0
        pd.concat([old, fresh], ignore_index=True).to_parquet(path, index=False)
        return len(fresh)

    def materialize_backfill(self, tickers: Iterable[str]) -> Dict[str, int]:
        """Unified parquet from every saved raw window (append-only; reruns add nothing)."""
        return {t.upper(): self.append_new(t.upper(), self.load_raw_articles(t.upper())) for t in tickers}

    def daily_update(self, tickers: Iterable[str], days: Optional[int] = None) -> Dict[str, Dict]:
        """Fetches the last `days` days per ticker and appends only new articles. Logs per-ticker counts."""
        days = days or int(self.cfg["finnhub"]["daily_lookback_days"])
        today = datetime.now(timezone.utc).date()
        report = {}
        for t in [x.upper() for x in tickers]:
            fetched_at = pd.Timestamp.now(tz="UTC")
            items = self._request_split(t, today - timedelta(days=days), today)
            raw = self.raw_dir / t
            raw.mkdir(parents=True, exist_ok=True)
            (raw / f"daily_{fetched_at:%Y%m%dT%H%M%S}.json").write_text(
                json.dumps({"ticker": t, "from": (today - timedelta(days=days)).isoformat(), "to": today.isoformat(),
                            "fetched_at": fetched_at.isoformat(), "articles": items}), encoding="utf-8")
            df = to_unified(t, items, fetched_at, self.cfg)
            added = self.append_new(t, df)
            prev = self.unified_path(t)
            typical = (len(pd.read_parquet(prev)) / max(1, (today - date.fromisoformat(self.cfg["providers"]["finnhub"]["start"])).days)) if prev.exists() else 0
            if len(items) == 0 and typical * days >= 1:
                logger.warning(f"[finnhub] {t}: ZERO articles in the last {days} days (typically ~{typical * days:.1f})")
            logger.info(f"[finnhub] {t}: fetched {len(items)}, new {added}")
            report[t] = {"fetched": len(items), "new": added}
            self._log_daily(t, today, len(items), added)
        return report

    def _log_daily(self, ticker: str, day: date, fetched: int, new: int):
        log = self.unified_dir / "daily_log.csv"
        header = not log.exists()
        with open(log, "a", encoding="utf-8") as f:
            if header:
                f.write("date,ticker,fetched,new,logged_at\n")
            f.write(f"{day.isoformat()},{ticker},{fetched},{new},{datetime.now(timezone.utc).isoformat()}\n")

    def coverage(self, ticker: str) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """Covered [from, to] date intervals = windows whose raw response was saved (daily files excluded)."""
        out = []
        d = self.raw_dir / ticker
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            if f.name.startswith("daily_"):
                continue
            blob = json.loads(f.read_text(encoding="utf-8"))
            out.append((pd.Timestamp(blob["from"]), pd.Timestamp(blob["to"])))
        return out
