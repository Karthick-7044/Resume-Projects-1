"""Refreshes the cached raw sources that do not update incrementally (SEC company facts, FRED macro, SEC 8-K) so the
next orchestrator run extends to DEFAULT_END_DATE. Prices are incremental and are extended by the orchestrator itself.

    python -m app.pipeline.refresh_to_latest
"""
import logging

from app.config.settings import REGIME_HISTORY_START
from app.data.providers.macro_provider import FredMacroProvider
from app.data.providers.sec_8k_provider import run as refresh_8k
from app.data.providers.sec_provider import EdgarSECDataProvider
from app.pipeline.harvest_news import universe_tickers

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sp, failed = EdgarSECDataProvider(), []
    for t in universe_tickers():
        try:
            sp.fetch_company_facts(t, force_refresh=True)
        except Exception as e:  # one ticker must not stop the rest
            failed.append(t)
            logging.warning(f"{t}: {e}")
    print("SEC company facts refreshed; failed:", failed, flush=True)
    m = FredMacroProvider().fetch_all(REGIME_HISTORY_START, force_refresh=True)
    print("FRED macro refreshed to", m["date"].max() if "date" in m else "?", flush=True)
    ev = refresh_8k(refresh=True)
    print("8-K events:", len(ev), "latest", ev["filing_date"].max(), flush=True)
    print("REFRESH DONE", flush=True)
