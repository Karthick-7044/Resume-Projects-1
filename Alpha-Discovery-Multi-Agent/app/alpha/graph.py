"""LangGraph orchestration of the alpha-discovery loop.

context -> research -> quant -> validate -> backtest -> attribution -> critic -> memory -> route
   ^                     ^                                                              |
   |                     +------------------- REVISE / next formula --------------------+
   +------------------------------- queue empty, budget left ---------------------------+
"""
import logging
from typing import Any, Dict, List, Optional, Set, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from app.alpha import critic as critic_mod
from app.alpha import llm as llm_mod
from app.alpha.agents import ContextBuilder, QuantAgent, ResearchAgent
from app.alpha.attribution import attribute, attribute_fast
from app.alpha.backtester import Backtester
from app.alpha.dsl import FactorEvaluator
from app.alpha.memory import ResearchMemory
from app.alpha.similarity import most_similar
from app.alpha.tracing import tracing_config
from app.alpha.validator import validate_formula
from app.config.settings import ALPHA_ATTRIBUTION, ALPHA_NOVELTY_GATE, ALPHA_RESEARCH_BATCH, ALPHA_WINDOWS

logger = logging.getLogger(__name__)
ORIGINALITY_MAX_SIMILARITY = 0.80   # Jaccard overlap of sub-expression signatures at/above which a formula is a rewrite


def refinable(crit: Dict) -> bool:
    """REVISE and REJECT verdicts are sent back for refinement, except when leakage failed (nothing to repair)."""
    if crit.get("verdict") not in ("REVISE", "REJECT"):
        return False
    return not any(c["check"] == "leakage" and c["status"] == "FAIL" for c in crit.get("checks", []))


def refinement_actions(crit: Dict) -> List[str]:
    """The Critic's suggested actions, plus a smoothing action derived from failed/warned instability or cost checks.
    A sign flip after seeing a negative IC is deliberately NOT offered (that would be data snooping)."""
    acts = list(crit.get("actions", []))
    flagged = {c["check"] for c in crit.get("checks", []) if c["status"] in ("FAIL", "WARN")}
    if flagged & {"stability", "year_consistency", "transaction_costs", "deflated_sharpe"} and "smooth" not in acts:
        acts.append("smooth")
    return acts


class LoopState(TypedDict, total=False):
    run_id: str
    config: str
    allowed_domains: List[str]
    budget: int
    use_critic: bool
    iteration: int
    context: Dict
    queue: List[Dict]
    hypothesis: Optional[Dict]
    formula: Optional[str]
    parent_id: Optional[str]
    revision_action: Optional[str]
    revisions_left: int
    validation: Dict
    metrics: Optional[Dict]
    attribution: Optional[Dict]
    critique: Optional[Dict]
    exhausted: bool
    dry: int


MAX_DRY = 3


