"""v5 attribution: cheap-check gating in the loop and the fast month-end regression method."""
import numpy as np
import pandas as pd

from app.alpha import graph
from app.alpha.attribution import attribute_fast


def stub(mode, monkeypatch, calls):
    monkeypatch.setattr(graph, "ALPHA_ATTRIBUTION", mode)
    monkeypatch.setattr(graph, "attribute", lambda *a, **k: calls.append("loo") or {"style_exposure": {}, "domain_share": {}})
    lp = graph.DiscoveryLoop.__new__(graph.DiscoveryLoop)
    lp.win = {"train": ("2020-01-01", "2023-12-31"), "valid": ("2024-01-01", "2024-12-31")}
    lp.evaluator = lp.backtester = None
    lp.novelty = None
    return lp


def state(ic_tr, sh_va):
    return {"formula": "cs_rank(roe)", "metrics": {"train": {"rank_ic": {"mean": ic_tr}}, "valid": {"sharpe": sh_va}}}


def test_gated_mode_skips_attribution_for_formulas_failing_cheap_checks(monkeypatch):
    calls = []
    lp = stub("gated", monkeypatch, calls)
    assert lp.n_attribution(state(-0.01, 0.5))["attribution"]["method"] == "skipped_failed_cheap_checks"
    assert lp.n_attribution(state(0.02, -0.1))["attribution"]["method"] == "skipped_failed_cheap_checks"
    lp.n_attribution(state(0.02, 0.4))
    assert calls == ["loo"]                    # only the survivor is attributed, with the accurate leave-one-out method


def test_fast_attribution_shares_sum_to_one_and_find_the_driving_feature():
    class Ev:
        def __init__(self, mats):
            self.mats = mats
        def matrix(self, f):
            return self.mats[f]
        def evaluate(self, expr, overrides=None):
            return 3 * self.mats["roe"].rank(axis=1) + self.mats["momentum_60d"].rank(axis=1)
    class Bt:
        def daily_ic(self, factor):
            return pd.Series(0.01, index=factor.index)
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    mats = {f: pd.DataFrame(rng.normal(size=(len(idx), 40)), index=idx) for f in ("roe", "momentum_60d")}
    att = attribute_fast("cs_rank(roe) + cs_rank(momentum_60d)", Ev(mats), Bt(), "2020-01-01", "2021-12-31")
    shares = {f: v["share"] for f, v in att["by_feature"].items()}
    assert abs(sum(shares.values()) - 1) < 1e-9 and shares["roe"] > shares["momentum_60d"] and att["dates"] == 24
