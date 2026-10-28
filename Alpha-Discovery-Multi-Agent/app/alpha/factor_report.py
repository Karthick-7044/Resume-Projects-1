"""Alpha Factor Report: one plain-language card per Critic-ACCEPTED LLM factor (+ their composite).

    python -m app.alpha.factor_report [--test-start 2025-01-01]

For every factor: hypothesis, data types, formula, what the portfolio buys/sells, test-window rank IC (HAC t) with a
Holm-corrected p over all reported factors, gross/net Sharpe, annual return, max drawdown, turnover (staggered monthly
long-short, 10 bps), FF5+Mom alpha, novelty vs known factors, attribution and Critic checks from discovery, refinement
history, a weekly equity curve (validation and test periods marked) and a one-line verdict. All definitions were fixed
before the test window was evaluated. Writes data/alpha/results/factor_report.json (served by /api/alpha/factor_report).
"""
import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.alpha import cost_aware as ca
from app.alpha.backtester import MIN_BREADTH, perf_stats
from app.alpha.dsl import FactorEvaluator, referenced_features
from app.alpha.ff_attribution import load_factors, regress
from app.alpha.library_tests import hac_t
from app.alpha.novelty import NoveltyReference
from app.alpha.walkforward import holm
from app.config.settings import ALPHA_EXPERIMENTS_DIR, ALPHA_RESULTS_DIR, ALPHA_TEST_END, ALPHA_WINDOWS, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine
from app.features.registry import feature_domain

DOMAIN_WORDS = {"technical": "price trends", "fundamental": "company accounts", "valuation": "valuation", "news": "news sentiment",
                "regime": "market mood", "macro": "interest rates / VIX", "cross_sectional": "relative rankings"}


def accepted_llm_factors() -> list:
    out, seen = [], set()
    for p in sorted(ALPHA_RESULTS_DIR.glob("ablation_results_*llm*.json")):
        res = json.load(open(p))
        for cfg in res["configs"].values():
            for e in cfg["experiments"]:
                ep = ALPHA_EXPERIMENTS_DIR / f"{e['experiment_id']}.json"
                if e["verdict"] != "ACCEPT" or not ep.exists() or e["formula"] in seen:
                    continue
                d = json.load(open(ep))
                if not str(d.get("source", "")).startswith("llm"):
                    continue
                seen.add(e["formula"])
                out.append({"file": p.name, "window": res.get("window"), "exp": d})
    return out


def history(exp: dict) -> list:
    """Refinement chain: parent experiments that led to this formula (oldest first)."""
    chain, cur = [], exp
    while cur.get("parent_id"):
        p = ALPHA_EXPERIMENTS_DIR / f"{cur['parent_id']}.json"
        if not p.exists():
            break
        cur = json.load(open(p))
        chain.append({"formula": cur["formula"], "verdict": cur["verdict"], "critique": (cur.get("critique") or "")[:300]})
    return list(reversed(chain))


def describe(formula: str, hyp: dict) -> str:
    doms = sorted({DOMAIN_WORDS.get(feature_domain(f), feature_domain(f)) for f in referenced_features(formula)})
    sign = "higher" if hyp.get("expected_sign", "positive") == "positive" else "lower"
    return (f"Each month it ranks all stocks by the formula (built from {', '.join(doms)}), buys the top-ranked stocks and "
            f"sells short the bottom-ranked ones with equal money on both sides. The idea expects {sign} formula values to be "
            f"followed by higher returns.")


def verdict(ic_p_holm, net_sharpe, net_p, ff_t) -> str:
    sig_rank = ic_p_holm is not None and ic_p_holm < 0.05
    profitable = net_sharpe is not None and net_sharpe > 0 and net_p is not None and net_p < 0.05
    if sig_rank and profitable and ff_t is not None and ff_t > 2:
        return "Significant ranking signal, profitable after costs and not explained by known factors."
    if sig_rank and profitable:
        return "Significant ranking signal and profitable after costs, but partly explained by known factors."
    if sig_rank:
        return "Significant ranking signal, not yet profitable after trading costs."
    if net_sharpe is not None and net_sharpe > 0:
        return "Positive but not statistically significant; treat as unconfirmed."
    return "Not significant on the test period."


