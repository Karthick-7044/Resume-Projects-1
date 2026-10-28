"""LLM Research/Quant agent tests with a scripted fake LLM (no network, no key)."""
import json

import pandas as pd
import pytest

from app.alpha import llm, prompts
from app.alpha.agents import ContextBuilder, QuantAgent, ResearchAgent
from app.alpha.dsl import FactorEvaluator
from app.alpha.graph import DiscoveryLoop
from app.alpha.memory import ResearchMemory
from app.alpha.validator import validate_formula
from app.config.settings import ALPHA_WINDOWS, UNIFIED_PANEL_DIR
from app.features.cross_sectional import CrossSectionalFeatureEngine

PANEL_PATH = UNIFIED_PANEL_DIR / "master_panel.parquet"
needs_panel = pytest.mark.skipif(not PANEL_PATH.exists(), reason="master panel not built")


@pytest.fixture(autouse=True)
def isolated_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm, "CALL_LOG", tmp_path / "calls.jsonl")
    yield
    llm.reset_client()


@pytest.fixture(scope="module")
def panel():
    return pd.read_parquet(PANEL_PATH)


def scripted(research=None, quant=None, calls=None):
    """Fake LLM: answers by role, recording every (system, user)."""
    def fn(system, user):
        if calls is not None:
            calls.append((system, user))
        if "Research Agent" in system:
            return json.dumps({"hypotheses": research or []})
        return json.dumps({"formulas": quant(user) if callable(quant) else (quant or [])})
    return llm.CallableClient(fn)


H1 = {"title": "Sentiment-confirmed momentum", "rationale": "Momentum backed by good news persists",
      "literature_basis": "momentum, Jegadeesh & Titman 1993",
      "expected_sign": "positive", "domains": ["technical", "news"], "key_features": ["momentum_60d"], "condition": None}


def test_extract_json_handles_fences_prose_and_garbage():
    assert llm.extract_json('```json\n{"a": [1]}\n```') == {"a": [1]}
    assert llm.extract_json('Sure! {"formulas": ["x"]} Hope it helps') == {"formulas": ["x"]}
    assert llm.extract_json("no json here") is None and llm.extract_json("[1, 2]") is None


@needs_panel
def test_context_briefing_contains_what_the_llm_needs_and_hides_the_test_period(panel):
    ctx = ContextBuilder(panel, "fnspid").build({"technical", "news", "regime"}, {})
    win = ALPHA_WINDOWS["fnspid"]
    for anon in (True, False):                                                       # the test period is hidden either way
        text = prompts.render_context(ctx, anonymize=anon)
        assert win["test"][0] not in text and win["test"][1] not in text
        assert "momentum_60d" in text and "OPERATORS" in text and "RESEARCH PRIORS" in text
        assert "SPARSE" in text                                                      # thin news features are flagged
    assert win["train"][0] in prompts.render_context(ctx, anonymize=False)           # explicit dates only when asked for
    assert "fundamental" not in ctx["feature_vocabulary"]                            # only allowed domains are described
    assert all("rankable_days" in f for fs in ctx["feature_vocabulary"].values() for f in fs)


@needs_panel
def test_anonymised_briefing_withholds_tickers_and_calendar_dates(panel):
    import re
    ctx = ContextBuilder(panel, "fnspid").build({"technical", "news", "regime", "macro", "fundamental"}, {})
    text = prompts.render_context(ctx, anonymize=True)
    assert not any(re.search(rf"{t}", text) for t in ctx["universe"])          # no AAPL, NVDA, ...
    assert not re.search(r"(19|20)\d{2}-\d{2}-\d{2}", text) and not re.search(r"20[12]\d", text)   # no dates or years
    assert "names withheld" in text and "dates withheld" in text


def test_memory_is_rendered_so_the_llm_can_learn_from_failures():
    mem = {"n_tested": 3, "n_accepted": 1, "domains_tested": {"technical": 3},
           "accepted": [{"formula": "cs_rank(momentum_60d)", "verdict": "ACCEPT", "valid_rank_ic": 0.03, "critique": "ok"}],
           "recent_failures": [{"formula": "cs_rank(roe)", "verdict": "REJECT", "valid_rank_ic": -0.02, "critique": "IC flips sign"}]}
    text = prompts.render_memory(mem)
    assert "cs_rank(roe)" in text and "IC flips sign" in text and "technical=3" in text


