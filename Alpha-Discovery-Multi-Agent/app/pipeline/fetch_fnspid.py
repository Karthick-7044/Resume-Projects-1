"""Extracts the universe's FNSPID news (2013-2023) via range requests; resumable.

    python -m app.pipeline.fetch_fnspid
Never stores the full 29 GB of source files: rows are filtered while streaming.
"""
import logging
from app.data.providers.fnspid_provider import FnspidExtractor
from app.pipeline.harvest_news import universe_tickers

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ex = FnspidExtractor(universe_tickers())
    print("all_external kept:", ex.run_all_external(), flush=True)
    print("nasdaq kept:", ex.run_nasdaq(), flush=True)
    parts = ex.load_parts()
    print("total raw rows kept:", len(parts), flush=True)