def evaluate(ev, formula_or_sig, fwd, fac, days, test_start, novelty):
    sig = formula_or_sig if isinstance(formula_or_sig, pd.DataFrame) else ev.evaluate(formula_or_sig).reindex(index=days, columns=fwd.columns)
    live = sig.notna().sum(axis=1) >= MIN_BREADTH
    ic = sig.rank(axis=1).corrwith(fwd.rank(axis=1).where(sig.notna()), axis=1)[live]
    ls = ca.evaluate(ca.staggered(ca.rank_ls(sig), 21), fwd.fillna(0.0), live)
    test = ls["net"].index >= pd.Timestamp(test_start)
    net_t, gross_t = ls["net"][test], ls["gross"][test]
    ic_t = ic[ic.index >= pd.Timestamp(test_start)].dropna()
    st, sg = perf_stats(net_t), perf_stats(gross_t)
    t = hac_t(ic_t)
    eq = (1 + ls["net"].fillna(0)).cumprod()
    weekly = eq.resample("W-FRI").last().dropna()
    n = len(net_t)
    nt = float(net_t.mean() / net_t.std() * np.sqrt(n)) if n > 2 and net_t.std() > 0 else float("nan")
    out = {"rank_ic": float(ic_t.mean()), "rank_ic_t": t, "p_ic": float(1 - norm.cdf(t)) if np.isfinite(t) else None,
           "gross_sharpe": sg["sharpe"], "net_sharpe": st["sharpe"], "net_ann_return": st["ann_return"],
           "max_drawdown": st["max_drawdown"], "turnover": float(ls["stats"]["annual_turnover"]),
           "net_t": nt, "p_net": float(1 - norm.cdf(nt)) if np.isfinite(nt) else None,
           "ff": regress(net_t, fac),
           "equity": [{"date": str(d.date()), "equity": float(v)} for d, v in weekly.items()]}
    if novelty is not None and not isinstance(formula_or_sig, pd.DataFrame):
        out["novelty"] = novelty.check(ev.evaluate(formula_or_sig))
    return out


def run(test_start: str = "2025-01-01") -> dict:
    panel = pd.read_parquet(UNIFIED_PANEL_DIR / "master_panel.parquet")
    lab = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    lab["date"] = pd.to_datetime(lab["date"])
    fwd_all = lab.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index()
    win = ALPHA_WINDOWS["recent"]
    days = fwd_all.index[(fwd_all.index >= win["valid"][0]) & (fwd_all.index <= ALPHA_TEST_END)]   # validation + test
    fwd = fwd_all.loc[days]
    ev = FactorEvaluator(panel)
    fac = load_factors()
    novelty = NoveltyReference(ev, win["train"][0], win["train"][1])
    facs = accepted_llm_factors()
    cards = []
    for f in facs:
        d = f["exp"]
        det = d.get("detail") or {}
        hyp = det.get("hypothesis") or {}
        m = evaluate(ev, d["formula"], fwd, fac, days, test_start, novelty)
        att = det.get("attribution") or {}
        cards.append({
            "formula": d["formula"], "title": d.get("hypothesis_title"), "hypothesis": hyp.get("rationale") or d.get("rationale"),
            "literature": hyp.get("literature_basis"), "data_types": sorted({feature_domain(x) for x in referenced_features(d["formula"])}),
            "model": d.get("source"), "discovery_window": f["window"], "what_it_does": describe(d["formula"], hyp),
            "critic_checks": (det.get("critique") or {}).get("checks", []), "attribution": att.get("domain_share") or {},
            "attribution_features": {k: v.get("ic_contribution") for k, v in (att.get("by_feature") or {}).items()},
            "refinements": history(d), "validation": {"rank_ic": d.get("valid_rank_ic"), "net_sharpe": d.get("valid_sharpe")},
            "test": m,
        })
    # composite of all accepted LLM factors (equal-weight ranks), fixed before the test
    summary = {"n_accepted": len(cards), "test_window": [test_start, ALPHA_TEST_END], "validation_window": list(win["valid"]),
               "panel_end": str(fwd_all.index.max().date())}
    if cards:
        ranks = [ev.evaluate(c["formula"]).reindex(index=days, columns=fwd.columns).rank(axis=1, pct=True) for c in cards]
        comp = pd.concat(ranks).groupby(level=0).mean().reindex(days)
        summary["composite"] = evaluate(ev, comp, fwd, fac, days, test_start, None)
        summary["composite"]["novelty"] = novelty.check(comp)
    adj_ic = holm({c["formula"]: c["test"]["p_ic"] for c in cards})
    adj_net = holm({c["formula"]: c["test"]["p_net"] for c in cards})
    for c in cards:
        c["test"]["p_ic_holm"], c["test"]["p_net_holm"] = adj_ic.get(c["formula"]), adj_net.get(c["formula"])
        c["verdict"] = verdict(c["test"]["p_ic_holm"], c["test"]["net_sharpe"], c["test"]["p_net_holm"], c["test"]["ff"].get("alpha_t"))
    if "composite" in summary:
        cp = summary["composite"]
        summary["composite"]["verdict"] = verdict(cp["p_ic"], cp["net_sharpe"], cp["p_net"], cp["ff"].get("alpha_t"))
    out = {"summary": summary, "factors": cards}
    (ALPHA_RESULTS_DIR / "factor_report.json").write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-start", default="2025-01-01")
    a = ap.parse_args()
    r = run(a.test_start)
    s = r["summary"]
    print("accepted LLM factors:", s["n_accepted"], "test", s["test_window"], "panel end", s["panel_end"])
    for c in r["factors"]:
        t = c["test"]
        print(f"IC {t['rank_ic']:+.4f} t {t['rank_ic_t']:+.2f} pHolm {t['p_ic_holm']} | net SR {t['net_sharpe']:+.2f} | {c['verdict']} | {c['formula'][:70]}")
    if "composite" in s:
        cp = s["composite"]
        print(f"COMPOSITE IC {cp['rank_ic']:+.4f} t {cp['rank_ic_t']:+.2f} | gross {cp['gross_sharpe']:+.2f} net {cp['net_sharpe']:+.2f} | {cp['verdict']}")
