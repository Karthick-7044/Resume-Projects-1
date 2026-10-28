"""Factor-level multiple-testing over the whole formula library.

    python -m app.alpha.library_tests [--panel path --tag ""]

For every distinct valid formula the discovery loop tested, and for each evaluation span:
  * mean daily rank IC with a Newey-West (HAC, 10 lags) t-statistic, one-sided p-value (H1: IC > 0)
  * net long-short Sharpe (rank weights, 21-day rebalance, 10 bps) with HAC t-statistic of the mean daily net return
  * Holm and Bonferroni adjusted p-values across the library (family = all formulas)
  * White's (2000) reality check for the best formula, stationary bootstrap (Politis & Romano), mean block 20 days
Spans: 2013-2023 is the FNSPID window that the library was DISCOVERED on (any significance there is in-sample and
optimistic); 2025 is the untouched hold-out (never used for discovery, selection or tuning).
"""
import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

from app.alpha.backtester import Backtester
from app.alpha.dsl import FactorEvaluator
from app.alpha.walkforward import holm, load_library
from app.config.settings import ALPHA_RESULTS_DIR, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine

logger = logging.getLogger("LibraryTests")
SPANS = {"discovery_2013_2023": ("2013-01-01", "2023-12-31"), "holdout_2025": ("2025-01-01", "2025-12-31")}
HAC_LAGS, BOOT, BLOCK = 10, 1000, 20


def hac_t(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) < 30 or x.std() == 0:
        return float("nan")
    m = sm.OLS(x.values, np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return float(m.tvalues[0])


def stationary_bootstrap_idx(n: int, block: int, rng) -> np.ndarray:
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    restart = rng.random(n) < 1.0 / block
    starts = rng.integers(n, size=n)
    for t in range(1, n):
        idx[t] = starts[t] if restart[t] else (idx[t - 1] + 1) % n
    return idx


def reality_check(X: np.ndarray, seed: int = 0) -> dict:
    """White's reality check, H0: max_k E[X_k] <= 0. X is days x strategies (NaN filled with 0)."""
    n = len(X)
    mu = X.mean(0)
    V = np.sqrt(n) * mu.max()
    rng = np.random.default_rng(seed)
    Vb = np.empty(BOOT)
    for b in range(BOOT):
        Vb[b] = np.sqrt(n) * (X[stationary_bootstrap_idx(n, BLOCK, rng)].mean(0) - mu).max()
    return {"best_index": int(mu.argmax()), "p_value": float((Vb >= V).mean()), "n_days": int(n), "n_strategies": int(X.shape[1])}


def run(panel_path: Path = None, tag: str = "", library: str = "offline") -> dict:
    panel = pd.read_parquet(panel_path or UNIFIED_PANEL_DIR / "master_panel.parquet")
    labels = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    bt = Backtester(labels, window="fnspid", rebalance_days=21)
    ev = FactorEvaluator(panel)
    lib = load_library(library)
    ics, nets = {}, {}
    for item in lib:
        s = bt.run(ev.evaluate(item["formula"]), periods=["train"])["_series"]
        ics[item["formula"]], nets[item["formula"]] = s["ic"], s["net"]
    IC, NET = pd.DataFrame(ics), pd.DataFrame(nets)
    out = {"library": library, "library_size": len(lib), "universe_size": int(panel["ticker"].nunique()),
           "panel_end": str(pd.to_datetime(panel["date"]).max().date()), "spans": {}}
    for span, (lo, hi) in SPANS.items():
        ic = IC[(IC.index >= lo) & (IC.index <= hi)]
        net = NET[(NET.index >= lo) & (NET.index <= hi)]
        net = net[net.abs().sum(axis=1) > 0]
        if ic.dropna(how="all").shape[0] < 60:
            out["spans"][span] = {"note": "insufficient data"}
            continue
        rows = {}
        for f in IC.columns:
            t_ic, t_net = hac_t(ic[f]), hac_t(net[f])
            rows[f] = {"mean_ic": float(ic[f].mean()), "ic_t_hac": t_ic,
                       "ic_p": float(1 - norm.cdf(t_ic)) if np.isfinite(t_ic) else None,
                       "net_sharpe": float(net[f].mean() / net[f].std() * np.sqrt(252)) if net[f].std() > 0 else None,
                       "net_t_hac": t_net, "net_p": float(1 - norm.cdf(t_net)) if np.isfinite(t_net) else None}
        for key in ("ic_p", "net_p"):
            adj = holm({f: r[key] for f, r in rows.items()})
            m = sum(1 for r in rows.values() if r[key] is not None)
            for f, r in rows.items():
                r[f"{key}_holm"] = adj.get(f)
                r[f"{key}_bonferroni"] = min(1.0, r[key] * m) if r[key] is not None else None
        rc_ic = reality_check(ic.fillna(0.0).values)
        rc_net = reality_check(net.fillna(0.0).values, seed=1)
        out["spans"][span] = {
            "range": [lo, hi], "days": int(len(ic)),
            "n_raw_p_below_0.05_ic": sum(1 for r in rows.values() if r["ic_p"] is not None and r["ic_p"] < 0.05),
            "n_holm_below_0.05_ic": sum(1 for r in rows.values() if r["ic_p_holm"] is not None and r["ic_p_holm"] < 0.05),
            "n_raw_p_below_0.05_net": sum(1 for r in rows.values() if r["net_p"] is not None and r["net_p"] < 0.05),
            "n_holm_below_0.05_net": sum(1 for r in rows.values() if r["net_p_holm"] is not None and r["net_p_holm"] < 0.05),
            "reality_check_ic": {**rc_ic, "best_formula": IC.columns[rc_ic["best_index"]]},
            "reality_check_net": {**rc_net, "best_formula": IC.columns[rc_net["best_index"]]},
            "formulas": rows,
        }
    (ALPHA_RESULTS_DIR / f"library_tests{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--library", choices=["offline", "llm", "llm_v4", "llm_v5"], default="offline")
    a = ap.parse_args()
    r = run(Path(a.panel) if a.panel else None, a.tag, a.library)
    print("panel end", r["panel_end"], "library", r["library_size"])
    for span, s in r["spans"].items():
        if "formulas" not in s:
            print(span, s)
            continue
        print(f"{span}: raw p<.05 IC {s['n_raw_p_below_0.05_ic']}, Holm {s['n_holm_below_0.05_ic']} | raw p<.05 net {s['n_raw_p_below_0.05_net']}, "
              f"Holm {s['n_holm_below_0.05_net']} | RC p (IC) {s['reality_check_ic']['p_value']:.3f} best {s['reality_check_ic']['best_formula']} | "
              f"RC p (net) {s['reality_check_net']['p_value']:.3f}")
        top = sorted(s["formulas"].items(), key=lambda kv: -(kv[1]["ic_t_hac"] if np.isfinite(kv[1]["ic_t_hac"]) else -9))[:5]
        for f, v in top:
            print(f"   {f[:70]:70s} IC {v['mean_ic']:+.4f} t {v['ic_t_hac']:+.2f} pHolm {v['ic_p_holm']:.3f} netSR {v['net_sharpe'] or float('nan'):+.2f}")
