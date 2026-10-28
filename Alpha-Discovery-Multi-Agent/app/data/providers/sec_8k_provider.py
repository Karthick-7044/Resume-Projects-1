"""SEC EDGAR 8-K filing events (submissions API, no key; declared User-Agent; <= 5 requests/second).

    python -m app.data.providers.sec_8k_provider [TICKER ...]

For every ticker the full filing history is read from https://data.sec.gov/submissions/CIK##########.json plus its
paginated history files, cached under data/raw/sec/submissions/, and the 8-K / 8-K/A rows are written to
data/processed/sec/eightk_events.parquet with: ticker, form, filing_date, acceptance_datetime (UTC), items (e.g. "2.02,9.01").
Point-in-time: an event is usable from the first trading day AFTER its acceptance date (SEC_AVAILABILITY_LAG_DAYS),
whatever the time of day, matching the treatment of other EDGAR data in this project.
"""
import json
import logging
import sys
import time

import pandas as pd
import requests

from app.config.settings import PROCESSED_DATA_DIR, RAW_SEC_DIR, SEC_REQUEST_TIMEOUT, SEC_USER_AGENT
from app.data.providers.sec_provider import EdgarSECDataProvider
from app.pipeline.harvest_news import universe_tickers

logger = logging.getLogger("SEC8K")
SUB_DIR = RAW_SEC_DIR / "submissions"
EVENTS_PATH = PROCESSED_DATA_DIR / "sec" / "eightk_events.parquet"
MIN_INTERVAL = 0.2
_last = [0.0]


def _get_json(url: str):
    for attempt in range(1, 5):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        r = requests.get(url, headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=SEC_REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 503):
            time.sleep(2 * attempt)
            continue
        r.raise_for_status()
    raise RuntimeError(f"SEC request failed: {url}")


def _cached(name: str, url: str, refresh: bool = False):
    SUB_DIR.mkdir(parents=True, exist_ok=True)
    p = SUB_DIR / name
    if refresh or not p.exists():
        p.write_text(json.dumps(_get_json(url)))
    return json.loads(p.read_text())


def _rows(block: dict) -> pd.DataFrame:
    keys = ["form", "filingDate", "acceptanceDateTime", "items"]
    return pd.DataFrame({k: block.get(k, []) for k in keys})


def fetch_8k(ticker: str, cik: str, refresh: bool = False) -> pd.DataFrame:
    # the main file holds the most recent filings (refresh it); older history pages never change
    sub = _cached(f"CIK{cik}.json", f"https://data.sec.gov/submissions/CIK{cik}.json", refresh=refresh)
    frames = [_rows(sub["filings"]["recent"])]
    for f in sub["filings"].get("files", []):
        frames.append(_rows(_cached(f["name"], f"https://data.sec.gov/submissions/{f['name']}")))
    df = pd.concat(frames, ignore_index=True)
    df = df[df["form"].isin(["8-K", "8-K/A"])].copy()
    df["ticker"] = ticker
    df["cik"] = cik
    df["filing_date"] = pd.to_datetime(df["filingDate"])
    df["acceptance_datetime"] = pd.to_datetime(df["acceptanceDateTime"], utc=True, errors="coerce")
    return df.rename(columns={"items": "items"})[["ticker", "cik", "form", "filing_date", "acceptance_datetime", "items"]]


def run(tickers=None, refresh: bool = False) -> pd.DataFrame:
    sp = EdgarSECDataProvider()
    out = []
    for t in tickers or universe_tickers():
        # a ticker can map to several CIKs over time (e.g. reorganisations); take all of them
        for cik in sp.get_cik_lineage(t) or [sp.get_cik(t)]:
            if not cik:
                continue
            try:
                out.append(fetch_8k(t, str(cik).zfill(10), refresh=refresh))
            except Exception as e:  # one ticker must not stop the rest
                logger.warning(f"{t} CIK {cik}: {e}")
    ev = pd.concat(out, ignore_index=True).drop_duplicates(["ticker", "acceptance_datetime", "form", "items"])
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ev.to_parquet(EVENTS_PATH, index=False)
    return ev


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args = [a for a in sys.argv[1:] if a != "--refresh"]
    ev = run(args or None, refresh="--refresh" in sys.argv)
    print(len(ev), "8-K filings;", ev["ticker"].nunique(), "tickers;", ev["filing_date"].min().date(), "to", ev["filing_date"].max().date())
    print("filings with Item 2.02 (earnings):", int(ev["items"].str.contains("2.02").sum()))
