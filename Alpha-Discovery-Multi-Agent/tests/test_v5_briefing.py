"""v5 two-step briefing: compact research menu, domain-filtered quant prompt, failure retrieval, small-model routing."""
from app.alpha import llm, prompts


def ctx():
    vocab = {
        "technical": [{"name": f"tech_{i}", "description": "technical feature", "train_coverage": 1.0} for i in range(20)],
        "fundamental": [{"name": "roe", "description": "return on equity", "train_coverage": 0.95},
                        {"name": "accruals_ratio", "description": "accruals", "train_coverage": 0.98}],
        "news": [{"name": "sent_decay", "description": "decayed sentiment", "train_coverage": 0.8}],
        "regime": [{"name": "regime_bull", "description": "bull indicator", "train_coverage": 1.0}],
    }
    mem = {"n_tested": 3, "n_accepted": 0, "accepted": [], "domains_tested": {"technical": 3},
           "recent_failures": [], "failure_pool": [
               {"title": "a", "formula": "cs_rank(tech_1)", "verdict": "REJECT", "critique": "decays"},
               {"title": "b", "formula": "cs_rank(roe) * regime_bull", "verdict": "REJECT", "critique": "negative IC"},
               {"title": "c", "formula": "cs_rank(sent_decay)", "verdict": "INVALID", "critique": "sparse"}]}
    return {"research_question": "q", "universe": ["X"] * 192, "train_period": ["2020-01-01", "2023-12-31"],
            "validation_period": ["2024-01-01", "2024-12-31"], "allowed_domains": list(vocab), "feature_vocabulary": vocab,
            "operators": "cs_rank(x), ts_mean(x, n)", "memory": mem, "train_regime_distribution": {"Bull": 0.7}}


def test_compact_research_prompt_is_a_short_menu(monkeypatch):
    c = ctx()
    monkeypatch.setattr(prompts, "ALPHA_LLM_BRIEFING", "full")
    full = prompts.research_user_prompt(c, 5)
    monkeypatch.setattr(prompts, "ALPHA_LLM_BRIEFING", "compact")
    compact = prompts.research_user_prompt(c, 5)
    assert len(compact) < len(full) and "tech_7" not in compact and "fundamental:" in compact and "propose 5" in compact


def test_compact_quant_prompt_lists_only_chosen_domains_and_relevant_failures(monkeypatch):
    monkeypatch.setattr(prompts, "ALPHA_LLM_BRIEFING", "compact")
    hyp = {"title": "quality in calm markets", "domains": ["fundamental", "regime"], "expected_sign": "positive"}
    p = prompts.quant_user_prompt(hyp, ctx())
    assert "roe" in p and "regime_bull" in p and "tech_3" not in p and "sent_decay" not in p.split("RELEVANT")[0]
    assert "cs_rank(roe) * regime_bull" in p and "cs_rank(tech_1)" not in p          # overlap retrieval


def test_repairs_use_the_small_model_and_ideas_use_the_large_one(monkeypatch):
    class Big(llm.LLMClient):
        provider, model = "groq", "big"
    monkeypatch.setattr(llm, "GROQ_MODEL_SMALL", "small-model")
    monkeypatch.setattr(llm, "GROQ_API_KEY", "k")
    monkeypatch.setattr(llm, "_SMALL_CLIENT", None)
    llm.set_client(llm.FallbackClient([Big()]))
    try:
        assert llm.client_for("research").clients[0].model == "big"
        small = llm.client_for("quant_repair")
        assert small.clients[0].model == "small-model" and small.clients[-1].model == "big"
    finally:
        llm.reset_client()
        monkeypatch.setattr(llm, "_SMALL_CLIENT", None)
