"""Rolling (walk-forward) out-of-sample evaluation of the discovered factor library.

    python -m app.alpha.walkforward [--first 2016 --last 2023 --top-k 3 --rebalance 5]

For every test year Y (expanding window, nothing from year Y or later is used for selection):
  * naive rule     : top-k formulas by mean rank IC over all years < Y                     (data-mining baseline)
  * critic_v1 rule : formulas whose mean IC over years < Y-1 is > 0 AND whose IC in year Y-1 is > 0 AND which were
                     positive in at least 2/3 of the earlier years; ranked by mean prior IC, top-k
  * critic rule    : the stricter Critic (critic.strict_gate): IC positive in >= 2/3 of ALL prior years, IC > 0 in
                     year Y-1, and deflated Sharpe ratio of the prior gross long-short returns >= 0.95 where the
                     deflation uses the whole library as the trial set; ranked by mean prior IC, top-k. If nothing
                     passes, the rule holds cash for year Y (zero return, no IC observation).
  * random rule    : k formulas drawn uniformly (seed 42, kept for continuity) plus a 200-draw null distribution
The selected factors are combined by averaging cross-sectional percentile ranks and evaluated on year Y only.
Pooled out-of-sample statistics over all test years are the headline numbers (more power than one 2-year window).
The library is every formula that the discovery loop tested (all configurations, valid formulas only), so the number of
formulas is reported as the multiple-testing count.
"""
import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.alpha.backtester import Backtester, ic_stats, perf_stats
from app.alpha.critic import strict_gate
from app.alpha.dsl import FactorEvaluator
from app.alpha.stats import deflated_sharpe
from app.config.settings import ALPHA_RESULTS_DIR, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine

logger = logging.getLogger("WalkForward")
N_RANDOM_DRAWS = 200
# Fixed literature composite (no selection on data): 12-1 momentum [3], short-term reversal, quality (ROE),
# value (earnings yield) and low volatility, equally weighted by cross-sectional rank.
LITERATURE = ["cs_rank(momentum_252_21d)", "-cs_rank(momentum_5d)", "cs_rank(roe)", "cs_rank(earnings_yield)",
              "-cs_rank(volatility_60d)"]


LIBRARIES = {
    "offline": ["ablation_results_fnspid_offline.json", "ablation_results_recent_offline.json"],   # knowledge base
    "llm": "ablation_results_fnspid_llm*.json",                                                   # LLM runs (data <= 2021)
    "llm_v4": "ablation_results_recent_llm_v4*.json",   # v4 LLM runs: novelty + cost gates, data <= 2024, test 2025+
    "llm_v5": "ablation_results_recent_llm_v5*.json",   # v5: v4 + two-step briefing, gated attribution, small repair model
}


def load_library(source: str = "offline") -> list:
    """Distinct valid formulas tested by the loop. source='offline' (knowledge base) or 'llm' (LLM runs; only formulas
    whose recorded source is an LLM, so knowledge-base fallbacks inside hybrid runs are excluded)."""
    files = LIBRARIES[source]
    paths = [ALPHA_RESULTS_DIR / f for f in files] if isinstance(files, list) else sorted(ALPHA_RESULTS_DIR.glob(files))
    forms = {}
    for p in paths:
        if not p.exists():
            continue
        if source == "llm":
            from app.config.settings import ALPHA_EXPERIMENTS_DIR
            for cfg in json.load(open(p))["configs"].values():
                for e in cfg["experiments"]:
                    ep = ALPHA_EXPERIMENTS_DIR / f"{e['experiment_id']}.json"
                    src = json.load(open(ep)).get("source", "") if ep.exists() else ""
                    if e["verdict"] != "INVALID" and e["train_rank_ic"] is not None and str(src).startswith("llm"):
                        forms.setdefault(e["formula"], e["domains"])
            continue
        for cfg in json.load(open(p))["configs"].values():
            for e in cfg["experiments"]:
                if e["verdict"] != "INVALID" and e["train_rank_ic"] is not None:
                    forms.setdefault(e["formula"], e["domains"])
    return [{"formula": k, "domains": v} for k, v in forms.items()]


def combine(evaluator: FactorEvaluator, formulas: list, skipna: bool = False) -> pd.DataFrame:
    """Rank average. skipna=False (top-k rules): a stock needs every selected formula; skipna=True (composites of
    many formulas): average over the formulas available for that stock, so sparse inputs do not empty the cross-section."""
    ranks = [evaluator.evaluate(f).rank(axis=1, pct=True) for f in formulas]
    if skipna:
        return pd.concat(ranks).groupby(level=0).mean()
    return sum(ranks) / len(ranks)


SKIPNA_RULES = {"composite", "literature"}


def monthly_t(ic: pd.Series) -> float:
    """t-statistic of monthly mean IC (monthly averaging reduces the autocorrelation of daily IC)."""
    m = ic.groupby([ic.index.year, ic.index.month]).mean()
    return float(m.mean() / m.std() * np.sqrt(len(m))) if len(m) > 2 and m.std() > 0 else float("nan")


