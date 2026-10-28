"""Prompt construction for the LLM Research Agent and Quant Agent.

The LLM only knows what is placed in these prompts, so everything it needs is rendered here from the
controlled research context (see agents.ContextBuilder): the feature catalogue with real coverage figures,
the operator grammar, worked examples, memory of earlier experiments and the editable research priors.
The test period is never mentioned. Outputs are requested as strict JSON and are always re-validated by
deterministic code (validator -> backtester -> critic); the model can suggest, never approve.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from datetime import date

from app.config.settings import ALPHA_LLM_ANONYMIZE, ALPHA_LLM_BRIEFING, DATA_DIR

PRIORS_PATH = DATA_DIR / "config" / "research_priors.md"

FORMULA_EXAMPLES = [
    ("Medium-term momentum", "cs_rank(momentum_60d)"),
    ("Low volatility (negative sign: lower risk -> higher return)", "-cs_rank(volatility_60d)"),
    ("Quality at a reasonable price", "cs_rank(roe) + cs_rank(earnings_yield)"),
    ("Regime-conditional switch (market-wide flag combined with stock-level ranks)",
     "if_else(regime_bull, cs_rank(momentum_60d), -cs_rank(volatility_60d))"),
    ("Smoothed signal to cut turnover", "cs_rank(ts_mean(momentum_20d, 5))"),
]

RESEARCH_SYSTEM = """You are the Research Agent of a quantitative equity research team.
Your job: propose NEW, economically motivated hypotheses for cross-sectional alpha factors that rank stocks by expected
next-period return. You propose ideas only; you do not write formulas and you never judge whether an idea works.

Rules:
- Every hypothesis needs a concrete economic mechanism, an expected sign (higher factor value -> higher next-period
  return) and the feature domains it needs.
- Use only domains and features listed in the briefing. Never refer to future data, forward returns or the test period.
- Respect the data caveats (sparse features, small universe, market-wide features must be combined with stock-level ones).
- Be different from the ideas already tested (see memory). Prefer simple ideas; vary the domains you explore.
- When two or more domains are allowed, every hypothesis must COMBINE AT LEAST TWO DIFFERENT DOMAINS (e.g. technical +
  fundamental, fundamental + news, technical + regime, valuation + macro) and list them all in "domains"; explain how the
  domains interact in the mechanism. Single-domain ideas are rejected automatically.
- Learn from the recent failures in memory: do not re-propose a mechanism the Critic already rejected for the same reason.
- Every hypothesis must name its "literature_basis": the established, PUBLISHED mechanism or anomaly it builds on
  (e.g. "momentum, Jegadeesh & Titman 1993", "low-volatility anomaly", "accruals, Sloan 1996"). Anything you cannot ground
  in published research must not be proposed.
- Do NOT mention any company, ticker, calendar year after 2019, date or specific market event. Describe mechanisms only.
- Answer with ONE JSON object and nothing else:
{"hypotheses": [{"title": str, "rationale": str, "literature_basis": str, "expected_sign": "positive" | "negative",
 "domains": [str], "key_features": [str], "condition": str | null}]}"""

QUANT_SYSTEM = """You are the Quant Agent. You convert a research hypothesis into executable factor formulas.

A formula is a single expression over the feature catalogue using ONLY the listed operators. Higher output must mean a
higher expected next-period return (use a leading minus sign when the hypothesis says lower values are better).
All time-series operators look backward; windows and lags are integer constants between 1 and 252.
Rules:
- Use only features from the catalogue. No labels, no forward returns, no unknown names, no Python other than the operators.
- Market-wide features (regime_*, macro) have the same value for every stock on a date: combine them with stock-level
  features (if_else, multiplication). Never output a formula that ranks a market-wide feature alone.
