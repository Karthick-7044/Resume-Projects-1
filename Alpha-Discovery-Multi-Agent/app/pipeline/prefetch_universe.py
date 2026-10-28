"""Warms the raw caches (prices, splits, SEC facts) for every ticker in universe.csv; resumable (cache-aware).

    python -m app.pipeline.prefetch_universe            # universe.csv
    python -m app.pipeline.prefetch_universe v3         # the v3 candidate list (before screening)
"""
import logging
import sys

from app.config.settings import DEFAULT_END_DATE, DEFAULT_START_DATE
from app.data.providers.market_provider import YahooMarketDataProvider
from app.data.providers.sec_provider import EdgarSECDataProvider
from app.pipeline.harvest_news import universe_tickers

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    mp, sp = YahooMarketDataProvider(), EdgarSECDataProvider()
    if len(sys.argv) > 1 and sys.argv[1] == "v3":
        from app.pipeline.fetch_fnspid_extra import candidate_tickers
        tickers = candidate_tickers("v3")
    else:
        tickers = universe_tickers()
    for t in tickers:
        try:
            m = mp.fetch_daily(t, DEFAULT_START_DATE, DEFAULT_END_DATE)
            mp.fetch_splits(t)
            f = sp.fetch_company_facts(t)
            print(f"{t}: {len(m)} price rows, {len(f)} SEC facts, CIK {sp.get_cik(t)}", flush=True)
        except Exception as e:  # keep going: one failing ticker must not stop the rest
            print(f"{t}: FAILED {e}", flush=True)
