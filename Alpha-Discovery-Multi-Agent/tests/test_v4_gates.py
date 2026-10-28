"""v4 Critic gates (novelty, cost-aware) and the Cerebras provider."""
import numpy as np
import pandas as pd
import pytest

from app.alpha import critic, llm
from app.alpha.novelty import NoveltyReference


def metrics(ic_tr=0.02, ic_va=0.02, sh_va=0.8):
    per = lambda ic, sh: {"rank_ic": {"mean": ic, "t_stat": 3.0}, "sharpe": sh, "ic_by_year": {2014: ic, 2015: ic, 2016: ic},
                          "by_regime": {}, "max_ticker_pnl_share": 0.1, "cost_sensitivity": {"0": 1.0, "20": 0.5},
                          "annual_turnover": 10.0}
    return {"train": per(ic_tr, 1.0), "valid": per(ic_va, sh_va)}


def verdict(novelty=None, sh_va=0.8):
    att = {"style_exposure": {}, "novelty": novelty} if novelty else {"style_exposure": {}}
    return critic.review(metrics(sh_va=sh_va), att, {"warnings": [], "nodes": 5}, {"title": "t"})


def check(res, name):
    return next(c for c in res["checks"] if c["check"] == name)


def test_novelty_gate_rejects_a_disguised_known_factor_and_passes_a_new_one():
    bad = verdict({"max_abs_corr": 0.72, "signed_corr": 0.72, "closest": "momentum_12_1"})
    assert check(bad, "novelty_gate")["status"] == "FAIL" and bad["verdict"] == "REJECT"
    good = verdict({"max_abs_corr": 0.31, "signed_corr": -0.31, "closest": "low_volatility"})
    assert check(good, "novelty_gate")["status"] == "PASS" and good["verdict"] == "ACCEPT"


def test_cost_gate_rejects_negative_validation_sharpe_after_costs():
    res = verdict(sh_va=-0.2)
    assert check(res, "cost_gate")["status"] == "FAIL" and res["verdict"] == "REJECT"


def test_novelty_reference_finds_the_closest_known_factor():
    class Ev:                                         # minimal evaluator over a synthetic matrix (test only)
        def __init__(self, m):
            self.m = m
        def evaluate(self, expr):
            if expr == "known":
                return self.m
            raise KeyError(expr)
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=200)
    m = pd.DataFrame(rng.normal(size=(200, 30)), index=idx)
    ref = NoveltyReference(Ev(m), "2020-01-01", "2020-12-31", library=["known"], step=1)
    same = ref.check(m + rng.normal(scale=0.1, size=m.shape))
    other = ref.check(pd.DataFrame(rng.normal(size=(200, 30)), index=idx))
    assert same["closest"] == "known" and same["max_abs_corr"] > 0.9 and other["max_abs_corr"] < 0.2


def test_cerebras_client_uses_its_own_endpoint_and_never_leaks_the_key(monkeypatch):
    monkeypatch.setattr(llm.GroqClient, "MIN_INTERVAL", 0.0)
    class Resp:
        status_code, text, headers = 200, "", {}
        def json(self):
            return {"choices": [{"message": {"content": '{"ok": 1}'}}]}
    class Sess:
        def post(self, url, json=None, headers=None, timeout=None):
            assert url.startswith("https://api.cerebras.ai/") and headers["Authorization"] == "Bearer K" and "K" not in url
            return Resp()
    assert llm.extract_json(llm.CerebrasClient(api_key="K", model="m", session=Sess()).complete("s", "u")) == {"ok": 1}
