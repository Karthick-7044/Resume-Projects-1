"""Critic: deterministic, rule-based review of a backtested factor.

The Critic never sees the test period. It checks leakage, instability/overfitting, regime
dependence, concentration, transaction-cost sensitivity and economic plausibility, and returns
a verdict (ACCEPT / REVISE / REJECT) with reasons and concrete revision actions.
"""
from typing import Dict, List

import numpy as np

# Thresholds (kept in one place so they can be reported in the paper)
T = {
    "min_train_ic": 0.005, "min_valid_ic": 0.0, "min_valid_sharpe": 0.0,
    "suspicious_ic": 0.15, "suspicious_sharpe": 4.0,
    "decay_ratio": 0.30, "year_consistency": 0.60,
    "conc_warn": 0.35, "conc_fail": 0.50,
    "regime_min_days": 60, "turnover_warn": 60.0, "style_corr": 0.85,
    # stricter gate (fixed before any walk-forward test year was evaluated with it)
    "min_year_share": 2 / 3,   # rank IC must be positive in at least 2/3 of the prior years
    "min_dsr": 0.95,           # deflated Sharpe ratio of the prior-period gross long-short returns
    # v4 gates (fixed before the post-cutoff test window)
    "novelty_max_corr": 0.5,   # reject if |mean daily rank corr| with any known factor exceeds this (training data)
    "min_valid_net_sharpe": 0.0,  # cost-aware: validation Sharpe AFTER 10 bps must be positive
}


def year_share_positive(yearly_ic) -> float:
    """Share of years with positive mean rank IC (NaN years ignored)."""
    v = np.asarray([y for y in yearly_ic if y is not None and np.isfinite(y)], dtype=float)
    return float((v > 0).mean()) if len(v) else 0.0


def strict_gate(yearly_ic, dsr: float) -> Dict:
    """Stricter Critic rule shared by the discovery loop and the walk-forward evaluation.

    PASS requires (a) mean prior IC > 0, (b) positive IC in >= min_year_share of the prior years and
    (c) deflated Sharpe ratio >= min_dsr, where the DSR deflates by the number of formulas tried.
    """
    v = [y for y in yearly_ic if y is not None and np.isfinite(y)]
    share = year_share_positive(v)
    reasons = []
    if not v or np.mean(v) <= 0:
        reasons.append("mean prior IC <= 0")
    if share < T["min_year_share"]:
        reasons.append(f"IC positive in only {share:.0%} of prior years (< {T['min_year_share']:.0%})")
    if dsr is None or not np.isfinite(dsr) or dsr < T["min_dsr"]:
        reasons.append(f"deflated Sharpe {_nz(dsr, float('nan')):.2f} < {T['min_dsr']:.2f}")
    return {"pass": not reasons, "year_share": share, "dsr": dsr, "reasons": reasons}


def _nz(x, default=0.0):
    return default if x is None or (isinstance(x, float) and np.isnan(x)) else x


