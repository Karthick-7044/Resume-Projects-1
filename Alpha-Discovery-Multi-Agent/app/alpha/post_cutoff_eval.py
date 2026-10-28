"""Post-knowledge-cutoff test of the v4 LLM signals (all choices fixed BEFORE looking at the test window).

    python -m app.alpha.post_cutoff_eval [--start 2025-01-01 --end 2026-10-23]

Signals (each a rank-average composite, NaN-tolerant):
  llm_v4_novel  : every v4/v5 LLM formula the Critic ACCEPTED (passed novelty <= 0.5 and validation Sharpe after costs > 0),
                  generated from data <= 2024 only - the headline signal
  llm_v4_all    : every valid v4/v5 LLM formula (no Critic) - shows what the Critic adds
  kb_composite  : the knowledge-base library composite (all 70 formulas) - built-in benchmark
Per signal on the test window:
  rank IC (HAC t), residual IC after the 7 style factors (HAC t), staggered monthly long-short gross/net Sharpe,
  long-only top quintile minus equal-weight (net Sharpe), turnover, FF5+Mom alpha of the net long-short series.
Multiple testing: Holm over the FOUR pre-registered tests of the headline signal (IC, residual IC, L/S net, L/O net),
one-sided; the other signals are reported for comparison only.
"""
import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.alpha import cost_aware as ca
from app.alpha.backtester import MIN_BREADTH
from app.alpha.dsl import FactorEvaluator
from app.alpha.ff_attribution import load_factors, regress
from app.alpha.library_tests import hac_t
from app.alpha.novelty import STYLES, _rank
from app.alpha.walkforward import holm, load_library
from app.config.settings import ALPHA_EXPERIMENTS_DIR, ALPHA_RESULTS_DIR, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine


def v4_formulas(accepted_only: bool) -> list:
    out = []
    for p in sorted(ALPHA_RESULTS_DIR.glob("ablation_results_recent_llm_v[45]*.json")):
        for e in json.load(open(p))["configs"]["Full"]["experiments"]:
            ep = ALPHA_EXPERIMENTS_DIR / f"{e['experiment_id']}.json"
            src = json.load(open(ep)).get("source", "") if ep.exists() else ""
            if not str(src).startswith("llm") or e["verdict"] == "INVALID" or e["train_rank_ic"] is None:
                continue
            if accepted_only and e["verdict"] != "ACCEPT":
                continue
            if e["formula"] not in out:
                out.append(e["formula"])
    return out


def composite(ev, formulas, index, columns):
    ranks = [ev.evaluate(f).reindex(index=index, columns=columns).rank(axis=1, pct=True) for f in formulas]
    return pd.concat(ranks).groupby(level=0).mean().reindex(index)


def residual_ic_series(ev, sig, fwd):
    f = _rank(sig)
    styles = {s: _rank(ev.evaluate(e).reindex_like(f)) for s, e in STYLES.items()}
    out = {}
    for d in f.index:
        y = f.loc[d]
        X = pd.concat([styles[s].loc[d] for s in styles], axis=1)
        ok = y.notna() & X.notna().all(axis=1) & fwd.loc[d].notna()
        if ok.sum() < 20:
            continue
        Xo = np.column_stack([np.ones(ok.sum()), X[ok].values])
        beta, *_ = np.linalg.lstsq(Xo, y[ok].values, rcond=None)
        resid = pd.Series(y[ok].values - Xo @ beta, index=y[ok].index)
        out[d] = resid.corr(fwd.loc[d][ok], method="spearman")
    return pd.Series(out)


