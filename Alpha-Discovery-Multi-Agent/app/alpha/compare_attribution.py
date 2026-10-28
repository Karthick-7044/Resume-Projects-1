"""Compares the leave-one-out attribution (v1-v4) with the fast month-end regression attribution (v5).

    python -m app.alpha.compare_attribution

For a fixed set of multi-domain formulas: time per formula, the dominant domain under each method, and the rank
correlation of the per-feature shares. Writes data/alpha/results/attribution_comparison.json.
"""
import json
import time

import numpy as np
import pandas as pd

from app.alpha.attribution import attribute, attribute_fast
from app.alpha.backtester import Backtester
from app.alpha.dsl import FactorEvaluator
from app.config.settings import ALPHA_RESULTS_DIR, ALPHA_WINDOWS, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine

FORMULAS = [
    "if_else(regime_bull, cs_rank(roe) + cs_rank(momentum_60d), -cs_rank(volatility_60d))",
    "cs_rank(ocf_yield) + cs_rank(momentum_252_21d)",
    "regime_bull * (cs_rank(ocf_yield) + cs_rank(momentum_252_21d))",
    "-cs_rank(momentum_5d) * cs_rank(vix_chg_5d)",
    "cs_rank(revenue_growth) + cs_rank(earnings_yield)",
    "cs_rank(roe) * (1 - regime_high_vol) - cs_rank(debt_to_assets)",
    "cs_rank(ts_mean(sent_decay, 5)) + cs_rank(earnings_yield)",
]


def shares_loo(att):
    tot = sum(abs(v["ic_contribution"]) for v in att["by_feature"].values())
    return {f: abs(v["ic_contribution"]) / tot if tot > 0 else 0.0 for f, v in att["by_feature"].items()}


if __name__ == "__main__":
    panel = pd.read_parquet(UNIFIED_PANEL_DIR / "master_panel.parquet")
    labels = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    ev = FactorEvaluator(panel)
    win = ALPHA_WINDOWS["recent"]
    bt = Backtester(labels, panel[["date", "market_regime"]].drop_duplicates("date"), window="recent")
    rows = []
    for f in FORMULAS:
        t = time.time(); old = attribute(f, ev, bt, win["train"][0], win["valid"][1]); t_old = time.time() - t
        t = time.time(); new = attribute_fast(f, ev, bt, win["train"][0], win["valid"][1]); t_new = time.time() - t
        so, sn = shares_loo(old), {k: v["share"] for k, v in new["by_feature"].items()}
        common = [k for k in so if k in sn]
        rho = float(pd.Series([so[k] for k in common]).corr(pd.Series([sn[k] for k in common]), method="spearman")) if len(common) > 2 else None
        top_old = max(so, key=so.get) if so else None
        top_new = max(sn, key=sn.get) if sn else None
        rows.append({"formula": f, "sec_old": round(t_old, 2), "sec_new": round(t_new, 2), "dominant_domain_old": old["dominant_domain"],
                     "dominant_domain_new": new["dominant_domain"], "top_feature_old": top_old, "top_feature_new": top_new,
                     "share_rank_corr": rho, "shares_old": so, "shares_new": sn})
        print(f"{t_old:5.2f}s -> {t_new:5.2f}s | domain {old['dominant_domain']:>12s} vs {new['dominant_domain']:<12s} | "
              f"top feature {top_old} vs {top_new} | {f[:55]}")
    agree_dom = np.mean([r["dominant_domain_old"] == r["dominant_domain_new"] for r in rows])
    agree_top = np.mean([r["top_feature_old"] == r["top_feature_new"] for r in rows])
    out = {"n": len(rows), "mean_sec_old": float(np.mean([r["sec_old"] for r in rows])), "mean_sec_new": float(np.mean([r["sec_new"] for r in rows])),
           "dominant_domain_agreement": float(agree_dom), "top_feature_agreement": float(agree_top), "rows": rows}
    (ALPHA_RESULTS_DIR / "attribution_comparison.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"mean time {out['mean_sec_old']:.2f}s -> {out['mean_sec_new']:.2f}s; dominant domain agrees {agree_dom:.0%}; top feature agrees {agree_top:.0%}")
