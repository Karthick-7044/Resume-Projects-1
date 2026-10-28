"""Cost-aware portfolio construction for the walk-forward factor selections.

    python -m app.alpha.cost_aware [--tag ""]

The SAME out-of-sample signal as the walk-forward evaluation is used: in every test year Y the factor is the rank
average of the formulas the rule (naive / critic) selected from years < Y. Only the way the signal is traded changes.
All variants are fixed in advance (conventional parameter choices, no tuning on test years) and every variant is counted
as a trial in the multiple-testing correction (Holm over net Sharpe p-values, deflated Sharpe over the variant set).

Every rebalanced variant is a staggered-tranche portfolio (average over all rebalance-day phases), because a single
rebalance calendar made the Sharpe ratio depend strongly on the arbitrary choice of rebalance day.
Variants (net of 10 bps one-way per unit of turnover):
  ls_reb5 / ls_reb21 / ls_reb63 : dollar-neutral rank weights, rebalanced every 5 / 21 / 63 trading days
  ls_smooth_reb21               : signal smoothed with an exponential moving average (half-life 10 days), monthly rebalance
  ls_buffer                     : quintile long-short with a turnover buffer (enter top/bottom 20%, exit beyond 40%), weekly check
  lo_top_q_active               : long-only equal-weight top quintile minus the equal-weight universe, monthly rebalance
  ls_sector_neutral_reb21       : ranks demeaned within sector, monthly rebalance
"""
import argparse
import json
import logging

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.alpha.backtester import MIN_BREADTH, perf_stats
from app.alpha.dsl import FactorEvaluator
from app.alpha.stats import deflated_sharpe
from app.alpha.walkforward import SKIPNA_RULES, holm
from app.config.settings import ALPHA_RESULTS_DIR, ALPHA_TRANSACTION_COST_BPS, CONFIG_DIR, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine

logger = logging.getLogger("CostAware")
RULES = ["naive", "critic_v1", "critic", "composite", "literature"]


def oos_signal(ev: FactorEvaluator, folds: list, rule: str, index, columns, smooth_halflife: int = 0) -> pd.DataFrame:
    """Rank-average signal where the rows of year Y use the formulas selected for year Y (NaN in cash years)."""
    out = pd.DataFrame(np.nan, index=index, columns=columns)
    for fold in folds:
        fs = fold[rule]["selected"]
        if not fs:
            continue
        ranks = [ev.evaluate(f).reindex(index=index, columns=columns).rank(axis=1, pct=True) for f in fs]
        s = pd.concat(ranks).groupby(level=0).mean() if rule in SKIPNA_RULES else sum(ranks) / len(ranks)
        if smooth_halflife:
            s = s.ewm(halflife=smooth_halflife, min_periods=1).mean()   # backward-looking only
        m = index.year == fold["year"]
        out.loc[m] = s.loc[m].values
    return out


def hold(w: pd.DataFrame, every: int, phase: int = 0) -> pd.DataFrame:
    keep = np.zeros(len(w), dtype=bool)
    keep[phase::every] = True
    w = w.copy()
    w[~keep] = np.nan
    return w.ffill().fillna(0.0)


def staggered(w: pd.DataFrame, every: int) -> pd.DataFrame:
    """Average of the `every` phase-shifted portfolios (staggered tranches).

    A single rebalance calendar makes results depend on WHICH day of the cycle is used (the 5-day Sharpe of the same
    signal ranged from -0.14 to 0.51 across phases); averaging the tranches removes that arbitrary choice."""
    return sum(hold(w, every, p) for p in range(every)) / every


def rank_ls(sig: pd.DataFrame, groups: pd.Series = None) -> pd.DataFrame:
    rank = sig.rank(axis=1, pct=True)
    if groups is not None:
        g = groups.reindex(sig.columns)
        dem = rank.T.groupby(g.values).transform(lambda x: x - x.mean()).T
    else:
        dem = rank.sub(rank.mean(axis=1), axis=0)
    w = dem.div(dem.abs().sum(axis=1).replace(0, np.nan), axis=0)
    w[sig.notna().sum(axis=1) < MIN_BREADTH] = np.nan
    return w.fillna(0.0)