class DiscoveryLoop:
    def __init__(self, panel: pd.DataFrame, labels: pd.DataFrame, memory: ResearchMemory, seed: int = 42,
                 use_llm: bool = True, batch: int = ALPHA_RESEARCH_BATCH, max_revisions: int = 2, window: str = "recent"):
        self.window = window
        self.win = ALPHA_WINDOWS[window]
        self.evaluator = FactorEvaluator(panel)
        regimes = panel[["date", "market_regime"]].drop_duplicates("date")
        self.backtester = Backtester(labels, regimes, window=window)
        self.novelty = None
        if ALPHA_NOVELTY_GATE:                       # v4: compare every candidate with the known-factor reference set
            from app.alpha.novelty import NoveltyReference
            self.novelty = NoveltyReference(self.evaluator, self.win["train"][0], self.win["train"][1])
        self.memory = memory
        self.context_builder = ContextBuilder(panel, window)
        self.research = ResearchAgent(seed=seed, use_llm=use_llm)
        self.quant = QuantAgent()
        self.batch = batch
        self.max_revisions = max_revisions
        self.graph = self._build()

    # ------------------------------------------------------------------ nodes
    def n_context(self, s: LoopState) -> Dict:
        return {"context": self.context_builder.build(set(s["allowed_domains"]), self.memory.summary(s["run_id"]))}

    def n_research(self, s: LoopState) -> Dict:
        # a batch whose hypotheses yield no testable formula (all rejected by the leakage guard or the Quant Agent)
        # counts as dry; the round stops after MAX_DRY dry batches in a row instead of looping forever
        queue = self.research.propose(s["context"], self.batch)
        dry = s.get("dry", 0) + 1
        return {"queue": queue, "dry": dry, "exhausted": dry > MAX_DRY}

    def _validator(self, s: LoopState):
        """Callable used by the LLM Quant Agent to check each proposed formula (and learn from the errors)."""
        return lambda f: validate_formula(f, allowed_domains=set(s["allowed_domains"]), evaluator=self.evaluator,
                                          train_start=self.win["train"][0], train_end=self.win["train"][1])

    def _prepare(self, hyp: Dict, s: LoopState) -> None:
        """LLM-proposed hypotheses get their formulas from the LLM Quant Agent; rejected attempts go to memory."""
        if hyp.get("source", "").startswith("llm") and not hyp.get("llm_formulated"):
            res = self.quant.llm_formulate(hyp, s["context"], self._validator(s))
            for f, err in res["rejected"]:
                self.memory.record(s["run_id"], s["config"], s["iteration"], hyp, f,
                                   {"valid": False, "errors": [err], "domains": hyp.get("domains", [])},
                                   None, None, None, source=hyp["source"])

    def n_quant(self, s: LoopState) -> Dict:
        # A pending revision (set by the router) takes priority over a new hypothesis
        if s.get("formula") and s.get("revision_action"):
            return {}
        queue = list(s.get("queue", []))
        hyp = s.get("hypothesis")
        formula = self.quant.formulate(hyp, self.memory, s["run_id"]) if hyp else None
        while formula is None and queue:
            hyp = queue.pop(0)
            self._prepare(hyp, s)
            formula = self.quant.formulate(hyp, self.memory, s["run_id"])
        return {"queue": queue, "hypothesis": hyp if formula else None, "formula": formula,
                **({"dry": 0} if formula else {}),
                "parent_id": None, "revision_action": None,
                "revisions_left": self.max_revisions if formula else 0}

    def n_validate(self, s: LoopState) -> Dict:
        v = validate_formula(s["formula"], allowed_domains=set(s["allowed_domains"]), evaluator=self.evaluator,
                             train_start=self.win["train"][0], train_end=self.win["train"][1])
        d = v.to_dict()
        if v.valid:                                       # originality: reject trivial rewrites of formulas already tested
            sim, other = most_similar(s["formula"], [r["formula"] for r in self.memory.for_run(s["run_id"])])
            d["originality"] = round(1.0 - sim, 3)
            if sim >= ORIGINALITY_MAX_SIMILARITY:
                d["valid"] = False
                d["errors"] = list(d["errors"]) + [f"ORIGINALITY: structurally {sim:.0%} similar to an earlier formula ({other}); propose something different"]
        return {"validation": d, "metrics": None, "attribution": None, "critique": None}

    def n_backtest(self, s: LoopState) -> Dict:
        return {"metrics": self.backtester.run(self.evaluator.evaluate(s["formula"]), periods=["train", "valid"])}

    def n_attribution(self, s: LoopState) -> Dict:
        if ALPHA_ATTRIBUTION in ("fast", "gated"):
            tr, va = s["metrics"]["train"], s["metrics"]["valid"]
            ic_tr, sh_va = tr["rank_ic"]["mean"], va.get("sharpe")
            # cheap checks first: a formula that the Critic will reject anyway (wrong sign in training, or not profitable
            # after costs in validation) skips attribution and the novelty check
            if ic_tr is None or not ic_tr > 0 or sh_va is None or not sh_va > 0:
                return {"attribution": {"method": "skipped_failed_cheap_checks", "style_exposure": {}, "domain_share": {}}}
            # "gated" (v5 default): survivors get the accurate leave-one-out attribution; "fast": month-end regression
            # (measures what the factor is MADE OF, which agreed with leave-one-out on the dominant domain in only 4/7
            # test formulas - see compare_attribution.py - so it is not used to explain predictive power)
            fn = attribute_fast if ALPHA_ATTRIBUTION == "fast" else attribute
            att = fn(s["formula"], self.evaluator, self.backtester, self.win["train"][0], self.win["valid"][1])
            if self.novelty is not None:
                att["novelty"] = self.novelty.check(self.evaluator.evaluate(s["formula"]))
            return {"attribution": att}
        att = attribute(s["formula"], self.evaluator, self.backtester, self.win["train"][0], self.win["valid"][1])
        if self.novelty is not None:
            att["novelty"] = self.novelty.check(self.evaluator.evaluate(s["formula"]))
        return {"attribution": att}

    def n_critic(self, s: LoopState) -> Dict:
        if s.get("use_critic", True):
            return {"critique": critic_mod.review(s["metrics"], s["attribution"], s["validation"], s["hypothesis"])}
        tr = s["metrics"]["train"]["rank_ic"]["mean"]
        return {"critique": {"verdict": "UNREVIEWED", "score": float(tr or 0) * 100, "checks": [], "actions": [],
                             "summary": "Critic disabled: ranked by training IC only", "n_fail": 0, "n_warn": 0}}

    def n_memory(self, s: LoopState) -> Dict:
        rec = self.memory.record(s["run_id"], s["config"], s["iteration"], s["hypothesis"], s["formula"],
                                 s["validation"], s.get("metrics"), s.get("attribution"), s.get("critique"),
                                 parent_id=s.get("parent_id"), revision_action=s.get("revision_action"),
                                 source=s["hypothesis"].get("source", "knowledge_base"))
        out: Dict[str, Any] = {"iteration": s["iteration"] + 1, "formula": None, "revision_action": None, "parent_id": None}
        crit = s.get("critique") or {}
        if refinable(crit) and s.get("revisions_left", 0) > 0:
            # Critic feedback loop: the Critic's reasons (stored with this attempt in memory) go back to the Quant Agent,
            # which proposes a refined formula; the child attempt is linked to this one via parent_id.
            actions = refinement_actions(crit)
            rev = None
            if llm_mod.llm_mode() != "offline" and s["hypothesis"].get("source", "").startswith("llm"):
                rev = self.quant.llm_revise(s["formula"], crit.get("summary", ""), actions, s["hypothesis"],
                                            s["context"], self._validator(s), self.memory, s["run_id"])
            if rev is None:
                rev = self.quant.revise(s["formula"], actions, set(s["allowed_domains"]), self.memory, s["run_id"])
            if rev:
                out.update({"formula": rev["formula"], "revision_action": rev["action"],
                            "parent_id": rec["experiment_id"], "revisions_left": s["revisions_left"] - 1})
        return out

    # ------------------------------------------------------------------ routing
    @staticmethod
    def r_after_quant(s: LoopState) -> str:
        return "validate" if s.get("formula") else "context"

    @staticmethod
    def r_after_research(s: LoopState) -> str:
        return "end" if s.get("exhausted") else "quant"

    @staticmethod
    def r_after_validate(s: LoopState) -> str:
        return "backtest" if s["validation"]["valid"] else "memory"

    @staticmethod
    def r_after_memory(s: LoopState) -> str:
        return "end" if s["iteration"] >= s["budget"] else "quant"

    def _build(self):
        g = StateGraph(LoopState)
        for name, fn in [("context", self.n_context), ("research", self.n_research), ("quant", self.n_quant),
                         ("validate", self.n_validate), ("backtest", self.n_backtest),
                         ("attribution", self.n_attribution), ("critic", self.n_critic), ("memory", self.n_memory)]:
            g.add_node(name, fn)
        g.set_entry_point("context")
        g.add_edge("context", "research")
        g.add_conditional_edges("research", self.r_after_research, {"quant": "quant", "end": END})
        g.add_conditional_edges("quant", self.r_after_quant, {"validate": "validate", "context": "context"})
        g.add_conditional_edges("validate", self.r_after_validate, {"backtest": "backtest", "memory": "memory"})
        g.add_edge("backtest", "attribution")
        g.add_edge("attribution", "critic")
        g.add_edge("critic", "memory")
        g.add_conditional_edges("memory", self.r_after_memory, {"quant": "quant", "end": END})
        return g.compile()

    def run(self, run_id: str, config: str, allowed_domains: Set[str], budget: int = 30,
            use_critic: bool = True) -> List[Dict]:
        self.memory.clear_run(run_id)
        self.graph.invoke({"run_id": run_id, "config": config, "allowed_domains": sorted(allowed_domains),
                           "budget": budget, "use_critic": use_critic, "iteration": 0, "queue": [],
                           "hypothesis": None, "formula": None},
                          config={"recursion_limit": 50 * budget + 100, **tracing_config(run_id, config)})
        return self.memory.for_run(run_id)
