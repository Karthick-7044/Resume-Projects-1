"""Runs the multi-agent discovery loop under each ablation configuration.

Protocol
1. For every configuration the LangGraph loop tests up to `budget` formulas using only the
   feature domains that configuration allows. Agents and the Critic see train + validation only.
2. The best `top_k` factors are selected on VALIDATION (critic verdict ACCEPT, ranked by score).
   The no-critic configuration selects by training IC only (naive data mining baseline).
3. Selected factors, and their equal-weight z-score combination, are evaluated ONCE on the
   held-out test year. Test numbers are never fed back into memory or the agents.
"""
import argparse
import json
import logging
from datetime import datetime
from typing import Dict, List, Set

import numpy as np
import pandas as pd

from app.alpha import llm as llm_mod
from app.alpha.graph import DiscoveryLoop
from app.alpha.stats import deflated_sharpe
from app.alpha.memory import ResearchMemory, _clean
from app.config.settings import ALPHA_RESULTS_DIR, ALPHA_WINDOWS, DATASET_VERSION, UNIFIED_PANEL_DIR
from app.data.storage.duckdb_manager import DuckDBManager
from app.features.cross_sectional import CrossSectionalFeatureEngine

logger = logging.getLogger("AlphaDiscovery")

BASE = {"technical"}
CONFIGS: Dict[str, Dict] = {
    "A": {"label": "Technical only", "domains": BASE, "critic": True},
    "B": {"label": "A + fundamentals + valuation", "domains": BASE | {"fundamental", "valuation", "cross_sectional"}, "critic": True},
    "C": {"label": "B + news", "domains": BASE | {"fundamental", "valuation", "cross_sectional", "news"}, "critic": True},
    "D": {"label": "C + regime", "domains": BASE | {"fundamental", "valuation", "cross_sectional", "news", "regime"}, "critic": True},
    "Full": {"label": "All domains + macro, critic and memory",
             "domains": BASE | {"fundamental", "valuation", "cross_sectional", "news", "regime", "macro"}, "critic": True},
    "Full-NoCritic": {"label": "All domains, no critic (selection by training IC)",
                      "domains": BASE | {"fundamental", "valuation", "cross_sectional", "news", "regime", "macro"}, "critic": False},
}
KEYS = ["ann_return", "ann_vol", "sharpe", "gross_sharpe", "max_drawdown", "calmar", "annual_turnover",
        "hit_rate", "active_day_share", "max_ticker_pnl_share"]


def brief(m: Dict) -> Dict:
    out = {k: m.get(k) for k in KEYS}
    out["rank_ic"] = m["rank_ic"]["mean"]
    out["rank_ic_t"] = m["rank_ic"]["t_stat"]
    out["rank_ic_5d"] = m["rank_ic_5d"]["mean"]
    out["cost_sensitivity"] = m.get("cost_sensitivity")
    out["by_regime"] = m.get("by_regime")
    return out


def select(records: List[Dict], use_critic: bool, top_k: int) -> List[Dict]:
    valid = [r for r in records if r["is_valid"] and r["train_rank_ic"] is not None]
    if use_critic:
        pool = sorted([r for r in valid if r["verdict"] == "ACCEPT"], key=lambda r: -(r["score"] or -9))
    else:
        pool = sorted(valid, key=lambda r: -(r["train_rank_ic"] or -9))
    return pool[:top_k]