def buffer_ls(sig: pd.DataFrame, enter: float = 0.2, exit_: float = 0.4, every: int = 5) -> pd.DataFrame:
    """Staggered over the `every` check-day phases, like the rebalanced variants."""
    return sum(_buffer_ls(sig, enter, exit_, every, p) for p in range(every)) / every


def _buffer_ls(sig: pd.DataFrame, enter: float, exit_: float, every: int, phase: int) -> pd.DataFrame:
    pct = sig.rank(axis=1, pct=True).values
    state = np.zeros(pct.shape[1])
    W = np.zeros_like(pct)
    for t in range(len(pct)):
        p = pct[t]
        if np.isfinite(p).sum() < MIN_BREADTH:
            state[:] = 0
        elif t % every == phase:
            nan = ~np.isfinite(p)
            long_keep, short_keep = (state > 0) & (p >= 1 - exit_), (state < 0) & (p <= exit_)
            new = np.zeros_like(state)
            new[long_keep | (p >= 1 - enter)] = 1
            new[short_keep | (p <= enter)] = -1
            new[nan] = 0
            state = new
        nl, ns = (state > 0).sum(), (state < 0).sum()
        if nl and ns:
            W[t] = np.where(state > 0, 0.5 / nl, np.where(state < 0, -0.5 / ns, 0.0))
    return pd.DataFrame(W, index=sig.index, columns=sig.columns)


def top_quintile(sig: pd.DataFrame) -> pd.DataFrame:
    pct = sig.rank(axis=1, pct=True)
    top = (pct > 0.8).astype(float)
    w = top.div(top.sum(axis=1).replace(0, np.nan), axis=0)
    w[sig.notna().sum(axis=1) < MIN_BREADTH] = np.nan
    return w.fillna(0.0)


def evaluate(w: pd.DataFrame, fwd: pd.DataFrame, live: pd.Series, bench: pd.Series = None, cost_bps: float = ALPHA_TRANSACTION_COST_BPS) -> dict:
    gross = (w * fwd).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    net = gross - turnover * cost_bps / 1e4
    if bench is not None:
        gross, net = gross - bench, net - bench
    gross, net, turnover = gross[live], net[live], turnover[live]
    n = len(net)
    t = float(net.mean() / net.std(ddof=1) * np.sqrt(n)) if n > 2 and net.std(ddof=1) > 0 else float("nan")
    return {"net": net, "gross": gross,
            "stats": {**{f"net_{k}": v for k, v in perf_stats(net).items()}, "gross_sharpe": perf_stats(gross)["sharpe"],
                      "gross_ann_return": perf_stats(gross)["ann_return"], "annual_turnover": float(turnover.sum() / (n / 252)),
                      "net_t": t, "net_p_one_sided": float(1 - norm.cdf(t)) if np.isfinite(t) else None}}


