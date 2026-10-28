"""Alpha Vantage NEWS_SENTIMENT historical news provider.

Design (see project documentation, Section 10):
- Genuine historical articles only. There is no synthetic fallback on any code path.
- Every API response is stored verbatim under data/raw/news/alphavantage/{TICKER}/ so the
  pipeline can be rebuilt offline and every daily feature can be traced back to raw JSON.
- The free tier allows ~25 requests/day. Fetching is therefore resumable: for each ticker a
  cursor pages forward through time (sort=EARLIEST). Each call advances the cursor to the
  latest timestamp returned, and a fetch log records the covered interval, so re-running the
  pipeline on later days extends coverage without re-downloading anything.
- Coverage is explicit: a (ticker, date) is "covered" only when it lies inside an interval the
  provider actually returned. Days outside coverage are NO_COVERAGE, never "zero news".
- Alpha Vantage `time_published` has no timezone designator. It is interpreted as US/Eastern,
  which can only make an article appear *later* than it really was (if the true zone is UTC),
  never earlier, so the assumption cannot introduce look-ahead.
"""
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import requests

from app.config.settings import (
    ALPHAVANTAGE_API_KEY,
    ALPHAVANTAGE_DAILY_REQUEST_BUDGET,
    ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS,
    DEFAULT_END_DATE,
    DEFAULT_NEWS_START_DATE,
    MARKET_TIMEZONE,
    RAW_NEWS_AV_DIR,
)

logger = logging.getLogger(__name__)

AV_ENDPOINT = "https://www.alphavantage.co/query"
AV_PAGE_LIMIT = 1000
PROVIDER_NAME = "alphavantage"

# Alpha Vantage topic names (normalized to snake_case) mapped to daily topic-count features.
TOPIC_FEATURE_MAP = {
    "earnings": "earnings",
    "mergers_and_acquisitions": "merger",
    "mergers_&_acquisitions": "merger",
    "technology": "technology",
    "economy_macro": "macro",
    "economy_monetary": "macro",
    "economy_fiscal": "macro",
    "financial_markets": "financial_market",
}


def normalize_topic(name: str) -> str:
    """'Economy - Macro' and 'economy_macro' both normalize to 'economy_macro'."""
    return re.sub(r"[\s\-]+", "_", str(name).strip().lower()).replace("__", "_")


class AlphaVantageRateLimitError(RuntimeError):
    """Raised when Alpha Vantage reports that the request quota is exhausted."""


