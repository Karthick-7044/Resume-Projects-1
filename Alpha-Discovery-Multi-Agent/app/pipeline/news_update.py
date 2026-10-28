"""News update CLI.

    python -m app.pipeline.news_update --mode backfill    # Finnhub 2024-01-01 -> today (probe-gated)
    python -m app.pipeline.news_update --mode daily       # last 3 days, append-only (schedule after US close)

The backfill first probes the key: if Finnhub rejects it, or returns no 2024 data on the free tier, it STOPS and
reports instead of continuing (override with --force only after reading the probe verdict). The daily mode does
not depend on 2024 history: it only needs a working key.
Scheduling (US market closes 16:00 ET = 20:00/21:00 UTC): see docs/NEWS_DAILY_SCHEDULE.md.
"""
import argparse
import logging
import sys
from datetime import date

from app.data.providers.finnhub_news_provider import FinnhubAuthError, FinnhubNewsProvider
from app.pipeline.harvest_news import universe_tickers

logger = logging.getLogger("NewsUpdate")


def probe_2024(provider: FinnhubNewsProvider, ticker: str) -> str:
    """Returns 'OK', 'EMPTY' (no 2024 data) or raises FinnhubAuthError."""
    items = provider._request(ticker, date(2024, 3, 1), date(2024, 3, 31))
    return "OK" if items else "EMPTY"


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["backfill", "daily"], required=True)
    ap.add_argument("--force", action="store_true", help="backfill even if the probe finds no 2024 data")
    ap.add_argument("--tickers", nargs="*")
    a = ap.parse_args(argv)
    tickers = [t.upper() for t in a.tickers] if a.tickers else universe_tickers()
    prov = FinnhubNewsProvider()
    try:
        if a.mode == "backfill":
            status = probe_2024(prov, tickers[0])
            if status == "EMPTY" and not a.force:
                logger.error("Probe: Finnhub returned NO data for March 2024. Stopping the backfill (use --force to run anyway).")
                return 1
            print(prov.backfill(tickers))
            print("materialized:", prov.materialize_backfill(tickers))
        else:
            print(prov.daily_update(tickers))
    except FinnhubAuthError as e:
        logger.error(f"Finnhub key problem: {e}. Set FINNHUB_API_KEY (environment or .env) and retry.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
