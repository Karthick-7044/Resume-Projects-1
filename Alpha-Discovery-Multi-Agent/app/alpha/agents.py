"""Agents of the Phase 2 research loop: Context Builder, Research Agent, Quant Agent."""
import random
from typing import Dict, List, Optional, Set

import pandas as pd

from app.alpha import llm, prompts
from app.alpha.dsl import grammar_description
from app.alpha.hypotheses import LIBRARY, expand_templates
from app.alpha.memory import ResearchMemory
from app.config.settings import ALPHA_LLM_STRICT, ALPHA_WINDOWS
from app.features.registry import FEATURES


class ContextBuilder:
    """Builds the controlled research context. The test period is never described to agents."""

    def __init__(self, panel: pd.DataFrame, window: str = "recent"):
        p = panel.copy()
        p["date"] = pd.to_datetime(p["date"])
        self.win = ALPHA_WINDOWS[window]
        self.train = p[(p["date"] >= self.win["train"][0]) & (p["date"] <= self.win["train"][1])]
        # share of training days on which >= 5 stocks have a value (the minimum needed to rank a factor)
        numeric = [f["feature_name"] for f in FEATURES if f["feature_name"] in self.train.columns]
        cnt = self.train.groupby("date")[numeric].count()
        self.rankable = (cnt >= 5).mean().to_dict()

    def build(self, allowed_domains: Set[str], memory_summary: Dict) -> Dict:
        vocab: Dict[str, List[Dict]] = {}
        for f in FEATURES:
            if not f["point_in_time_safe"] or f["category"] not in allowed_domains:
                continue
            name = f["feature_name"]
            cov = float(self.train[name].notna().mean()) if name in self.train.columns else 0.0
            if cov < 0.01:        # dead features (no data in the training window) are not shown to the LLM at all
                continue
            vocab.setdefault(f["category"], []).append(
                {"name": name, "description": f["description"], "train_coverage": round(cov, 3),
                 "rankable_days": round(float(self.rankable.get(name, 0.0)), 3)})
        regimes = (self.train.drop_duplicates("date")["market_regime"].value_counts(normalize=True).round(3).to_dict()
                   if "market_regime" in self.train.columns else {})
        return {
            "research_question": "Find cross-sectional factors whose higher values predict higher next-period returns.",
            "universe": sorted(self.train["ticker"].unique().tolist()),
            "train_period": list(self.win["train"]),
            "validation_period": list(self.win["valid"]),
            "allowed_domains": sorted(allowed_domains),
            "feature_vocabulary": vocab,
            "operators": grammar_description(),
            "train_regime_distribution": regimes,
            "memory": memory_summary,
            "priors": prompts.read_priors(),
        }


class ResearchAgent:
    """Proposes financially motivated hypotheses (proposals, not results)."""

    def __init__(self, seed: int = 42, use_llm: bool = True):
        self.rng = random.Random(seed)
        self.use_llm = use_llm

    def propose(self, context: Dict, batch: int = 4) -> List[Dict]:
        """LLM mode: all hypotheses from the LLM. Hybrid: half LLM, rest from the knowledge base. Offline: knowledge base."""
        allowed = set(context["allowed_domains"])
        tested = set(context["memory"].get("tested_hypothesis_ids", []))
        dom_tested = context["memory"].get("domains_tested", {})
        mode = llm.llm_mode() if self.use_llm else "offline"
        out: List[Dict] = []
        if mode in ("llm", "hybrid"):
            want = batch if mode == "llm" else max(1, batch // 2)
            out.extend(h for h in llm.research_hypotheses(context, n=want) if h["id"] not in tested)
        # LLM-only falls back to the knowledge base when the LLM produced nothing, unless ALPHA_LLM_STRICT=1
        # (then the round simply ends, so an LLM experiment never silently contains knowledge-base ideas)
        if mode != "llm" or (not out and not ALPHA_LLM_STRICT):
            pool = [h for h in LIBRARY if set(h["domains"]) <= allowed and h["id"] not in tested]
            self.rng.shuffle(pool)
            # Explore under-tested domains first; richer (multi-domain) ideas break ties
            pool.sort(key=lambda h: (min(dom_tested.get(d, 0) for d in h["domains"]), -len(h["domains"])))
            for h in pool[:max(0, batch - len(out))]:
                out.append({**h, "source": "knowledge_base"})
        return out


class QuantAgent:
    """Turns a hypothesis into an executable formula and applies critic-requested revisions."""

    REVISIONS = {
        "smooth": lambda f: f"ts_mean({f}, 5)",
        "gate_bull": lambda f: f"regime_bull * ({f})",
        "gate_high_vol": lambda f: f"regime_high_vol * ({f})",
        "gate_low_vol": lambda f: f"(1 - regime_high_vol) * ({f})",
    }

    def formulate(self, hypothesis: Dict, memory: ResearchMemory, run_id: str) -> Optional[str]:
        """First formula of the hypothesis that has not been tested in this run."""
        for f in expand_templates(hypothesis):
            if not memory.formula_seen(run_id, f):
                return f
        return None

    def alternatives(self, hypothesis: Dict, memory: ResearchMemory, run_id: str) -> List[str]:
        return [f for f in expand_templates(hypothesis) if not memory.formula_seen(run_id, f)]

    def llm_formulate(self, hypothesis: Dict, context: Dict, validate) -> Dict:
        """LLM Quant Agent for an LLM-proposed hypothesis: fills hypothesis['templates'] with VALID formulas."""
        valid, rejected = llm.formulate(hypothesis, context, validate)
        hypothesis["templates"] = valid
        hypothesis["llm_formulated"] = True
        return {"valid": valid, "rejected": rejected}

    def llm_revise(self, formula: str, critique: str, actions: List[str], hypothesis: Dict, context: Dict,
                   validate, memory: ResearchMemory, run_id: str) -> Optional[Dict]:
        new = llm.revise_formula(formula, critique, actions, hypothesis, context, validate)
        if new and not memory.formula_seen(run_id, new):
            return {"formula": new, "action": "llm_revision"}
        return None

    def revise(self, formula: str, actions: List[str], allowed_domains: Set[str],
               memory: ResearchMemory, run_id: str) -> Optional[Dict]:
        for a in actions:
            if a.startswith("gate") and "regime" not in allowed_domains:
                continue
            if a == "smooth" and formula.startswith("ts_mean("):
                continue
            new = self.REVISIONS[a](formula)
            if not memory.formula_seen(run_id, new):
                return {"formula": new, "action": a}
        return None