@needs_panel
def test_research_agent_llm_mode_hybrid_and_fallback(panel, monkeypatch):
    ctx = ContextBuilder(panel, "fnspid").build({"technical", "news"}, {"tested_hypothesis_ids": [], "domains_tested": {}})
    llm.set_client(scripted(research=[H1, {**H1, "title": "Attention reversal"}]))
    monkeypatch.setattr(llm, "ALPHA_LLM_MODE", "hybrid")
    out = ResearchAgent(use_llm=True).propose(ctx, batch=4)
    srcs = [h["source"] for h in out]
    assert any(s.startswith("llm") for s in srcs) and "knowledge_base" in srcs      # hybrid mixes both
    assert all(h["templates"] == [] for h in out if h["source"].startswith("llm"))   # Research Agent gives ideas, not formulas
    monkeypatch.setattr(llm, "ALPHA_LLM_MODE", "llm")
    only = ResearchAgent(use_llm=True).propose(ctx, batch=2)
    assert all(h["source"].startswith("llm") for h in only)
    llm.set_client(llm.CallableClient(lambda s, u: "not json"))                       # LLM failure -> knowledge base
    fb = ResearchAgent(use_llm=True).propose(ctx, batch=2)
    assert fb and all(h["source"] == "knowledge_base" for h in fb)
    llm.set_client(None)                                                              # offline
    assert all(h["source"] == "knowledge_base" for h in ResearchAgent(use_llm=True).propose(ctx, batch=2))


@needs_panel
def test_quant_agent_repairs_formulas_using_validator_errors(panel):
    ev = FactorEvaluator(panel)
    seen = []

    def quant(user):
        if "REJECTED BY THE VALIDATOR" in user:
            seen.append(user)
            return ["cs_rank(momentum_60d) + cs_rank(roe)"]
        return ["cs_rank(made_up_feature)", "lag(momentum_5d, -3)"]                  # unknown feature + future reference

    llm.set_client(scripted(quant=quant))
    validate = lambda f: validate_formula(f, allowed_domains={"technical", "fundamental"}, evaluator=ev,
                                          train_start="2013-01-01", train_end="2019-12-31")
    res = QuantAgent().llm_formulate(dict(H1), {"allowed_domains": ["technical"], "universe": ["AAPL"], "train_period": ["a", "b"],
                                                "validation_period": ["c", "d"], "research_question": "q",
                                                "feature_vocabulary": {}, "operators": "ops", "memory": {}}, validate)
    assert res["valid"] == ["cs_rank(momentum_60d) + cs_rank(roe)"]
    assert len(res["rejected"]) == 2 and any("not in the feature registry" in e for _, e in res["rejected"])
    assert seen and "made_up_feature" in seen[0] and "FUTURE_REFERENCE" in seen[0]     # validator errors were shown to the LLM


@needs_panel
def test_llm_cannot_smuggle_labels_or_unsafe_code_past_the_validator(panel):
    ev = FactorEvaluator(panel)
    llm.set_client(scripted(quant=["cs_rank(fwd_ret_5d)", "__import__('os').system('x')", "cs_rank(momentum_60d)"]))
    validate = lambda f: validate_formula(f, allowed_domains={"technical"}, evaluator=ev, train_start="2013-01-01", train_end="2019-12-31")
    valid, rejected = llm.formulate(dict(H1), {"allowed_domains": ["technical"], "universe": [], "train_period": ["a", "b"],
                                              "validation_period": ["c", "d"], "research_question": "q",
                                              "feature_vocabulary": {}, "operators": "", "memory": {}}, validate, max_repairs=0)
    assert valid == ["cs_rank(momentum_60d)"] and len(rejected) == 2