def evaluate_signal(ev, sig, fwd, fac) -> dict:
    live = sig.notna().sum(axis=1) >= MIN_BREADTH
    ic = sig.rank(axis=1).corrwith(fwd.rank(axis=1).where(sig.notna()), axis=1)[live].dropna()
    ric = residual_ic_series(ev, sig, fwd).dropna()
    ls = ca.evaluate(ca.staggered(ca.rank_ls(sig), 21), fwd.fillna(0.0), live)
    bench = fwd.where(sig.notna()).mean(axis=1)
    lo = ca.evaluate(ca.staggered(ca.top_quintile(sig), 21), fwd.fillna(0.0), live, bench)
    t_ic, t_ric = hac_t(ic), hac_t(ric)
    p1 = lambda t: float(1 - norm.cdf(t)) if np.isfinite(t) else None
    return {
        "days": int(live.sum()), "rank_ic": float(ic.mean()), "rank_ic_t": t_ic, "p_ic": p1(t_ic),
        "residual_ic": float(ric.mean()), "residual_ic_t": t_ric, "p_residual_ic": p1(t_ric),
        "ls_gross_sharpe": ls["stats"]["gross_sharpe"], "ls_net_sharpe": ls["stats"]["net_sharpe"],
        "ls_net_ann_return": ls["stats"]["net_ann_return"], "ls_turnover": ls["stats"]["annual_turnover"],
        "p_ls_net": ls["stats"]["net_p_one_sided"],
        "lo_active_gross_sharpe": lo["stats"]["gross_sharpe"], "lo_active_net_sharpe": lo["stats"]["net_sharpe"],
        "lo_active_net_ann_return": lo["stats"]["net_ann_return"], "p_lo_net": lo["stats"]["net_p_one_sided"],
        "ff_ls_net": regress(ls["net"], fac), "ff_lo_active_net": regress(lo["net"], fac),
    }


def run(start: str, end: str) -> dict:
    panel = pd.read_parquet(UNIFIED_PANEL_DIR / "master_panel.parquet")
    lab = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    lab["date"] = pd.to_datetime(lab["date"])
    fwd_all = lab.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index()
    days = fwd_all.index[(fwd_all.index >= start) & (fwd_all.index <= end)]
    fwd = fwd_all.loc[days]
    ev = FactorEvaluator(panel)
    fac = load_factors()
    signals = {"llm_v4_novel": v4_formulas(True), "llm_v4_all": v4_formulas(False),
               "kb_composite": [x["formula"] for x in load_library("offline")]}
    out = {"test_window": [start, end], "panel_end": str(fwd_all.index.max().date()), "universe": int(fwd.shape[1]),
           "n_formulas": {k: len(v) for k, v in signals.items()}, "formulas_llm_v4_novel": signals["llm_v4_novel"], "signals": {}}
    for name, fs in signals.items():
        if fs:
            out["signals"][name] = evaluate_signal(ev, composite(ev, fs, days, fwd.columns), fwd, fac)
    h = out["signals"].get("llm_v4_novel")
    if h:
        adj = holm({"rank_ic": h["p_ic"], "residual_ic": h["p_residual_ic"], "ls_net": h["p_ls_net"], "lo_net": h["p_lo_net"]})
        h["holm"] = adj
    (ALPHA_RESULTS_DIR / "post_cutoff_eval.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    from app.config.settings import ALPHA_TEST_END
    r = run(a.start, a.end or ALPHA_TEST_END)
    print("test", r["test_window"], "panel end", r["panel_end"], "formulas", r["n_formulas"])
    for k, v in r["signals"].items():
        ff = v["ff_ls_net"]
        print(f"{k:14s} IC {v['rank_ic']:+.4f} (t {v['rank_ic_t']:+.2f}) resid IC {v['residual_ic']:+.4f} (t {v['residual_ic_t']:+.2f}) "
              f"L/S gross {v['ls_gross_sharpe']:+.2f} net {v['ls_net_sharpe']:+.2f} | L/O net {v['lo_active_net_sharpe']:+.2f} | "
              f"FF alpha {ff.get('alpha_ann', float('nan')):+.3f} (t {ff.get('alpha_t', float('nan')):+.2f})" + (f" | Holm {v['holm']}" if 'holm' in v else ""))
