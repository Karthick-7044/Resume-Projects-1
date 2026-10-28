"""Post-hoc robustness check of ONE formula flagged by the library tests (not a new trial; reported as post hoc).

    python -m app.alpha.single_factor_check "-cs_rank(accruals_ratio)" [--tag _u192]

Reports, net of 10 bps with staggered 21-day rebalancing: 2013-2023 and the untouched 2024-2025 hold-out, the split
between the original 36 stocks (where the library was discovered) and the stocks added later, and FF5+Mom alpha.
"""
import argparse
import json
from io import StringIO

import numpy as np
import pandas as pd

from app.alpha import cost_aware as ca
from app.alpha.backtester import MIN_BREADTH
from app.alpha.dsl import FactorEvaluator
from app.alpha.ff_attribution import load_factors, regress
from app.alpha.library_tests import hac_t
from app.config.settings import ALPHA_RESULTS_DIR, CONFIG_DIR, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine

SPANS = {"2013_2023": ("2013-01-01", "2023-12-31"), "2024_2025": ("2024-01-01", "2025-12-31")}


def run(formula: str, tag: str = "") -> dict:
    panel = pd.read_parquet(UNIFIED_PANEL_DIR / "master_panel.parquet")
    lab = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    lab["date"] = pd.to_datetime(lab["date"])
    fwd = lab.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index()
    sig = FactorEvaluator(panel).evaluate(formula).reindex(index=fwd.index, columns=fwd.columns)
    v2 = pd.read_csv(StringIO("\n".join(l for l in (CONFIG_DIR / "universe_v2_36.csv").read_text().splitlines()
                                        if not l.startswith("#"))))["ticker"].tolist()
    fac = load_factors()
    out = {"formula": formula, "note": "post hoc check of a formula flagged by library_tests; not a pre-specified trial", "spans": {}}
    for span, (lo, hi) in SPANS.items():
        m = (fwd.index >= lo) & (fwd.index <= hi)
        res = {}
        for name, cols in (("all", list(fwd.columns)), ("original_36", [c for c in fwd.columns if c in v2]),
                           ("added", [c for c in fwd.columns if c not in v2])):
            s, f = sig.loc[m, cols], fwd.loc[m, cols]
            live = s.notna().sum(axis=1) >= MIN_BREADTH
            r = ca.evaluate(ca.staggered(ca.rank_ls(s), 21), f.fillna(0.0), live)
            ic = s.rank(axis=1).corrwith(f.rank(axis=1).where(s.notna()), axis=1)[live]
            res[name] = {"n_stocks": len(cols), "mean_ic": float(ic.mean()), "ic_t_hac": hac_t(ic),
                         "net_sharpe": r["stats"]["net_sharpe"], "net_t": r["stats"]["net_t"],
                         "turnover": r["stats"]["annual_turnover"], "ff": regress(r["net"], fac) if name == "all" else None}
        out["spans"][span] = res
    (ALPHA_RESULTS_DIR / f"single_factor_check{tag}.json").write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("formula")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    r = run(a.formula, a.tag)
    for span, res in r["spans"].items():
        for k, v in res.items():
            ff = v["ff"] or {}
            print(f"{span} {k:12s} n={v['n_stocks']:3d} IC {v['mean_ic']:+.4f} (t {v['ic_t_hac']:+.2f}) net SR {v['net_sharpe']:+.2f} "
                  f"(t {v['net_t']:+.2f}) turnover {v['turnover']:.1f}x" + (f" | FF alpha {ff.get('alpha_ann', 0):+.4f} t {ff.get('alpha_t', 0):+.2f}" if ff else ""))
