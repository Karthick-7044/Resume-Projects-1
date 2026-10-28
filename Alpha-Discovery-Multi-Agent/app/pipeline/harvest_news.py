"""Harvests historical news for the universe with the in-house Google News RSS harvester.

Resumable: windows already fetched are skipped, so it can be stopped and restarted at any time.
    python -m app.pipeline.harvest_news            # whole universe
    python -m app.pipeline.harvest_news AAPL MSFT  # selected tickers
"""
import argparse
import logging
from io import StringIO

import pandas as pd

from app.config.settings import UNIVERSE_FILE
from app.data.providers.gnews_provider import GoogleNewsHarvester


def universe_tickers():
    lines = [l for l in UNIVERSE_FILE.read_text().splitlines() if not l.strip().startswith("#")]
    return pd.read_csv(StringIO("\n".join(lines)))["ticker"].str.upper().tolist()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    a = ap.parse_args()
    h = GoogleNewsHarvester()
    tickers = [t.upper() for t in a.tickers] or universe_tickers()
    for t in tickers:
        n = h.harvest(t)
        print(f"{t}: fetched {n} windows; total requests {h.requests_made}", flush=True)
    print(h.coverage_table(tickers).to_string())
