"""Fills the 2024-2025 news gap (FNSPID ends 2023-12-31) with Google News RSS headlines for the whole universe.

    python -m app.pipeline.harvest_news_recent [TICKER ...]

Sample mode: 14-day windows, NOT split when Google's ~100-item cap is hit (such windows are flagged truncated), so the
result is a capped headline SAMPLE per ticker and fortnight, not a complete archive. Resumable; raw responses are kept
in data/raw/news/gnews_recent/. Provider name in the unified layer: google_news_rss.
"""
import logging
import sys

from app.config.settings import DEFAULT_END_DATE, RAW_NEWS_DIR
from app.data.providers.gnews_provider import GoogleNewsHarvester
from app.pipeline.harvest_news import universe_tickers

RECENT_DIR = RAW_NEWS_DIR / "gnews_recent"
START, END, WINDOW_DAYS = "2024-01-01", DEFAULT_END_DATE, 14


def harvester() -> GoogleNewsHarvester:
    return GoogleNewsHarvester(raw_dir=RECENT_DIR, start_date=START, end_date=END, window_days=WINDOW_DAYS,
                               split_truncated=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    h = harvester()
    for t in [x.upper() for x in sys.argv[1:]] or universe_tickers():
        n = h.harvest(t)
        print(f"{t}: fetched {n} windows; total requests {h.requests_made}", flush=True)
    print(h.coverage_table(universe_tickers()).to_string())
