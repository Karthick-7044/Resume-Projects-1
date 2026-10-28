"""Critic feedback loop: REVISE/REJECT reasons go back to the Quant Agent for up to two refinements per hypothesis."""
from app.alpha import llm
from app.alpha.agents import QuantAgent
from app.alpha.graph import DiscoveryLoop, refinable, refinement_actions
from app.alpha.memory import ResearchMemory

HYP = {"id": "h1", "title": "Medium-term momentum", "domains": ["technical"], "source": "knowledge_base"}


def crit(verdict, checks, actions=()):
    return {"verdict": verdict, "checks": [{"check": c, "status": s, "detail": d} for c, s, d in checks],
            "actions": list(actions), "summary": f"{verdict}: " + "; ".join(d for _, _, d in checks), "score": 0.0}


def loop_stub(max_revisions=2):
    lp = DiscoveryLoop.__new__(DiscoveryLoop)       # no panel needed for the memory/routing node
    lp.memory, lp.quant, lp.max_revisions = ResearchMemory(persist=False), QuantAgent(), max_revisions
    return lp


def state(lp, formula, critique, revisions_left):
    return {"run_id": "r", "config": "A", "iteration": 0, "hypothesis": HYP, "formula": formula, "allowed_domains": ["technical"],
            "validation": {"valid": True, "errors": [], "domains": ["technical"]}, "metrics": None, "attribution": None,
            "critique": critique, "revisions_left": revisions_left, "context": {}}


def test_reject_and_revise_are_refinable_but_leakage_and_accept_are_not():
    assert refinable(crit("REVISE", [("stability", "WARN", "IC decays")]))
    assert refinable(crit("REJECT", [("stability", "FAIL", "IC changes sign out of sample")]))
    assert not refinable(crit("REJECT", [("leakage", "FAIL", "suspiciously strong")]))
    assert not refinable(crit("ACCEPT", []))


def test_refinement_actions_follow_the_critics_reasons_and_never_flip_the_sign():
    assert refinement_actions(crit("REJECT", [("year_consistency", "FAIL", "positive in 40% of years")])) == ["smooth"]
    assert refinement_actions(crit("REVISE", [("regime_dependence", "WARN", "x")], ["gate_bull"])) == ["gate_bull"]
    assert refinement_actions(crit("REJECT", [("plausibility", "FAIL", "negative IC")])) == []        # no sign flip


def test_failed_formula_is_refined_up_to_two_times_with_reasons_kept_in_memory():
    llm.set_client(None)
    lp = loop_stub()
    c = crit("REJECT", [("stability", "FAIL", "Rank IC changes sign out of sample")])
    out1 = lp.n_memory(state(lp, "cs_rank(momentum_60d)", c, 2))
    assert out1["formula"] == "ts_mean(cs_rank(momentum_60d), 5)" and out1["revisions_left"] == 1 and out1["parent_id"]
    parent = lp.memory.for_run("r")[0]
    assert parent["verdict"] == "REJECT" and "changes sign" in parent["critique"]                       # WHY is stored
    c2 = crit("REJECT", [("transaction_costs", "WARN", "Sharpe falls at 20 bps")], ["gate_bull"])
    out2 = lp.n_memory({**state(lp, out1["formula"], c2, out1["revisions_left"]), "parent_id": out1["parent_id"],
                        "revision_action": out1["revision_action"], "allowed_domains": ["technical", "regime"]})
    assert out2["formula"] and out2["revisions_left"] == 0
    out3 = lp.n_memory({**state(lp, out2["formula"], c2, out2["revisions_left"]), "allowed_domains": ["technical", "regime"]})
    assert out3["formula"] is None                                                                     # budget of 2 used
    recs = lp.memory.for_run("r")
    assert len(recs) == 3 and recs[1]["parent_id"] == recs[0]["experiment_id"]


def test_leakage_failures_are_not_sent_back():
    llm.set_client(None)
    lp = loop_stub()
    out = lp.n_memory(state(lp, "cs_rank(momentum_60d)", crit("REJECT", [("leakage", "FAIL", "too strong")], ["smooth"]), 2))
    assert out["formula"] is None
