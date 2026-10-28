"""Legacy live-headline news provider (Yahoo RSS) and lexicon tone scorer.

Phase 2: this provider is NOT used for historical research. Yahoo RSS only serves the latest
~20-30 headlines, and the former synthetic historical-headline fallback has been removed; the
historical archive comes from AlphaVantageNewsProvider. Kept for live monitoring only.
"""
import hashlib
import logging
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import requests

from app.config.settings import (
    RAW_NEWS_DIR,
    COMPANY_ALIASES_FILE,
    DEFAULT_NEWS_START_DATE,
    DATASET_VERSION
)
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

# Standard Financial Polarity Lexicon (Loughran-McDonald & Financial domain keywords)
FINANCIAL_POSITIVE_TERMS = {
    "surge", "surges", "surged", "surging", "jump", "jumps", "jumped", "rally", "rallies",
    "profit", "profitable", "beat", "beats", "beating", "upgrade", "upgrades", "upgraded",
    "growth", "record", "bull", "bullish", "strong", "outperform", "outperformed",
    "exceeded", "higher", "gain", "gains", "gained", "innovative", "expansion", "positive"
}

FINANCIAL_NEGATIVE_TERMS = {
    "plunge", "plunges", "plunged", "drop", "drops", "dropped", "fall", "falls", "falling",
    "loss", "losses", "miss", "misses", "missed", "downgrade", "downgrades", "downgraded",
    "decline", "declines", "declining", "bear", "bearish", "weak", "underperform",
    "probe", "investigation", "lawsuit", "fine", "fined", "deficit", "lower", "warning",
    "risk", "negative", "layoffs", "cut", "cuts", "cutting"
}


def score_text_tone(text: str) -> float:
    """Calculates a normalized financial tone polarity score in [-1.0, 1.0]."""
    if not text:
        return 0.0

    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    if not words:
        return 0.0

    pos_count = sum(1 for w in words if w in FINANCIAL_POSITIVE_TERMS)
    neg_count = sum(1 for w in words if w in FINANCIAL_NEGATIVE_TERMS)
    total_matches = pos_count + neg_count

    if total_matches == 0:
        return 0.0

    tone = (pos_count - neg_count) / float(total_matches)
    return round(float(np_clip(tone, -1.0, 1.0)), 4)


def np_clip(val: float, low: float, high: float) -> float:
    return max(low, min(val, high))


class NewsDataProvider(ABC):
    """Abstract base class for news providers."""

    @abstractmethod
    def fetch_news_for_ticker(
        self,
        ticker: str,
        start_date: str = DEFAULT_NEWS_START_DATE,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """Fetches news records for a given ticker."""
        pass


class FinvizRSSNewsProvider(NewsDataProvider):
    """Fetches and normalizes news for universe tickers with company alias mapping."""

    def __init__(self, raw_dir: Path = RAW_NEWS_DIR):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.aliases: Dict[str, List[str]] = {}
        self._load_aliases()

    def _load_aliases(self):
        """Loads ticker alias mapping from CSV file."""
        if COMPANY_ALIASES_FILE.exists():
            try:
                df = pd.read_csv(COMPANY_ALIASES_FILE)
                for _, row in df.iterrows():
                    sym = str(row["ticker"]).strip().upper()
                    alias_str = str(row.get("aliases", ""))
                    alias_list = [a.strip() for a in alias_str.split(";") if a.strip()]
                    self.aliases[sym] = alias_list
            except Exception as e:
                logger.warning(f"Failed to load aliases CSV: {e}")

    def fetch_news_for_ticker(
        self,
        ticker: str,
        start_date: str = DEFAULT_NEWS_START_DATE,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """Fetches raw news articles for a ticker with tone scoring and local Parquet cache."""
        ticker = ticker.strip().upper()
        cache_file = self.raw_dir / f"{ticker}_news.parquet"

        if cache_file.exists() and not force_refresh:
            cached_df = ParquetStore.read(cache_file)
            if not cached_df.empty:
                return cached_df

        articles = []
        collected_at = datetime.now(timezone.utc)

        # 1. Attempt fetching live RSS/Finviz news
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and "<item>" in resp.text:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")
                    source_elem = item.find("source")

                    title = title_elem.text if title_elem is not None and title_elem.text else ""
                    link = link_elem.text if link_elem is not None and link_elem.text else ""
                    pub_str = pub_elem.text if pub_elem is not None and pub_elem.text else ""
                    source = source_elem.text if source_elem is not None and source_elem.text else "Yahoo Finance"

                    if not title:
                        continue

                    try:
                        # e.g., "Wed, 10 Sep 2025 14:30:00 +0000"
                        pub_dt = pd.to_datetime(pub_str).tz_convert(None) if pub_str else collected_at.replace(tzinfo=None)
                    except Exception:
                        pub_dt = collected_at.replace(tzinfo=None)

                    art_id = hashlib.md5(f"{ticker}_{link or title}".encode("utf-8")).hexdigest()
                    tone = score_text_tone(title)

                    articles.append({
                        "article_id": art_id,
                        "ticker": ticker,
                        "source": source,
                        "url": link,
                        "title": title,
                        "published_at": pub_dt,
                        "collected_at": collected_at.replace(tzinfo=None),
                        "language": "en",
                        "tone": tone,
                        "ticker_mapping": "EXACT"
                    })
        except Exception as e:
            logger.info(f"Online news feed fetch for {ticker} yielded: {e}")

        if not articles:
            return pd.DataFrame()

        df = pd.DataFrame(articles).drop_duplicates(subset=["article_id"]).sort_values("published_at").reset_index(drop=True)
        ParquetStore.write(df, cache_file)
        return df
