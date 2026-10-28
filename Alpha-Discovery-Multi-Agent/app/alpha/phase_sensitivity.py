"""Rebalance-phase sensitivity of the walk-forward signals.

    python -m app.alpha.phase_sensitivity [--panel path --tag ""]

With a single rebalance calendar every k days, the result depends on WHICH of the k days is used. For each rule and
k in {5, 21} this reports the gross and net (10 bps) Sharpe ratio of every phase and of the staggered average.
"""
import argparse
import json

import numpy as np
import pandas as pd

from app.alpha import cost_aware as ca
from app.alpha.dsl import FactorEvaluator
from app.config.settings import ALPHA_RESULTS_DIR, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine


def run(panel_path=None, tag: str = "", rules=("naive", "composite")) -> dict:
    wf = json.loads((ALPHA_RESULTS_DIR / f"walkforward_results{tag}.json").read_text())
    panel = pd.read_parquet(panel_path or UNIFIED_PANEL_DIR / "master_panel.parquet")
    lab = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    lab["date"] = pd.to_datetime(lab["date"])
    fwd = lab.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index()
    ev = FactorEvaluator(panel)
    years = [f["year"] for f in wf["folds"]]
    days = fwd.index[(fwd.index.year >= min(years)) & (fwd.index.year <= max(years))]
    f = fwd.loc[days]
    sr = lambda x: float(x.mean() / x.std() * np.sqrt(252))
    out = {}
    for rule in rules:
        W = ca.rank_ls(ca.oos_signal(ev, wf["folds"], rule, days, fwd.columns))
        for k in (5, 21):
            g_all, n_all = [], []
            for ph in range(k):
                w = ca.hold(W, k, ph)
                g = (w * f).sum(axis=1)
                t = w.diff().abs().sum(axis=1).fillna(0)
                g_all.append(sr(g))
                n_all.append(sr(g - t * 10 / 1e4))
            ws = ca.staggered(W, k)
            g = (ws * f).sum(axis=1)
            t = ws.diff().abs().sum(axis=1).fillna(0)
            out[f"{rule}_reb{k}"] = {"gross_min": min(g_all), "gross_mean": float(np.mean(g_all)), "gross_max": max(g_all),
                                     "net_min": min(n_all), "net_max": max(n_all), "staggered_gross": sr(g),
                                     "staggered_net": sr(g - t * 10 / 1e4)}
    (ALPHA_RESULTS_DIR / f"phase_sensitivity{tag}.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    for k, v in run(a.panel, a.tag).items():
        print(k, {kk: round(vv, 2) for kk, vv in v.items()})