def run(tag: str = "", panel_path=None) -> dict:
    wf = json.loads((ALPHA_RESULTS_DIR / f"walkforward_results{tag}.json").read_text())
    panel = pd.read_parquet(panel_path or UNIFIED_PANEL_DIR / "master_panel.parquet")
    labels = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    labels["date"] = pd.to_datetime(labels["date"])
    fwd = labels.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index()
    ev = FactorEvaluator(panel)
    sectors = None
    for f in ("universe.csv", "universe_candidates.csv"):
        u = pd.read_csv(CONFIG_DIR / f, comment="#")
        sectors = u.set_index("ticker")["sector"] if sectors is None else sectors.combine_first(u.set_index("ticker")["sector"])
    years = [f["year"] for f in wf["folds"]]
    test_days = fwd.index[(fwd.index.year >= min(years)) & (fwd.index.year <= max(years))]
    fwd_t = fwd.loc[test_days]
    bench_all = fwd_t.mean(axis=1)

    results, daily = {}, {}
    for rule in RULES:
        if not any(f[rule]["selected"] for f in wf["folds"]):
            results[f"{rule}:all_years_cash"] = {"note": "rule selected no formula in any test year"}
            continue
        sig = oos_signal(ev, wf["folds"], rule, test_days, fwd.columns)
        sig_s = oos_signal(ev, wf["folds"], rule, test_days, fwd.columns, smooth_halflife=10)
        live = sig.notna().sum(axis=1) >= MIN_BREADTH          # days with a position (not cash years)
        bench = fwd_t.where(sig.notna()).mean(axis=1).fillna(bench_all)
        W = rank_ls(sig)
        variants = {
            "ls_reb5": staggered(W, 5), "ls_reb21": staggered(W, 21), "ls_reb63": staggered(W, 63),
            "ls_smooth_reb21": staggered(rank_ls(sig_s), 21), "ls_buffer": buffer_ls(sig),
            "lo_top_q_active": staggered(top_quintile(sig), 21), "ls_sector_neutral_reb21": staggered(rank_ls(sig, sectors), 21),
        }
        for name, w in variants.items():
            r = evaluate(w, fwd_t, live, bench if name.startswith("lo_") else None)
            key = f"{rule}:{name}"
            results[key] = r["stats"]
            daily[f"{key}_net"], daily[f"{key}_gross"] = r["net"], r["gross"]
            logger.info(f"{key}: net Sharpe {r['stats']['net_sharpe']:.2f} gross {r['stats']['gross_sharpe']:.2f} "
                        f"turnover {r['stats']['annual_turnover']:.1f}x")
        lo = evaluate(staggered(top_quintile(sig), 21), fwd_t, live)
        results[f"{rule}:lo_top_q_absolute"] = {**lo["stats"], "note": "absolute long-only return (not a trial; market beta)"}
        daily[f"{rule}:lo_top_q_absolute_net"] = lo["net"]
        results[f"{rule}:benchmark_ew"] = {"ann_return": perf_stats(bench[live])["ann_return"], "sharpe": perf_stats(bench[live])["sharpe"]}

    trials = {k: v for k, v in results.items() if "net_t" in v and "note" not in v}
    adj = holm({k: v["net_p_one_sided"] for k, v in trials.items()})
    srs = [float(daily[f"{k}_net"].mean() / daily[f"{k}_net"].std(ddof=1)) for k in trials]
    for k in trials:
        results[k]["net_p_holm"] = adj.get(k)
        results[k]["dsr"] = deflated_sharpe(daily[f"{k}_net"].values, n_trials=len(trials), sr_trials=srs)["dsr"]
    out = {"cost_bps": ALPHA_TRANSACTION_COST_BPS, "test_years": years, "n_trials": len(trials), "variants": results}
    (ALPHA_RESULTS_DIR / f"cost_aware_results{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    pd.DataFrame(daily).to_parquet(ALPHA_RESULTS_DIR / f"cost_aware_daily{tag}.parquet")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    ap.add_argument("--panel", default=None)
    a = ap.parse_args()
    r = run(a.tag, a.panel)
    print(f"{'variant':38s} {'netSR':>6s} {'grossSR':>7s} {'netRet':>7s} {'turn':>6s} {'p':>6s} {'pHolm':>6s} {'DSR':>5s}")
    for k, v in r["variants"].items():
        if "net_sharpe" in v:
            print(f"{k:38s} {v['net_sharpe']:6.2f} {v['gross_sharpe']:7.2f} {v['net_ann_return']:7.3f} {v['annual_turnover']:6.1f} "
                  f"{v['net_p_one_sided']:6.3f} {v.get('net_p_holm') or float('nan'):6.3f} {v.get('dsr') or float('nan'):5.2f}")