- Keep formulas short (at most about 25 nodes) and interpretable. Offer up to 3 DISTINCT variants.
- Answer with ONE JSON object and nothing else: {"formulas": [str]}"""


# Post-2019 events an LLM could only know from its pre-training; hypotheses referring to them are rejected in code.
FORBIDDEN_EVENT_TERMS = ["covid", "coronavirus", "pandemic", "lockdown", "ukraine", "chatgpt", "silicon valley bank", "svb",
                         "ftx", "gamestop", "meme stock", "inflation surge", "rate hike cycle", "2008 crisis"]


def read_priors() -> str:
    return PRIORS_PATH.read_text(encoding="utf-8") if PRIORS_PATH.exists() else ""


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def render_catalogue(vocab: Dict[str, List[Dict]], sparse_below: float = 0.40) -> str:
    """Feature catalogue by domain with coverage; sparse features are flagged so the LLM does not waste ideas."""
    lines = []
    for domain, feats in sorted(vocab.items()):
        lines.append(f"[{domain}]")
        for f in feats:
            flag = ""
            if f["train_coverage"] < sparse_below or (f.get("rankable_days") is not None and f["rankable_days"] < 0.30):
                flag = "  <SPARSE: usually untestable alone>"
            rk = f" rankable-days {_pct(f.get('rankable_days'))}," if f.get("rankable_days") is not None else ""
            lines.append(f"  - {f['name']}: {f['description']} (coverage {_pct(f['train_coverage'])},{rk.rstrip(',')}){flag}")
    return "\n".join(lines)


def render_memory(mem: Dict, max_items: int = 5) -> str:
    if not mem or not mem.get("n_tested"):
        return "No experiments yet."
    out = [f"{mem['n_tested']} formulas tested so far, {mem['n_accepted']} accepted by the Critic."]
    if mem.get("domains_tested"):
        out.append("Tests per domain: " + ", ".join(f"{k}={v}" for k, v in sorted(mem["domains_tested"].items())))
    for title, key in (("Accepted so far", "accepted"), ("Recent failures (learn from the reasons)", "recent_failures")):
        items = mem.get(key, [])[:max_items]
        if items:
            out.append(title + ":")
            for it in items:
                ic = it.get("valid_rank_ic")
                out.append(f"  - {it['formula']}  [{it['verdict']}; validation IC {('%+.3f' % ic) if ic is not None else 'n/a'}] "
                           f"{(it.get('critique') or '')[:160]}")
    return "\n".join(out)


def _years(period) -> float:
    try:
        return max((date.fromisoformat(period[1]) - date.fromisoformat(period[0])).days / 365.25, 0.0)
    except (ValueError, TypeError):
        return 0.0


def render_context(context: Dict, anonymize: Optional[bool] = None) -> str:
    """Briefing text. With anonymize (default) tickers and calendar dates are withheld: the LLM needs the mechanism
    and the data quality facts, not the identities or dates it may remember from its pre-training."""
    anon = ALPHA_LLM_ANONYMIZE if anonymize is None else anonymize
    tr, va = context["train_period"], context["validation_period"]
    if anon:
        universe = f"{len(context['universe'])} large-cap US stocks (names withheld)"
        periods = (f"DATA YOU MAY LEARN FROM: a training sample of about {_years(tr):.0f} years and a validation sample of about "
                   f"{_years(va):.0f} years (calendar dates withheld). A later period exists but is hidden from you.")
    else:
        universe = f"{', '.join(context['universe'])} ({len(context['universe'])} stocks)"
        periods = (f"DATA YOU MAY LEARN FROM: training {tr[0]}..{tr[1]}, validation {va[0]}..{va[1]}. "
                   "A later period exists but is hidden from you.")
    parts = [
        f"RESEARCH QUESTION: {context['research_question']}",
        f"UNIVERSE: {universe}",
        periods,
        f"ALLOWED DOMAINS: {', '.join(context['allowed_domains'])}",
        "MARKET REGIME MIX IN TRAINING: " + (", ".join(f"{k} {v:.0%}" for k, v in context.get("train_regime_distribution", {}).items()) or "n/a"),
        "\nFEATURE CATALOGUE (name: meaning (coverage = share of training stock-days with a value; rankable-days = share of "
        "training days with >=5 stocks valued, the minimum needed to rank)):\n" + render_catalogue(context["feature_vocabulary"]),
        "\nOPERATORS:\n" + context["operators"],
        "\nMEMORY OF EARLIER EXPERIMENTS:\n" + render_memory(context.get("memory", {})),
    ]
    priors = context.get("priors") or ""
    if priors:
        parts.append("\nRESEARCH PRIORS AND DATA CAVEATS (from the research team):\n" + priors)
    return "\n".join(parts)


def research_user_prompt(context: Dict, n: int) -> str:
    if ALPHA_LLM_BRIEFING == "compact":
        return research_user_prompt_compact(context, n)
    return (render_context(context) + f"\n\nTASK: propose {n} new hypotheses. Cover domains that memory shows are under-tested, "
            "and do not repeat tested ideas. Return the JSON object only.")


# ---------------------------------------------------------------------- two-step (compact) briefing, v5
DOMAIN_LINES = {
    "technical": "price/volume history: momentum, reversal, volatility, RSI, moving averages, volume",
    "fundamental": "SEC accounts as first reported: revenue, earnings, cash flow, margins, ROE, growth, leverage, accruals",
    "valuation": "price relative to fundamentals: P/E, P/B, P/S, earnings/cash-flow/sales yields, market cap",
    "cross_sectional": "ready-made universe percentile ranks of key features (sector-relative P/E)",
    "news": "FinBERT news sentiment: mean/decayed sentiment, surprise, dispersion, momentum, news volume",
    "regime": "market mood from a walk-forward HMM: bull, bear, high-volatility indicators and probabilities (market-wide)",
    "macro": "interest rates, yield curve, VIX, fed funds and their recent changes (market-wide)",
}


def _median(xs) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def render_menu(context: Dict) -> str:
    """Step 1 (Research agent): one line per allowed data type with feature count and median coverage."""
    vocab = context["feature_vocabulary"]
    lines = []
    for d in context["allowed_domains"]:
        feats = vocab.get(d, [])
        cov = _median([f.get("train_coverage") for f in feats])
        lines.append(f"  - {d}: {DOMAIN_LINES.get(d, '')} ({len(feats)} features, median coverage {_pct(cov)})")
    return "\n".join(lines)


def render_memory_short(mem: Dict) -> str:
    if not mem or not mem.get("n_tested"):
        return "No experiments yet."
    out = [f"{mem['n_tested']} formulas tested, {mem['n_accepted']} accepted."]
    if mem.get("domains_tested"):
        out.append("Tests per data type: " + ", ".join(f"{k}={v}" for k, v in sorted(mem["domains_tested"].items())))
    if mem.get("accepted"):
        out.append("Accepted ideas: " + "; ".join(a["title"] for a in mem["accepted"][:5]))
    fails = mem.get("recent_failures", [])[:5]
    if fails:
        out.append("Recently rejected (reason): " + "; ".join(f"{f['title']} ({(f.get('critique') or '').split(';')[0][-90:]})" for f in fails))
    return "\n".join(out)


def research_user_prompt_compact(context: Dict, n: int) -> str:
    tr, va = context["train_period"], context["validation_period"]
    return "\n".join([
        f"RESEARCH QUESTION: {context['research_question']}",
        f"UNIVERSE: {len(context['universe'])} large-cap US stocks (names withheld). Training sample about {_years(tr):.0f} years, "
        f"validation about {_years(va):.0f} years (dates withheld); a later period is hidden.",
        "MARKET REGIME MIX IN TRAINING: " + (", ".join(f"{k} {v:.0%}" for k, v in context.get("train_regime_distribution", {}).items()) or "n/a"),
        "\nDATA TYPES YOU CAN COMBINE (pick 2-3 per idea; exact features are given to the Quant agent later):\n" + render_menu(context),
        "\nMEMORY:\n" + render_memory_short(context.get("memory", {})),
        f"\nTASK: propose {n} new hypotheses, each combining 2-3 data types (list them in \"domains\"). Avoid mechanisms "
        "already rejected for the same reason. Return the JSON object only."])


def relevant_failures(context: Dict, domains: List[str], k: int = 5) -> List[Dict]:
    """Past failures sharing the most features/data types with the chosen domains (simple overlap retrieval)."""
    vocab = context["feature_vocabulary"]
    names = {f["name"] for d in domains for f in vocab.get(d, [])}
    pool = (context.get("memory") or {}).get("failure_pool") or (context.get("memory") or {}).get("recent_failures", [])
    scored = [(sum(1 for n in names if n in (f.get("formula") or "")), i, f) for i, f in enumerate(pool)]
    return [f for s, i, f in sorted(scored, key=lambda x: (-x[0], -x[1])) if s > 0][:k]


def render_domain_features(context: Dict, domains: List[str]) -> str:
    vocab = context["feature_vocabulary"]
    chosen = [d for d in domains if d in vocab] or list(vocab)
    return render_catalogue({d: vocab[d] for d in chosen})


def _compact_quant_context(hypothesis: Dict, context: Dict) -> List[str]:
    doms = [d for d in (hypothesis.get("domains") or []) if d in context["allowed_domains"]] or context["allowed_domains"]
    fails = relevant_failures(context, doms)
    p = [f"FEATURES OF THE CHOSEN DATA TYPES ({', '.join(doms)}):\n" + render_domain_features(context, doms),
         "\nOPERATORS:\n" + context["operators"],
         "\nWORKED EXAMPLES:\n" + "\n".join(f"  - {d}: {f}" for d, f in FORMULA_EXAMPLES)]
    if fails:
        p.append("\nRELEVANT PAST FAILURES (do not repeat them):\n" + "\n".join(
            f"  - {f['formula']}  [{f['verdict']}] {(f.get('critique') or '')[:150]}" for f in fails))
    return p


def quant_user_prompt(hypothesis: Dict, context: Dict, errors: Optional[List[str]] = None, previous: Optional[List[str]] = None) -> str:
    if ALPHA_LLM_BRIEFING == "compact":
        p = _compact_quant_context(hypothesis, context)
        p.append("\nHYPOTHESIS TO IMPLEMENT:\n" + json.dumps({k: hypothesis.get(k) for k in
                                                           ("title", "rationale", "expected_sign", "domains", "key_features", "condition")}))
        if previous and errors:
            p.append("\nYOUR PREVIOUS ATTEMPT WAS REJECTED BY THE VALIDATOR:\n" + "\n".join(f"  {f}  ->  {e}" for f, e in zip(previous, errors))
                     + "\nFix the problems and answer again.")
        p.append("\nTASK: write up to 3 distinct formulas implementing this hypothesis. Return the JSON object only.")
        return "\n".join(p)
    ex = "\n".join(f"  - {d}: {f}" for d, f in FORMULA_EXAMPLES)
    p = [render_context({**context, "memory": context.get("memory", {})}),
         "\nWORKED EXAMPLES:\n" + ex,
         "\nHYPOTHESIS TO IMPLEMENT:\n" + json.dumps({k: hypothesis.get(k) for k in
                                                       ("title", "rationale", "literature_basis", "expected_sign", "domains", "key_features", "condition")}, indent=1)]
    if previous and errors:
        p.append("\nYOUR PREVIOUS ATTEMPT WAS REJECTED BY THE VALIDATOR:\n" + "\n".join(f"  {f}  ->  {e}" for f, e in zip(previous, errors))
                 + "\nFix the problems and answer again.")
    p.append("\nTASK: write up to 3 distinct formulas implementing this hypothesis. Return the JSON object only.")
    return "\n".join(p)


def revise_user_prompt(formula: str, critique: str, actions: List[str], hypothesis: Dict, context: Dict) -> str:
    if ALPHA_LLM_BRIEFING == "compact":
        return "\n".join(_compact_quant_context(hypothesis, context) + [
            "\nHYPOTHESIS:\n" + json.dumps({k: hypothesis.get(k) for k in ("title", "rationale", "expected_sign")}),
            f"\nFORMULA UNDER REVIEW: {formula}\nCRITIC FEEDBACK: {critique}\nSUGGESTED ACTIONS: {', '.join(actions) or 'none'}",
            "TASK: propose ONE revised formula that addresses the Critic's concerns while staying faithful to the hypothesis. "
            "Return {\"formulas\": [one formula]} only."])
    return (render_context(context) + "\n\nHYPOTHESIS:\n" + json.dumps({k: hypothesis.get(k) for k in ("title", "rationale", "expected_sign")})
            + f"\n\nFORMULA UNDER REVIEW: {formula}\nCRITIC FEEDBACK: {critique}\nSUGGESTED ACTIONS: {', '.join(actions) or 'none'}\n"
            "TASK: propose ONE revised formula that addresses the Critic's concerns while staying faithful to the hypothesis "
            "(for example smoothing to reduce turnover, or conditioning on a regime). Return {\"formulas\": [one formula]} only.")
