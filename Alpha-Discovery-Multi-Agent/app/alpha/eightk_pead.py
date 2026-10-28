"""One pre-specified event hypothesis from SEC 8-K filings: post-earnings-announcement drift (PEAD) by the earnings
announcement return (EAR; Brandt, Kishore, Santa-Clara & Venkatachalam, 2008).

    python -m app.alpha.eightk_pead [--panel path --tag ""]

Specification (fixed before evaluation, not tuned):
  * event      : 8-K with Item 2.02 (Results of Operations), EDGAR acceptance time converted to US/Eastern;
                 day 0 = acceptance date if accepted before 16:00 ET on a trading day, otherwise the next trading day
  * EAR        : stock return minus equal-weight universe return, cumulated over days 0 and +1
  * signal     : from the close of day +1 (when EAR is fully known) for 63 trading days, cs_rank(EAR); NaN otherwise
  * evaluation : daily rank IC (Newey-West t), staggered 21-day dollar-neutral portfolio net of 10 bps, FF5+Mom alpha;
                 2013-2023 and 2024-2025 reported separately. It is ONE hypothesis, so no library-size deflation applies,
                 but it is counted in the paper's total trial count.
"""
import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from app.alpha.backtester import MIN_BREADTH, perf_stats
from app.alpha.cost_aware import evaluate, rank_ls, staggered
from app.alpha.ff_attribution import load_factors, regress
from app.alpha.library_tests import hac_t
from app.config.settings import ALPHA_RESULTS_DIR, MARKET_TIMEZONE, UNIFIED_PANEL_DIR
from app.data.providers.sec_8k_provider import EVENTS_PATH
from app.features.cross_sectional import CrossSectionalFeatureEngine

logger = logging.getLogger("PEAD")
HOLD_DAYS = 63
SPANS = {"2013_2023": ("2013-01-01", "2023-12-31"), "2024_2025": ("2024-01-01", "2025-12-31")}


def ear_signal(events: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    days = close.index
    ret = close.pct_change(fill_method=None)
    abn = ret.sub(ret.mean(axis=1), axis=0)
    sig = pd.DataFrame(np.nan, index=days, columns=close.columns)
    ev = events[events["form"].eq("8-K") & events["items"].fillna("").str.contains(r"\b2\.02\b")].copy()
    et = ev["acceptance_datetime"].dt.tz_convert(MARKET_TIMEZONE)
    after_close = (et.dt.hour >= 16)
    d = pd.to_datetime(et.dt.date)
    pos = days.searchsorted(d, side="left")                    # first trading day on/after the acceptance date
    on_trading_day = (pos < len(days)) & (days[np.minimum(pos, len(days) - 1)] == d.values)
    pos = np.where(after_close.values & on_trading_day, pos + 1, pos)
    ev["d0"] = pos
    for t, g in ev.groupby("ticker"):
        if t not in sig.columns:
            continue
        for p0 in sorted(set(g["d0"])):
            if p0 + 1 >= len(days):
                continue
            ear = abn[t].iloc[p0:p0 + 2].sum(min_count=2)
            if np.isfinite(ear):
                sig.iloc[p0 + 1:p0 + 1 + HOLD_DAYS, sig.columns.get_loc(t)] = ear   # later events overwrite earlier
    return sig


def run(panel_path: Path = None, tag: str = "") -> dict:
    panel = pd.read_parquet(panel_path or UNIFIED_PANEL_DIR / "master_panel.parquet")
    panel["date"] = pd.to_datetime(panel["date"])
    close = panel.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    lab = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    lab["date"] = pd.to_datetime(lab["date"])
    fwd = lab.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index().reindex(index=close.index, columns=close.columns)
    events = pd.read_parquet(EVENTS_PATH)
    sig = ear_signal(events, close)
    rank = sig.rank(axis=1)
    ic = rank.corrwith(fwd.rank(axis=1).where(sig.notna()), axis=1)
    ic[sig.notna().sum(axis=1) < MIN_BREADTH] = np.nan
    W = staggered(rank_ls(sig), 21)
    fac = load_factors()
    out = {"events_item_2_02": int(events["items"].fillna("").str.contains(r"\b2\.02\b").sum()),
           "tickers_with_events": int(events["ticker"].nunique()), "hold_days": HOLD_DAYS, "spans": {}}
    for span, (lo, hi) in SPANS.items():
        m = (close.index >= lo) & (close.index <= hi)
        live = pd.Series(m & (sig.notna().sum(axis=1) >= MIN_BREADTH).values, index=close.index)
        r = evaluate(W, fwd.fillna(0.0), live)
        icx = ic[m].dropna()
        out["spans"][span] = {"days_live": int(live.sum()), "median_breadth": float(sig[m].notna().sum(axis=1).median()),
                              "mean_ic": float(icx.mean()), "ic_t_hac": hac_t(icx), **r["stats"],
                              "ff": regress(r["net"], fac)}
    (ALPHA_RESULTS_DIR / f"eightk_pead{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    r = run(Path(a.panel) if a.panel else None, a.tag)
    print("Item 2.02 events:", r["events_item_2_02"])
    for s, v in r["spans"].items():
        ff = v["ff"]
        print(f"{s}: breadth {v['median_breadth']:.0f}, IC {v['mean_ic']:+.4f} (HAC t {v['ic_t_hac']:+.2f}), net Sharpe {v['net_sharpe']:+.2f}, "
              f"gross {v['gross_sharpe']:+.2f}, turnover {v['annual_turnover']:.1f}x, FF alpha {ff.get('alpha_ann', float('nan')):+.4f} "
              f"(t {ff.get('alpha_t', float('nan')):+.2f})")