def normalize_url(url: str) -> str:
    """Canonical URL used for deterministic article IDs (drops query string and fragment)."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def make_article_id(url: str, title: str = "", published_raw: str = "") -> str:
    """Deterministic article ID: SHA-1 of the normalized URL (title+time when URL is missing)."""
    key = normalize_url(url) or f"{(title or '').strip().lower()}|{published_raw}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def parse_av_timestamp(value: str) -> Optional[pd.Timestamp]:
    """Parses 'YYYYMMDDTHHMMSS' (US/Eastern assumed) into a naive UTC timestamp."""
    if not value or not isinstance(value, str):
        return None
    m = re.fullmatch(r"(\d{8})T(\d{4})(\d{2})?", value.strip())
    if not m:
        return None
    fmt = "%Y%m%dT%H%M%S" if m.group(3) else "%Y%m%dT%H%M"
    try:
        local = pd.Timestamp(datetime.strptime(value.strip(), fmt)).tz_localize(
            MARKET_TIMEZONE, ambiguous="NaT", nonexistent="shift_forward"
        )
    except (ValueError, TypeError):
        return None
    if pd.isna(local):
        return None
    return local.tz_convert("UTC").tz_localize(None)


def parse_av_feed(payload: Dict[str, Any], ticker: str, collected_at: datetime) -> pd.DataFrame:
    """Converts one NEWS_SENTIMENT response into raw article rows for the queried ticker.

    Only the queried ticker's ticker_sentiment entry is used: coverage is established for the
    queried symbol only, so attributing the article to other symbols would mix coverage regimes.
    """
    ticker = ticker.upper()
    rows: List[Dict[str, Any]] = []
    for item in payload.get("feed", []) or []:
        if not isinstance(item, dict):
            continue
        ts_entry = next(
            (t for t in item.get("ticker_sentiment", []) or [] if str(t.get("ticker", "")).upper() == ticker),
            None,
        )
        published_raw = str(item.get("time_published", ""))
        topics = item.get("topics", []) or []
        topic_names = sorted({normalize_topic(t.get("topic", "")) for t in topics if t.get("topic")})

        def _to_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        rows.append({
            "article_id": make_article_id(item.get("url", ""), item.get("title", ""), published_raw),
            "ticker": ticker,
            "title": (item.get("title") or "").strip(),
            "summary": (item.get("summary") or "").strip(),
            "publisher": item.get("source") or "",
            "source_domain": item.get("source_domain") or "",
            "url": item.get("url") or "",
            "published_raw": published_raw,
            "published_at": parse_av_timestamp(published_raw),
            "collected_at": pd.Timestamp(collected_at).tz_localize(None) if pd.Timestamp(collected_at).tzinfo else pd.Timestamp(collected_at),
            "source": PROVIDER_NAME,
            "topics": ";".join(topic_names),
            "overall_sentiment_score": _to_float(item.get("overall_sentiment_score")),
            "overall_sentiment_label": item.get("overall_sentiment_label"),
            "av_relevance_score": _to_float(ts_entry.get("relevance_score")) if ts_entry else None,
            "av_ticker_sentiment": _to_float(ts_entry.get("ticker_sentiment_score")) if ts_entry else None,
            "av_ticker_sentiment_label": ts_entry.get("ticker_sentiment_label") if ts_entry else None,
            "ticker_mapping": "PROVIDER_TICKER_SENTIMENT" if ts_entry else "QUERY_ONLY",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        })
    return pd.DataFrame(rows)


class AlphaVantageNewsProvider:
    """Resumable, quota-aware Alpha Vantage news archive for the configured universe."""

    def __init__(
        self,
        api_key: Optional[str] = ALPHAVANTAGE_API_KEY,
        raw_dir: Path = RAW_NEWS_AV_DIR,
        start_date: str = DEFAULT_NEWS_START_DATE,
        end_date: str = DEFAULT_END_DATE,
        request_budget: int = ALPHAVANTAGE_DAILY_REQUEST_BUDGET,
        session: Optional[requests.Session] = None,
        min_interval: float = ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS,
    ):
        self.api_key = api_key
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)
        self.request_budget = request_budget
        self.requests_made = 0
        self.session = session or requests.Session()
        self.min_interval = min_interval
        self._last_call = 0.0
        self.log_path = self.raw_dir / "fetch_log.json"
        self.fetch_log: Dict[str, List[Dict[str, Any]]] = self._load_log()

    # ------------------------------------------------------------------ fetch log
    def _load_log(self) -> Dict[str, List[Dict[str, Any]]]:
        if self.log_path.exists():
            try:
                return json.loads(self.log_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not read Alpha Vantage fetch log: {e}")
        return {}

    def _save_log(self):
        self.log_path.write_text(json.dumps(self.fetch_log, indent=2), encoding="utf-8")

    def cursor_for(self, ticker: str) -> pd.Timestamp:
        """Returns the next time_from for a ticker (end of contiguous covered interval)."""
        entries = [e for e in self.fetch_log.get(ticker, []) if e.get("status") == "OK"]
        if not entries:
            return self.start_date
        return max(pd.Timestamp(e["covered_to"]) for e in entries)

    def is_complete(self, ticker: str) -> bool:
        return self.cursor_for(ticker) >= self.end_date

    # ------------------------------------------------------------------ HTTP
    def _request(self, ticker: str, time_from: pd.Timestamp, time_to: pd.Timestamp) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured")
        if self.requests_made >= self.request_budget:
            raise AlphaVantageRateLimitError("Local daily request budget exhausted")

        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "time_from": time_from.strftime("%Y%m%dT%H%M"),
            "time_to": time_to.strftime("%Y%m%dT%H%M"),
            "sort": "EARLIEST",
            "limit": AV_PAGE_LIMIT,
            "apikey": self.api_key,
        }
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self._last_call = time.time()
                resp = self.session.get(AV_ENDPOINT, params=params, timeout=30)
                self.requests_made += 1
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                payload = resp.json()
                note = payload.get("Note") or payload.get("Information")
                if note and "feed" not in payload:
                    if "rate limit" in note.lower() or "requests per day" in note.lower() or "premium" in note.lower():
                        raise AlphaVantageRateLimitError(note)
                    raise RuntimeError(note)
                if "Error Message" in payload:
                    raise RuntimeError(payload["Error Message"])
                return payload
            except AlphaVantageRateLimitError:
                raise
            except (requests.RequestException, ValueError, RuntimeError) as e:
                last_error = e
                logger.warning(f"Alpha Vantage request failed for {ticker} (attempt {attempt}/3): {e}")
                time.sleep(2.0 * attempt)
        raise RuntimeError(f"Alpha Vantage request failed for {ticker}: {last_error}")

    # ------------------------------------------------------------------ public API
    def fetch_next_page(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetches one page forward from the ticker's cursor and records it in the fetch log."""
        ticker = ticker.upper()
        time_from = self.cursor_for(ticker)
        if time_from >= self.end_date:
            return None
        collected_at = datetime.now(timezone.utc)
        payload = self._request(ticker, time_from, self.end_date)

        ticker_dir = self.raw_dir / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{time_from.strftime('%Y%m%dT%H%M')}_{collected_at.strftime('%Y%m%dT%H%M%S')}.json"
        (ticker_dir / fname).write_text(
            json.dumps({"ticker": ticker, "collected_at": collected_at.isoformat(),
                        "time_from": time_from.isoformat(), "time_to": self.end_date.isoformat(),
                        "response": payload}, ensure_ascii=False),
            encoding="utf-8",
        )

        feed = payload.get("feed", []) or []
        stamps = [parse_av_timestamp(str(it.get("time_published", ""))) for it in feed]
        stamps = [s for s in stamps if s is not None]
        truncated = len(feed) >= AV_PAGE_LIMIT
        if truncated and stamps:
            # Coverage ends at the newest *US/Eastern* timestamp returned; the cursor re-requests
            # that minute next time and duplicates are removed by article_id.
            newest_local = max(
                pd.Timestamp(datetime.strptime(str(it["time_published"])[:13], "%Y%m%dT%H%M"))
                for it in feed if it.get("time_published")
            )
            covered_to = newest_local
        else:
            covered_to = self.end_date

        entry = {
            "status": "OK",
            "file": fname,
            "time_from": time_from.isoformat(),
            "covered_to": pd.Timestamp(covered_to).isoformat(),
            "items": len(feed),
            "truncated": bool(truncated),
            "fetched_at": collected_at.isoformat(),
        }
        self.fetch_log.setdefault(ticker, []).append(entry)
        self._save_log()
        logger.info(f"[AlphaVantage] {ticker}: {len(feed)} items, coverage {time_from.date()} -> {pd.Timestamp(covered_to).date()}")
        return entry

    def update_archive(self, tickers: List[str], max_requests: Optional[int] = None) -> Dict[str, Any]:
        """Round-robin paging across tickers until the request budget is used or all are complete."""
        budget = min(self.request_budget, max_requests) if max_requests else self.request_budget
        self.request_budget = budget
        summary = {"requests": 0, "rate_limited": False, "errors": []}
        pending = [t.upper() for t in tickers if not self.is_complete(t)]
        while pending and self.requests_made < budget:
            for ticker in list(pending):
                if self.requests_made >= budget:
                    break
                try:
                    self.fetch_next_page(ticker)
                except AlphaVantageRateLimitError as e:
                    logger.warning(f"Alpha Vantage quota reached: {e}")
                    summary["rate_limited"] = True
                    pending = []
                    break
                except RuntimeError as e:
                    summary["errors"].append(f"{ticker}: {e}")
                    pending.remove(ticker)
                    continue
                if self.is_complete(ticker):
                    pending.remove(ticker)
        summary["requests"] = self.requests_made
        return summary

    def load_articles(self, ticker: str) -> pd.DataFrame:
        """Parses every cached raw response for a ticker (offline, no API calls)."""
        ticker = ticker.upper()
        ticker_dir = self.raw_dir / ticker
        if not ticker_dir.exists():
            return pd.DataFrame()
        frames = []
        for f in sorted(ticker_dir.glob("*.json")):
            try:
                blob = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Skipping unreadable raw news file {f}: {e}")
                continue
            df = parse_av_feed(blob.get("response", {}), ticker, pd.Timestamp(blob.get("collected_at")).to_pydatetime())
            if not df.empty:
                df["raw_file"] = f.name
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        # Same article returned by overlapping pages: keep the first collected copy.
        out = out.sort_values("collected_at").drop_duplicates(subset=["article_id", "ticker"], keep="first")
        return out.sort_values("published_at").reset_index(drop=True)

    def coverage_intervals(self, ticker: str) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """Covered [from, to] intervals (US/Eastern wall-clock) returned by successful fetches."""
        return [
            (pd.Timestamp(e["time_from"]), pd.Timestamp(e["covered_to"]))
            for e in self.fetch_log.get(ticker.upper(), [])
            if e.get("status") == "OK"
        ]

    def coverage_table(self, tickers: List[str]) -> pd.DataFrame:
        rows = []
        for t in tickers:
            intervals = self.coverage_intervals(t)
            entries = self.fetch_log.get(t.upper(), [])
            rows.append({
                "ticker": t.upper(),
                "provider": PROVIDER_NAME,
                "requests": len(entries),
                "articles_returned": int(sum(e.get("items", 0) for e in entries)),
                "coverage_start": min((a for a, _ in intervals), default=None),
                "coverage_end": max((b for _, b in intervals), default=None),
                "complete": self.is_complete(t),
            })
        return pd.DataFrame(rows)