def holm(pvals: dict) -> dict:
    """Holm-Bonferroni adjusted p-values (family = the keys of pvals)."""
    items = sorted((p, k) for k, p in pvals.items() if p is not None and np.isfinite(p))
    m, out, run_max = len(items), {}, 0.0
    for i, (p, k) in enumerate(items):
        run_max = max(run_max, min(1.0, (m - i) * p))
        out[k] = run_max
    return out


def run(first: int = 2016, last: int = 2023, top_k: int = 3, window: str = "fnspid", rebalance: int = 5, tag: str = "",
        panel_path: Path = None, library: str = "offline") -> dict:
    panel = pd.read_parquet(panel_path or UNIFIED_PANEL_DIR / "master_panel.parquet")
    labels = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    bt = Backtester(labels, window=window, rebalance_days=rebalance)
    ev = FactorEvaluator(panel)
    lib = load_library(library)
    logger.info(f"library ({library}): {len(lib)} distinct valid formulas; universe {panel['ticker'].nunique()} stocks")

    yearly_ic, gross, avail = {}, {}, {}
    for item in lib:
        fac = ev.evaluate(item["formula"])
        ok = fac.notna().sum(axis=1) >= 5
        avail[item["formula"]] = ok.groupby(ok.index.year).mean()   # data availability is known ex ante (provider coverage)
        s = bt.run(fac, periods=["train"])["_series"]
        ic = s["ic"].dropna()
        ic = ic[(ic.index >= "2013-01-01") & (ic.index <= f"{last}-12-31")]
        yearly_ic[item["formula"]] = ic.groupby(ic.index.year).mean()
        gross[item["formula"]] = s["gross"]
    Y = pd.DataFrame(yearly_ic)                                   # year x formula
    A = pd.DataFrame(avail)                                       # year x formula: share of days the formula is computable
    G = pd.DataFrame(gross)                                       # day x formula (gross long-short return)
    G = G[G.index >= "2013-01-01"]

    rules = ["naive", "critic_v1", "critic", "random", "composite", "literature"]
    out = {"library": library, "library_size": len(lib), "universe_size": int(panel["ticker"].nunique()), "rebalance_days": rebalance,
           "top_k": top_k, "folds": [], "rules": {}}
    pooled = {r: {"ic": [], "net": [], "gross": []} for r in rules}
    rng = np.random.default_rng(42)
    rand_pooled = [[] for _ in range(N_RANDOM_DRAWS)]
    rng_null = np.random.default_rng(2024)
    for yr in range(first, last + 1):
        lo, hi = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        prior = Y.loc[Y.index < yr]
        picks = {"naive": prior.mean().sort_values(ascending=False).head(top_k).index.tolist()}
        older, last_year = prior.loc[prior.index < yr - 1], prior.loc[yr - 1]
        ok = (older.mean() > 0) & (last_year > 0) & ((older > 0).mean() >= 2 / 3)
        picks["critic_v1"] = prior.mean()[ok].sort_values(ascending=False).head(top_k).index.tolist()

        # stricter Critic: DSR over the prior gross returns, deflated by the whole library
        gp = G[G.index < lo]
        sr_trials = (gp.mean() / gp.std(ddof=1)).replace([np.inf, -np.inf], np.nan).dropna().tolist()
        gate = {}
        for f in Y.columns:
            d = deflated_sharpe(gp[f].dropna().values, n_trials=len(lib), sr_trials=sr_trials)["dsr"]
            g = strict_gate(prior[f].tolist(), d)
            g["pass"] = g["pass"] and bool(last_year[f] > 0)
            gate[f] = g
        passed = [f for f, g in gate.items() if g["pass"]]
        picks["critic"] = prior.mean()[passed].sort_values(ascending=False).head(top_k).index.tolist()
        # random draws come from formulas that can be computed in year Y (e.g. no news features after 2023)
        pool = [f for f in Y.columns if A.get(f, pd.Series(dtype=float)).get(yr, 0.0) >= 0.5]
        # composite: EVERY computable formula passing the stability gate (mean prior IC > 0, positive in >= 2/3 of prior
        # years), equally weighted - diversification instead of picking the top few
        stable = (prior.mean() > 0) & ((prior > 0).mean() >= 2 / 3)
        picks["composite"] = [f for f in Y.columns if stable.get(f, False) and f in pool]
        picks["literature"] = LITERATURE
        picks["random"] = list(rng.choice(pool, size=top_k, replace=False))

        fold = {"year": yr, "critic_n_passed": len(passed),
                "critic_max_dsr": float(np.nanmax([g["dsr"] for g in gate.values()])) if gate else None}
        for rule, fs in picks.items():
            days = bt.fwd1.index[(bt.fwd1.index >= lo) & (bt.fwd1.index <= hi)]
            if not fs:  # cash
                fold[rule] = {"selected": [], "rank_ic": None, "sharpe": None}
                pooled[rule]["net"].append(pd.Series(0.0, index=days))
                pooled[rule]["gross"].append(pd.Series(0.0, index=days))
                continue
            r = bt.run(combine(ev, fs, skipna=rule in SKIPNA_RULES), periods=["train"])["_series"]
            ic = r["ic"][(r["ic"].index >= lo) & (r["ic"].index <= hi)].dropna()
            net = r["net"][(r["net"].index >= lo) & (r["net"].index <= hi)].dropna()
            gr = r["gross"][(r["gross"].index >= lo) & (r["gross"].index <= hi)].dropna()
            for k, v in (("ic", ic), ("net", net), ("gross", gr)):
                pooled[rule][k].append(v)
            fold[rule] = {"selected": fs, "rank_ic": float(ic.mean()), "sharpe": perf_stats(net)["sharpe"],
                          "gross_sharpe": perf_stats(gr)["sharpe"]}
        # null distribution of random selection (IC only)
        for j in range(N_RANDOM_DRAWS):
            fs = list(rng_null.choice(pool, size=top_k, replace=False))
            ic = bt.daily_ic(combine(ev, fs))
            rand_pooled[j].append(ic[(ic.index >= lo) & (ic.index <= hi)].dropna())
        out["folds"].append(fold)
        logger.info(f"{yr}: critic passed {len(passed)} | " + " ".join(
            f"{k}={'cash' if fold[k]['rank_ic'] is None else round(fold[k]['rank_ic'], 4)}" for k in picks))

    null_ic = np.array([pd.concat(x).mean() for x in rand_pooled])
    null_ic = null_ic[np.isfinite(null_ic)]
    out["random_null"] = {"draws": N_RANDOM_DRAWS, "mean": float(null_ic.mean()), "p95": float(np.quantile(null_ic, 0.95)),
                          "p99": float(np.quantile(null_ic, 0.99))}
    daily = {}
    for rule, d in pooled.items():
        if not d["ic"]:
            out["rules"][rule] = None
            continue
        ic, net, gr = pd.concat(d["ic"]), pd.concat(d["net"]).sort_index(), pd.concat(d["gross"]).sort_index()
        yearly = [f[rule]["rank_ic"] for f in out["folds"] if f[rule]["rank_ic"] is not None]
        mt = monthly_t(ic)
        out["rules"][rule] = {
            "test_years": len(out["folds"]), "invested_years": len(yearly), "pooled_daily": ic_stats(ic),
            "pooled_net": perf_stats(net), "pooled_gross": perf_stats(gr),
            "monthly_ic_t": mt, "monthly_ic_p": float(2 * (1 - norm.cdf(abs(mt)))) if np.isfinite(mt) else None,
            "random_null_pvalue": float((null_ic >= ic.mean()).mean()),
            "share_years_positive": float(np.mean([y > 0 for y in yearly])) if yearly else None, "yearly_ic": yearly,
        }
        daily[f"{rule}_ic"], daily[f"{rule}_net"], daily[f"{rule}_gross"] = ic, net, gr
    # DSR of each rule's pooled net returns, deflated over the selection rules that were compared
    nets = {r: daily[f"{r}_net"] for r in out["rules"] if out["rules"][r]}
    srs = [float(s.mean() / s.std(ddof=1)) for s in nets.values() if s.std(ddof=1) > 0]
    for r, s in nets.items():
        out["rules"][r]["dsr_net"] = deflated_sharpe(s.values, n_trials=len(nets), sr_trials=srs)
    adj = holm({r: v["monthly_ic_p"] for r, v in out["rules"].items() if v and r != "random"})
    for r, p in adj.items():
        out["rules"][r]["monthly_ic_p_holm"] = p
    ALPHA_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (ALPHA_RESULTS_DIR / f"walkforward_results{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    pd.DataFrame(daily).to_parquet(ALPHA_RESULTS_DIR / f"walkforward_daily{tag}.parquet")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=2016)
    ap.add_argument("--last", type=int, default=2023)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--rebalance", type=int, default=5)
    ap.add_argument("--panel", type=str, default=None)
    ap.add_argument("--tag", type=str, default=None)
    ap.add_argument("--library", choices=["offline", "llm", "llm_v4", "llm_v5"], default="offline")
    a = ap.parse_args()
    tag = a.tag if a.tag is not None else ("" if a.rebalance == 5 else f"_reb{a.rebalance}")
    res = run(a.first, a.last, a.top_k, rebalance=a.rebalance, tag=tag, panel_path=Path(a.panel) if a.panel else None,
              library=a.library)
    print("random null: mean IC", round(res["random_null"]["mean"], 4), "p95", round(res["random_null"]["p95"], 4))
    for rule, d in res["rules"].items():
        if d:
            print(rule, "IC", round(d["pooled_daily"]["mean"], 4), "t", round(d["pooled_daily"]["t_stat"], 2),
                  "monthly t", round(d["monthly_ic_t"], 2), "Holm p", d.get("monthly_ic_p_holm") and round(d["monthly_ic_p_holm"], 4),
                  "null p", d["random_null_pvalue"], "net Sharpe", round(d["pooled_net"]["sharpe"], 2),
                  "gross Sharpe", round(d["pooled_gross"]["sharpe"], 2), "years+", d["share_years_positive"],
                  "invested", d["invested_years"])