def run_all(budget: int = 30, top_k: int = 3, seed: int = 42, configs: List[str] = None, use_llm: bool = True,
            window: str = "recent", tag: str = "") -> Dict:
    llm_mod.set_run_seed(seed)                     # independent LLM samples per seed (seed enters prompt + cache key)
    panel = pd.read_parquet(UNIFIED_PANEL_DIR / "master_panel.parquet")
    labels = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    db = DuckDBManager()
    memory = ResearchMemory(db)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    results: Dict = {"generated_at": datetime.utcnow().isoformat(), "dataset_version": DATASET_VERSION,
                     "budget": budget, "top_k": top_k, "seed": seed, "window": window, "periods": ALPHA_WINDOWS[window], "configs": {}}
    curves = []

    for name in (configs or list(CONFIGS)):
        cfg = CONFIGS[name]
        loop = DiscoveryLoop(panel, labels, memory, seed=seed, use_llm=use_llm, window=window)
        run_id = f"alpha_{stamp}_{window}_{name}"
        logger.info(f"=== Config {name}: {cfg['label']} ===")
        recs = loop.run(run_id, name, set(cfg["domains"]), budget=budget, use_critic=cfg["critic"])
        chosen = select(recs, cfg["critic"], top_k)
        verdicts = pd.Series([r["verdict"] for r in recs]).value_counts().to_dict()

        selected = []
        for r in chosen:
            m = loop.backtester.run(loop.evaluator.evaluate(r["formula"]), periods=["train", "valid", "test"])
            valid_net = m["_series"]["net"][(m["_series"]["net"].index >= pd.Timestamp(ALPHA_WINDOWS[window]["valid"][0])) &
                                            (m["_series"]["net"].index <= pd.Timestamp(ALPHA_WINDOWS[window]["valid"][1]))]
            trials_sr = [(x["valid_sharpe"] or 0.0) / np.sqrt(252) for x in recs if x["is_valid"] and x["valid_sharpe"] is not None]
            dsr = deflated_sharpe(valid_net.dropna().values, n_trials=len(trials_sr), sr_trials=trials_sr)
            selected.append({"experiment_id": r["experiment_id"], "deflated_sharpe_validation": dsr, "title": r["hypothesis_title"], "formula": r["formula"],
                             "domains": r["domains"], "dominant_domain": r["dominant_domain"], "verdict": r["verdict"],
                             "critique": r["critique"], **{p: brief(m[p]) for p in ("train", "valid", "test")}})
        combined = None
        if chosen:
            expr = " + ".join(f"cs_zscore({r['formula']})" for r in chosen)
            f = loop.evaluator.evaluate(expr)
            m = loop.backtester.run(f, periods=["train", "valid", "test"])
            combined = {"formula": expr, **{p: brief(m[p]) for p in ("train", "valid", "test")}}
            eq = loop.backtester.equity_curve(f, ALPHA_WINDOWS[window]["valid"][0], ALPHA_WINDOWS[window]["test"][1])
            eq["config"] = name
            curves.append(eq)

        results["configs"][name] = {
            "label": cfg["label"], "domains": sorted(cfg["domains"]), "use_critic": cfg["critic"], "run_id": run_id,
            "n_tested": len(recs), "verdicts": verdicts, "n_selected": len(chosen),
            "selected": selected, "combined": combined,
            "experiments": [{k: r[k] for k in ["experiment_id", "iteration", "hypothesis_id", "hypothesis_title", "formula",
                                               "domains", "verdict", "score", "train_rank_ic", "train_sharpe",
                                               "valid_rank_ic", "valid_sharpe", "annual_turnover", "dominant_domain",
                                               "revision_action", "parent_id", "critique"]} for r in recs],
        }
        c = combined or {}
        logger.info(f"{name}: tested {len(recs)} {verdicts}; selected {len(chosen)}; combined test IC "
                    f"{(c.get('test') or {}).get('rank_ic')} Sharpe {(c.get('test') or {}).get('sharpe')}")

    results = _clean(results)
    (ALPHA_RESULTS_DIR / f"ablation_results_{window}_{'llm' if use_llm and llm_mod.llm_available() else 'offline'}{tag}.json").write_text(json.dumps(results, indent=2))
    if curves:
        all_curves = pd.concat(curves, ignore_index=True)
        all_curves.to_parquet(ALPHA_RESULTS_DIR / "combined_equity_curves.parquet")
        db.replace_table("alpha_equity_curves", all_curves)
    rows = [{"config": n, "label": c["label"], "n_tested": c["n_tested"], "n_selected": c["n_selected"],
             **{f"{p}_{k}": (c["combined"] or {}).get(p, {}).get(k) for p in ("train", "valid", "test")
                for k in ("rank_ic", "rank_ic_t", "sharpe", "ann_return", "max_drawdown", "annual_turnover")}}
            for n, c in results["configs"].items()]
    db.replace_table("alpha_ablation", pd.DataFrame(rows))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser(description="Run multi-agent alpha discovery and the ablation study")
    ap.add_argument("--budget", type=int, default=30)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--configs", nargs="*")
    ap.add_argument("--window", choices=list(ALPHA_WINDOWS), default="recent", help="evaluation window (never pooled)")
    ap.add_argument("--offline", action="store_true", help="do not call Claude even if a key is configured")
    ap.add_argument("--tag", default="", help="suffix for the results file (e.g. _seed1 for multi-seed runs)")
    a = ap.parse_args()
    res = run_all(a.budget, a.top_k, a.seed, a.configs, use_llm=not a.offline, window=a.window, tag=a.tag)
    for n, c in res["configs"].items():
        t = (c["combined"] or {}).get("test", {})
        print(f"{n:14s} tested={c['n_tested']:3d} selected={c['n_selected']} test rank IC={t.get('rank_ic')} Sharpe={t.get('sharpe')}")