def review(metrics: Dict, attribution: Dict, validation: Dict, hypothesis: Dict) -> Dict:
    tr, va = metrics["train"], metrics["valid"]
    ic_tr, ic_va = _nz(tr["rank_ic"]["mean"]), _nz(va["rank_ic"]["mean"])
    sh_tr, sh_va = _nz(tr["sharpe"]), _nz(va["sharpe"])
    checks: List[Dict] = []
    actions: List[str] = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    # 1. Leakage
    if abs(ic_tr) > T["suspicious_ic"] or abs(sh_tr) > T["suspicious_sharpe"]:
        add("leakage", "FAIL", f"Suspiciously strong training result (rank IC {ic_tr:.3f}, Sharpe {sh_tr:.2f}); "
                               "inspect for look-ahead before trusting it")
    elif validation.get("warnings"):
        add("leakage", "WARN", "; ".join(validation["warnings"]))
    else:
        add("leakage", "PASS", "All features PIT-registered; no future references; performance within plausible range")

    # 2. Economic plausibility: formulas are oriented so the expected relation is positive
    if ic_tr <= 0:
        add("plausibility", "FAIL", f"Training rank IC {ic_tr:.4f} contradicts the hypothesis' expected positive relation")
    elif ic_tr < T["min_train_ic"]:
        add("plausibility", "WARN", f"Training rank IC {ic_tr:.4f} is economically negligible")
    else:
        add("plausibility", "PASS", f"Sign matches hypothesis (training rank IC {ic_tr:.4f}, t={_nz(tr['rank_ic']['t_stat']):.2f})")

    # 3. Instability / overfitting
    # sign consistency across ALL years seen so far (training + validation), relative to the training IC sign
    years = list(tr.get("ic_by_year", {}).values()) + list(va.get("ic_by_year", {}).values())
    consistency = float(np.mean([np.sign(y) == np.sign(ic_tr) for y in years])) if years and ic_tr != 0 else 0.0
    if ic_tr > 0 and ic_va <= T["min_valid_ic"]:
        add("stability", "FAIL", f"Rank IC changes sign out of sample (train {ic_tr:.4f}, validation {ic_va:.4f})")
    elif ic_tr > 0 and ic_va < T["decay_ratio"] * ic_tr:
        add("stability", "WARN", f"Validation IC {ic_va:.4f} is below {T['decay_ratio']:.0%} of training IC {ic_tr:.4f}")
        actions.append("smooth")
    elif consistency < T["year_consistency"]:
        add("stability", "WARN", f"IC sign is consistent in only {consistency:.0%} of training years")
        actions.append("smooth")
    else:
        add("stability", "PASS", f"Validation IC {ic_va:.4f} vs training {ic_tr:.4f}; sign consistent in {consistency:.0%} of years")

    # 3b. Stricter gate: positive IC in >= 2/3 of years and (when supplied) a minimum deflated Sharpe ratio
    share = year_share_positive(years)
    if years and share < T["min_year_share"]:
        add("year_consistency", "FAIL", f"Rank IC positive in only {share:.0%} of years (< {T['min_year_share']:.0%})")
    elif years:
        add("year_consistency", "PASS", f"Rank IC positive in {share:.0%} of years")
    dsr = tr.get("dsr")
    if dsr is not None and np.isfinite(dsr):
        if dsr < T["min_dsr"]:
            add("deflated_sharpe", "FAIL", f"Deflated Sharpe ratio {dsr:.2f} < {T['min_dsr']:.2f} after multiple-testing deflation")
        else:
            add("deflated_sharpe", "PASS", f"Deflated Sharpe ratio {dsr:.2f}")

    # 4. Regime dependence
    regs = {k: v for k, v in tr.get("by_regime", {}).items() if v["days"] >= T["regime_min_days"]}
    neg = [k for k, v in regs.items() if _nz(v["rank_ic"]) < 0]
    pos = [k for k, v in regs.items() if _nz(v["rank_ic"]) > 0]
    if regs and neg and pos:
        add("regime_dependence", "WARN", f"IC is positive in {pos} but negative in {neg}")
        if any("Bull" in p for p in pos) and not any("Bull" in n for n in neg):
            actions.append("gate_bull")
        elif any("High" in p for p in pos) and not any("High" in n for n in neg):
            actions.append("gate_high_vol")
        elif any("High" in n for n in neg):
            actions.append("gate_low_vol")
    elif regs:
        add("regime_dependence", "PASS", f"IC has the same sign across regimes {list(regs)}")
    else:
        add("regime_dependence", "PASS", "Insufficient regime history to test")

    # 5. Concentration
    conc = _nz(tr.get("max_ticker_pnl_share"))
    if conc > T["conc_fail"]:
        add("concentration", "FAIL", f"{conc:.0%} of absolute P&L comes from a single stock")
    elif conc > T["conc_warn"]:
        add("concentration", "WARN", f"{conc:.0%} of absolute P&L comes from a single stock")
    else:
        add("concentration", "PASS", f"Largest single-stock P&L share {conc:.0%}")

    # 6. Transaction costs
    cs = tr.get("cost_sensitivity", {})
    s0, s20 = _nz(cs.get("0")), _nz(cs.get("20"))
    turn = _nz(tr.get("annual_turnover"))
    if s0 > 0 and s20 <= 0:
        add("transaction_costs", "WARN", f"Sharpe falls from {s0:.2f} (0 bps) to {s20:.2f} (20 bps); annual turnover {turn:.0f}x")
        actions.append("smooth")
    elif turn > T["turnover_warn"]:
        add("transaction_costs", "WARN", f"High annual turnover {turn:.0f}x")
        actions.append("smooth")
    else:
        add("transaction_costs", "PASS", f"Sharpe {s0:.2f} at 0 bps, {s20:.2f} at 20 bps; turnover {turn:.0f}x")

    # 6b. Cost-aware gate: the validation Sharpe reported by the backtester is already net of transaction costs
    if va.get("sharpe") is not None and np.isfinite(_nz(va.get("sharpe"), np.nan)):
        if sh_va <= T["min_valid_net_sharpe"]:
            add("cost_gate", "FAIL", f"Validation Sharpe after costs {sh_va:.2f} <= {T['min_valid_net_sharpe']:.2f}")
        else:
            add("cost_gate", "PASS", f"Validation Sharpe after costs {sh_va:.2f}")

    # 6c. Novelty gate against the knowledge-base library and classic styles (computed by novelty.NoveltyReference)
    nov = attribution.get("novelty") or {}
    if nov.get("max_abs_corr") is not None:
        if nov["max_abs_corr"] > T["novelty_max_corr"]:
            add("novelty_gate", "FAIL", f"Rank correlation {nov.get('signed_corr', 0):+.2f} with known factor "
                                        f"'{nov.get('closest')}' exceeds {T['novelty_max_corr']:.2f}: not a new factor")
        else:
            add("novelty_gate", "PASS", f"Max |corr| with known factors {nov['max_abs_corr']:.2f} ({nov.get('closest')})")

    # 7. Novelty vs known styles
    expo = {k: v for k, v in attribution.get("style_exposure", {}).items() if v is not None}
    top = max(expo, key=lambda k: abs(expo[k])) if expo else None
    if top and abs(expo[top]) > T["style_corr"]:
        add("novelty", "WARN", f"Rank correlation {expo[top]:.2f} with the '{top}' style: little incremental information")
    else:
        add("novelty", "PASS", f"Highest style correlation: {top} ({expo.get(top, 0):.2f})" if top else "No style exposures")

    fails = [c for c in checks if c["status"] == "FAIL"]
    warns = [c for c in checks if c["status"] == "WARN"]
    good = ic_tr >= T["min_train_ic"] and ic_va > T["min_valid_ic"] and sh_va > T["min_valid_sharpe"]
    if fails:
        # A factor that works in-sample but fails out-of-sample for a fixable reason may be revised once
        fixable = ic_tr >= T["min_train_ic"] and all(c["check"] in ("stability",) for c in fails) and "gate" in " ".join(actions)
        verdict = "REVISE" if fixable else "REJECT"
    elif good and len(warns) <= 2:
        verdict = "ACCEPT"
    elif ic_tr >= T["min_train_ic"] and actions:
        verdict = "REVISE"
    elif good:
        verdict = "ACCEPT"
    else:
        verdict = "REJECT"

    # Complexity penalty: long expressions overfit (AlphaAgent-style control); the first 8 nodes are free
    nodes = int(validation.get("nodes") or 0)
    cplx = 0.02 * max(nodes - 8, 0)
    if nodes > 20:
        add("complexity", "WARN", f"{nodes}-node expression is likely over-engineered")
        warns = [c for c in checks if c["status"] == "WARN"]
    # Selection score uses validation only (training is where the search happened)
    score = float(ic_va * 100 + 0.25 * sh_va - 0.1 * len(warns) - cplx) if not fails else float(min(ic_va * 100, 0) - 1)
    summary = (f"{verdict}: '{hypothesis.get('title', '')}' - train IC {ic_tr:.4f} / Sharpe {sh_tr:.2f}, "
               f"validation IC {ic_va:.4f} / Sharpe {sh_va:.2f}; "
               + ("; ".join(f"{c['check']}: {c['detail']}" for c in fails + warns) or "all checks passed"))
    return {"verdict": verdict, "score": score, "checks": checks, "actions": list(dict.fromkeys(actions)),
            "summary": summary, "n_fail": len(fails), "n_warn": len(warns)}
