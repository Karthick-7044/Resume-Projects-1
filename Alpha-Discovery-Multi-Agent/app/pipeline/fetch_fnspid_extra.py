"""Extracts FNSPID news for the CANDIDATE universe (excluding tickers already extracted) into a separate folder.

    python -m app.pipeline.fetch_fnspid_extra blocks [v3]    # fast sorted-block part of the 23 GB file
    python -m app.pipeline.fetch_fnspid_extra streams [v3]   # unsorted tail + All_external (about 11 GB, resumable)

"v2" (default) = data/config/universe_candidates.csv -> data/raw/news_fnspid_u2
"v3"           = data/config/universe_candidates_v3.csv (S&P 500 names not screened in v2) -> data/raw/news_fnspid_u3
"""
import logging
import sys

import pandas as pd

from app.config.settings import CONFIG_DIR, DATA_DIR
from app.data.providers.fnspid_provider import FnspidExtractor
from app.pipeline.harvest_news import universe_tickers

EXTRA_DIR = DATA_DIR / "raw" / "news_fnspid_u2"
# v3 streams run concurrently with the v3 blocks, so they get their own folder (separate progress.json)
EXTRA_DIRS = {"v2": EXTRA_DIR, "v3": DATA_DIR / "raw" / "news_fnspid_u3", "v3s": DATA_DIR / "raw" / "news_fnspid_u3s",
              "v3b": DATA_DIR / "raw" / "news_fnspid_u3b"}
CANDIDATE_FILES = {"v2": CONFIG_DIR / "universe_candidates.csv", "v3": CONFIG_DIR / "universe_candidates_v3.csv"}


def candidate_tickers(version: str = "v2"):
    cand = pd.read_csv(CANDIDATE_FILES[version])["ticker"].str.upper().tolist()
    have = set(universe_tickers())
    if version != "v2":   # already screened in v2
        have |= set(pd.read_csv(CANDIDATE_FILES["v2"])["ticker"].str.upper())
    return [t for t in cand if t not in have]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "blocks"
    version = sys.argv[2] if len(sys.argv) > 2 else "v2"
    start = sys.argv[3] if len(sys.argv) > 3 else ""   # optional: only tickers >= start (third parallel worker)
    folder = EXTRA_DIRS[{"streams": "v3s", "blocks_rev": "v3b"}.get(mode, version) if version == "v3" else version]
    if start:
        folder = folder.parent / f"{folder.name}_{start}"
    ex = FnspidExtractor([t for t in candidate_tickers(version) if t >= start], raw_dir=folder)
    ex.wanted = ex.tickers                      # no alias symbols for the extra universe
    print(f"{len(ex.tickers)} candidate tickers", flush=True)
    if mode in ("blocks", "blocks_rev"):   # blocks_rev: second worker walking the sorted list from the end
        print("blocks kept:", ex.run_nasdaq(blocks_only=True, reverse=mode == "blocks_rev"), flush=True)
    else:
        print("tail kept:", ex.run_nasdaq(tail_only=True), flush=True)
        print("all_external kept:", ex.run_all_external(), flush=True)
    print("raw rows so far:", len(ex.load_parts()), flush=True)
