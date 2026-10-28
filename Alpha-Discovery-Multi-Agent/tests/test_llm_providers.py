"""Groq provider, provider fallback and the multi-domain hypothesis rule (no network: fake HTTP sessions)."""
import pytest

from app.alpha import llm


class Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._p, self.text, self.headers = status, payload, text, {}

    def json(self):
        return self._p


class Sess:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        return self.responses.pop(0)


def test_groq_client_uses_bearer_auth_json_mode_and_never_puts_the_key_in_the_url(monkeypatch):
    monkeypatch.setattr(llm.GroqClient, "MIN_INTERVAL", 0.0)
    s = Sess([Resp(200, {"choices": [{"message": {"content": '{"formulas": ["cs_rank(roe)"]}'}}]})])
    c = llm.GroqClient(api_key="SECRET", model="llama-test", session=s)
    assert llm.extract_json(c.complete("sys", "user")) == {"formulas": ["cs_rank(roe)"]}
    url, body, headers = s.calls[0]
    assert headers["Authorization"] == "Bearer SECRET" and "SECRET" not in url
    assert body["response_format"] == {"type": "json_object"} and body["model"] == "llama-test"


def test_groq_errors_are_clear_and_do_not_leak_the_key(monkeypatch):
    monkeypatch.setattr(llm.GroqClient, "MIN_INTERVAL", 0.0)
    with pytest.raises(llm.LLMError, match="daily quota"):
        llm.GroqClient(api_key="SECRET", session=Sess([Resp(429, text="Rate limit reached: tokens per day (TPD)")])).complete("s", "u")
    with pytest.raises(llm.LLMError) as e:
        llm.GroqClient(api_key="SECRET", session=Sess([Resp(401, text="invalid")])).complete("s", "u")
    assert "SECRET" not in str(e.value)
    c = llm.GroqClient(api_key="x")
    c.api_key = None
    with pytest.raises(llm.LLMError, match="not set"):
        c.complete("s", "u")


def test_fallback_client_moves_to_the_next_provider_on_error():
    class Bad(llm.LLMClient):
        provider, model = "groq", "x"
        def complete(self, system, user, max_tokens=8000):
            raise llm.LLMError("quota")
    class Good(llm.LLMClient):
        provider, model = "gemini", "y"
        def complete(self, system, user, max_tokens=8000):
            return '{"ok": 1}'
    assert llm.FallbackClient([Bad(), Good()]).complete("s", "u") == '{"ok": 1}'
    with pytest.raises(llm.LLMError, match="all LLM providers failed"):
        llm.FallbackClient([Bad()]).complete("s", "u")


def test_fallback_skips_a_provider_whose_daily_quota_is_exhausted():
    calls = []
    class Quota(llm.LLMClient):
        provider, model = "groq", "big"
        def complete(self, system, user, max_tokens=8000):
            calls.append("big")
            raise llm.LLMError("Groq daily quota exhausted; rerun after the quota resets")
    class Small(llm.LLMClient):
        provider, model = "groq", "small"
        def complete(self, system, user, max_tokens=8000):
            calls.append("small")
            return "{}"
    fb = llm.FallbackClient([Quota(), Small()])
    fb.complete("s", "u")
    fb.complete("s", "u")
    assert calls == ["big", "small", "small"]          # the exhausted model is not retried on every call


def test_different_seeds_are_independent_llm_samples_but_same_seed_replays(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm, "CALL_LOG", tmp_path / "calls.jsonl")
    seen = []
    llm.set_client(llm.CallableClient(lambda s, u: (seen.append(u), '{"ok": 1}')[1]))
    try:
        for seed in (1, 1, 2):
            llm.set_run_seed(seed)
            llm.complete_json("sys", "same prompt", "research")
    finally:
        llm.set_run_seed(None)
        llm.reset_client()
    assert len(seen) == 2 and "#1" in seen[0] and "#2" in seen[1]          # seed 1 replayed from cache, seed 2 asked anew


def test_hypotheses_must_combine_two_domains_when_several_are_allowed():
    allowed = ["technical", "fundamental", "news"]
    assert llm.domain_violations({"domains": ["technical", "news"]}, allowed) == []
    assert llm.domain_violations({"domains": ["technical"]}, allowed)
    assert llm.domain_violations({"domains": ["technical", "macro"]}, allowed)        # macro not allowed here
    assert llm.domain_violations({"domains": ["technical"]}, ["technical"]) == []     # single-domain config is fine
