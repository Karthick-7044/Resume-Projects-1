"""Execution-realism and cost-reduction study on the post-cutoff window (signals fixed before looking at the test window).

    python -m app.alpha.execution_eval [--start 2025-01-01 --end 2026-10-23]

The signal is known at the close of day t. Variants differ only in how it is traded:
  close_close : buy at close t, hold to close t+1          (the framework's original, optimistic convention)
  next_open   : trade at the open of t+1, hold to the open of t+2   (realistic: the signal exists only after the close)
  next_open + monthly staggered / buffered weights                  (cost reduction)
Signals: the Critic-accepted LLM formulas (equal rank average) and an IC-weighted blend whose weights are estimated on
2020-2024 data only. Every variant is reported (no selection); p-values are one-sided and Holm-corrected over all variants.
"""
import argparse
import json

import numpy as np
import pandas as pd

from app.alpha import cost_aware as ca
from app.alpha.backtester import MIN_BREADTH
from app.alpha.dsl import FactorEvaluator
from app.alpha.post_cutoff_eval import composite, v4_formulas
from app.alpha.walkforward import holm
from app.config.settings import ALPHA_RESULTS_DIR, UNIFIED_PANEL_DIR


def returns_close_close(panel: pd.DataFrame) -> pd.DataFrame:
    px = panel.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    return px.shift(-1) / px - 1


def returns_next_open(panel: pd.DataFrame) -> pd.DataFrame:
    """Row t holds the return of a trade decided at close t: open(t+2)/open(t+1) - 1, split-adjusted."""
    adj_open = (panel["open"] * panel["adj_close"] / panel["close"]).rename("aopen")
    op = panel.assign(aopen=adj_open).pivot(index="date", columns="ticker", values="aopen").sort_index()
    return op.shift(-2) / op.shift(-1) - 1


def ic_weighted(ev, formulas, panel_index, columns, fwd, lo, hi):
    """Weights = positive mean rank IC of each formula on [lo, hi] (train+valid only)."""
    ws, ranks = [], []
    d = fwd.index[(fwd.index >= lo) & (fwd.index <= hi)]
    for f in formulas:
        s = ev.evaluate(f).reindex(index=panel_index, columns=columns)
        ranks.append(s.rank(axis=1, pct=True))
        sub, fw = s.loc[d], fwd.loc[d]
        ic = sub.rank(axis=1).corrwith(fw.rank(axis=1).where(sub.notna()), axis=1).mean()
        ws.append(max(float(ic), 0.0) if np.isfinite(ic) else 0.0)
    ws = np.array(ws)
    if ws.sum() == 0:
        return None, ws
    ws = ws / ws.sum()
    blend = sum(r.fillna(0.5) * w for r, w in zip(ranks, ws))
    return blend, ws


def variants(sig):
    return {
        "monthly_rank_ls": ca.staggered(ca.rank_ls(sig), 21),
        "buffered_ls": ca.buffer_ls(sig, 0.2, 0.4, every=5),
        "weekly_rank_ls": ca.staggered(ca.rank_ls(sig), 5),
    }


def run(start: str, end: str) -> dict:
    panel = pd.read_parquet(UNIFIED_PANEL_DIR / "master_panel.parquet")
    panel["date"] = pd.to_datetime(panel["date"])
    cc, no = returns_close_close(panel), returns_next_open(panel)
    days = cc.index[(cc.index >= start) & (cc.index <= end)]
    ev = FactorEvaluator(panel)
    formulas = v4_formulas(True)
    cols = cc.columns
    eq = composite(ev, formulas, days, cols)
    full_idx = cc.index
    blend, w = ic_weighted(ev, formulas, full_idx, cols, cc, pd.Timestamp("2020-01-01"), pd.Timestamp("2024-12-31"))
    sigs = {"equal_avg": eq}
    if blend is not None:
        sigs["ic_weighted"] = blend.reindex(days)
    out = {"test_window": [start, end], "n_formulas": len(formulas), "formulas": formulas,
           "blend_weights": [float(x) for x in w], "results": {}}
    ps = {}
    for sname, sig in sigs.items():
        live = sig.notna().sum(axis=1) >= MIN_BREADTH
        for vname, wts in variants(sig).items():
            for ename, fwd in (("close_close", cc), ("next_open", no)):
                r = ca.evaluate(wts, fwd.reindex(days).fillna(0.0), live)
                key = f"{sname}|{vname}|{ename}"
                out["results"][key] = {k: r["stats"][k] for k in
                                       ("gross_sharpe", "net_sharpe", "net_ann_return", "annual_turnover", "net_t", "net_p_one_sided")}
                ps[key] = r["stats"]["net_p_one_sided"]
    adj = holm({k: v for k, v in ps.items() if v is not None})
    for k, v in adj.items():
        out["results"][k]["holm_p"] = v
    (ALPHA_RESULTS_DIR / "execution_eval.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    from app.config.settings import ALPHA_TEST_END
    r = run(a.start, a.end or ALPHA_TEST_END)
    print("formulas", r["n_formulas"], "blend weights", [round(x, 2) for x in r["blend_weights"]])
    for k, v in r["results"].items():
        print(f"{k:42s} gross {v['gross_sharpe']:+.2f} net {v['net_sharpe']:+.2f} ret {v['net_ann_return']:+.3f} "
              f"turn {v['annual_turnover']:.1f} p {v['net_p_one_sided']:.2f} holm {v.get('holm_p', float('nan')):.2f}")
