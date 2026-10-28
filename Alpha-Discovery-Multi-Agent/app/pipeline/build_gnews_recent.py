"""Builds unified-schema article files for the 2024-2025 Google News RSS sample (provider = google_news_rss).

    python -m app.pipeline.build_gnews_recent

Reads the raw responses saved by harvest_news_recent, maps them to the unified news schema used by FNSPID/Finnhub
(same enrichment: company mention, relevance weight, article type), and writes data/raw/news/gnews_recent/{T}_news.parquet.
Coverage for the news layer = the fortnightly windows that were actually fetched (see coverage()).
"""
import hashlib
import logging
from typing import Dict, List, Tuple

import pandas as pd

from app.config.news_config import load_news_config
from app.features.news_enrich import enrich
from app.pipeline.build_fnspid_news import UNIFIED_COLUMNS
from app.pipeline.harvest_news import universe_tickers
from app.pipeline.harvest_news_recent import RECENT_DIR, harvester

logger = logging.getLogger("BuildGnewsRecent")
PROVIDER = "google_news_rss"


def unified(raw: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=UNIFIED_COLUMNS)
    df = pd.DataFrame({
        "ticker": raw["ticker"].str.upper(),
        "published_at": pd.to_datetime(raw["published_reported"]).dt.tz_localize("UTC"),   # as reported; PIT rule applied later
        "fetched_at": pd.to_datetime(raw["collected_at"]).dt.tz_localize("UTC"),
        "title": raw["title"].fillna("").str.strip(), "summary": "",
        "source": raw["publisher"].where(raw["publisher"].fillna("") != "", raw["source_domain"]),
        "url": raw["url"], "provider": PROVIDER, "provider_fetch_kind": "rss_window_sample",
        "source_domain": raw["source_domain"].str.lower().str.replace("www.", "", regex=False),
        "time_precision": raw["time_precision"].map({"DATE_ONLY": "LOW", "EXACT": "EXACT"}).fillna("LOW"),
        "section": "google_news", "topics": raw["topics"], "orig_symbol": raw["ticker"].str.upper(),
    })
    df = df[df["title"] != ""].drop_duplicates(subset=["ticker", "title", "published_at"])
    key = df["ticker"] + "|" + df["title"] + "|" + df["published_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df["article_hash"] = key.map(lambda k: hashlib.sha1(k.encode("utf-8")).hexdigest())
    df["article_id"] = df["article_hash"].str[:20]
    df = enrich(df.reset_index(drop=True), cfg)
    return df[UNIFIED_COLUMNS].sort_values("published_at").reset_index(drop=True)


def coverage(tickers: List[str]) -> Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]]:
    """Inclusive covered intervals per ticker = successfully fetched windows [from, to)."""
    h = harvester()
    return {t: [(a, b - pd.Timedelta(days=1)) for a, b in h.coverage_intervals(t)] for t in tickers if h.coverage_intervals(t)}


def run() -> Dict[str, int]:
    cfg, h, out = load_news_config(), harvester(), {}
    for t in universe_tickers():
        df = unified(h.load_articles(t), cfg)
        if len(df):
            df.to_parquet(RECENT_DIR / f"{t}_news.parquet", index=False)
        out[t] = len(df)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    r = run()
    print(f"{sum(r.values()):,} articles for {sum(1 for v in r.values() if v)} tickers")