def test_responses_are_cached_and_every_call_is_logged(tmp_path):
    calls = []
    llm.set_client(scripted(research=[H1], calls=calls))
    ctx = {"allowed_domains": ["technical"], "universe": ["AAPL"], "train_period": ["2013-01-01", "2019-12-31"],
           "validation_period": ["2020-01-01", "2021-12-31"], "research_question": "q", "feature_vocabulary": {},
           "operators": "", "memory": {}, "train_regime_distribution": {}}
    a = llm.research_hypotheses(ctx, 2)
    b = llm.research_hypotheses(ctx, 2)
    assert a == b and len(calls) == 1                                                 # second call replayed from the cache
    log = [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [x["cached"] for x in log] == [False, True] and "key" in log[0] and "api" not in json.dumps(log).lower()


def test_gemini_client_parses_response_and_never_logs_the_key():
    class Resp:
        status_code = 200
        text = ""
        def json(self): return {"candidates": [{"content": {"parts": [{"text": '{"formulas": ["a"]}'}]}}]}
    class Sess:
        def post(self, url, json=None, headers=None, timeout=None):
            assert headers["x-goog-api-key"] == "SECRET" and "SECRET" not in url
            assert json["generationConfig"]["responseMimeType"] == "application/json"
            return Resp()
    c = llm.GeminiClient(api_key="SECRET", model="gemini-test", session=Sess())
    assert llm.extract_json(c.complete("sys", "user")) == {"formulas": ["a"]}
    with pytest.raises(llm.LLMError):
        llm.GeminiClient(api_key=None, model="m").complete("s", "u")


@needs_panel
def test_full_loop_with_llm_agents_records_llm_provenance(panel):
    labels = CrossSectionalFeatureEngine.forward_returns(panel[["date", "ticker", "adj_close"]])
    llm.set_client(scripted(research=[H1], quant=["cs_rank(momentum_60d)", "cs_rank(momentum_60d) + cs_rank(volatility_60d)"]))
    mem = ResearchMemory(persist=False)
    loop = DiscoveryLoop(panel, labels, mem, use_llm=True, batch=1, window="fnspid", max_revisions=0)
    recs = loop.run("t_run", "A", {"technical"}, budget=2, use_critic=True)
    llm_recs = [r for r in recs if r["source"].startswith("llm")]
    assert llm_recs and llm_recs[0]["formula"] == "cs_rank(momentum_60d)" and llm_recs[0]["is_valid"]
    assert llm_recs[0]["verdict"] in ("ACCEPT", "REVISE", "REJECT")                   # went through backtest + critic


def test_output_rules_reject_identity_future_year_event_and_ungrounded_hypotheses():
    u = ["AAPL", "NVDA", "V"]
    ok = dict(H1)
    assert llm.leakage_violations(ok, u) == []                                         # a clean, literature-grounded idea
    assert any("ticker" in w for w in llm.leakage_violations({**ok, "rationale": "AAPL always rebounds"}, u))
    assert any("company" in w for w in llm.leakage_violations({**ok, "rationale": "Nvidia benefits from AI demand"}, u))
    assert any("calendar year" in w for w in llm.leakage_violations({**ok, "rationale": "worked well in 2022"}, u))
    assert any("2020 or later" in w for w in llm.leakage_violations({**ok, "literature_basis": "AI paper 2023"}, u))
    assert any("market event" in w for w in llm.leakage_violations({**ok, "title": "Post-pandemic reversal"}, u))
    assert any("literature_basis" in w for w in llm.leakage_violations({**ok, "literature_basis": ""}, u))


def test_research_agent_drops_rule_breaking_hypotheses_and_keeps_an_audit_trail():
    llm.REJECTED_HYPOTHESES.clear()
    bad = {**H1, "title": "Buy NVDA after the pandemic", "rationale": "x"}
    llm.set_client(scripted(research=[bad, H1]))
    ctx = {"allowed_domains": ["technical"], "universe": ["NVDA"], "train_period": ["2013-01-01", "2019-12-31"],
           "validation_period": ["2020-01-01", "2021-12-31"], "research_question": "q", "feature_vocabulary": {},
           "operators": "", "memory": {}, "train_regime_distribution": {}}
    out = llm.research_hypotheses(ctx, 2)
    assert [h["title"] for h in out] == [H1["title"]]
    assert llm.REJECTED_HYPOTHESES and "ticker" in " ".join(llm.REJECTED_HYPOTHESES[0]["reasons"])
