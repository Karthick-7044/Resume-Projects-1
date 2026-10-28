"""Universe v3 screen: v2 universe + every v3 candidate with >= 20 FNSPID articles in EVERY year 2013-2023.

    python -m app.pipeline.screen_universe [--apply]

The rule is the one used for v2 (same threshold, same years, same normalisation/dedup as the news build), applied to the
S&P 500 names in data/config/universe_candidates_v3.csv that were not screened before. Writes
data/alpha/results/universe_screen_u{N}.json (per-candidate counts and verdicts); --apply also writes the new
data/config/universe.csv, keeping the v2 file as data/config/universe_v2_36.csv.
"""
import argparse
import json
import logging
import shutil
from io import StringIO

import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import ALPHA_RESULTS_DIR, CONFIG_DIR, DATA_DIR, RAW_MARKET_DIR, UNIVERSE_FILE
from app.data.providers.fnspid_provider import FnspidExtractor
from app.pipeline.build_fnspid_news import coverage_table, normalize
from app.pipeline.fetch_fnspid_extra import candidate_tickers

logger = logging.getLogger("ScreenUniverse")
V3_DIRS = [DATA_DIR / "raw" / f"news_fnspid_{s}" for s in ("u3", "u3_H", "u3_M", "u3b", "u3s")]


def run(apply: bool = False) -> dict:
    cfg = load_news_config()
    cand = candidate_tickers("v3")
    raw = pd.concat([FnspidExtractor(cand, raw_dir=d).load_parts() for d in V3_DIRS if d.exists()], ignore_index=True)
    raw = raw[raw["symbol"].str.upper().isin(cand)]
    logger.info(f"{len(raw):,} raw rows for {raw['symbol'].nunique()} of {len(cand)} candidates")
    counts = {}
    for t, sub in raw.groupby(raw["symbol"].str.upper()):
        part, _ = normalize(sub, [t], cfg)
        counts[t] = part
    arts = pd.concat(counts.values(), ignore_index=True)
    cov = coverage_table(arts, cfg).reindex(cand, fill_value=0)
    thr = cfg["coverage"]["min_articles_per_ticker_year"]
    # a candidate without a cached Yahoo price history (taken private / renamed by 2026) cannot enter the panel
    no_prices = [t for t in cand if not (RAW_MARKET_DIR / f"{t}.parquet").exists()]
    passed = [t for t in cov.index[(cov >= thr).all(axis=1)] if t not in no_prices]
    lines = [l for l in UNIVERSE_FILE.read_text().splitlines() if not l.strip().startswith("#")]
    u2 = pd.read_csv(StringIO("\n".join(lines)))
    n = len(u2) + len(passed)
    res = {"rule": f">= {thr} FNSPID articles in every year 2013-2023", "candidates": len(cand), "passed": len(passed),
           "universe_size": n, "passed_tickers": passed, "excluded_no_price_history": no_prices,
           "counts": {t: {int(y): int(v) for y, v in row.items()} for t, row in cov.iterrows()},
           "min_year_count": {t: int(cov.loc[t].min()) for t in cov.index}}
    ALPHA_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (ALPHA_RESULTS_DIR / f"universe_screen_u{n}.json").write_text(json.dumps(res, indent=1))
    if apply:
        keep = CONFIG_DIR / f"universe_v2_{len(u2)}.csv"
        if not keep.exists():
            shutil.copy(UNIVERSE_FILE, keep)
        c3 = pd.read_csv(CONFIG_DIR / "universe_candidates_v3.csv").set_index("ticker").loc[passed].reset_index()
        c3["active"], c3["universe_version"] = True, "v3.0"
        new = pd.concat([u2, c3[u2.columns]], ignore_index=True)
        header = (f"# Ticker Universe Configuration (v3.0, {n} stocks)\n"
                  f"# v2 (36 stocks) plus every S&P 500 candidate in universe_candidates_v3.csv ({len(cand)} screened) with >= {thr} FNSPID\n"
                  f"# articles in EVERY year 2013-2023 ({len(passed)} passed). Same rule as v2. Survivorship bias: present-day constituents only.\n")
        UNIVERSE_FILE.write_text(header + new.to_csv(index=False))
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    r = run(a.apply)
    print(f"{r['passed']} of {r['candidates']} candidates passed -> universe of {r['universe_size']}")
    near = sorted(((t, m) for t, m in r["min_year_count"].items() if t not in r["passed_tickers"]), key=lambda x: -x[1])[:15]
    print("closest misses (min articles in a year):", near)
