"""Stricter Critic gate, multiple-testing helpers, staggered rebalancing and Fama-French parsing."""
import numpy as np
import pandas as pd
import pytest

from app.alpha.cost_aware import hold, staggered
from app.alpha.critic import strict_gate, year_share_positive
from app.alpha.ff_attribution import parse_french_csv
from app.alpha.library_tests import reality_check
from app.alpha.walkforward import holm


def test_strict_gate_requires_two_thirds_positive_years_and_min_dsr():
    assert strict_gate([0.02, 0.01, 0.03], 0.97)["pass"]
    assert not strict_gate([0.02, -0.01, -0.03], 0.99)["pass"]          # only 1/3 of years positive
    assert not strict_gate([0.02, 0.01, 0.03], 0.80)["pass"]            # deflated Sharpe too low
    assert not strict_gate([0.02, 0.01, 0.03], float("nan"))["pass"]
    assert year_share_positive([0.1, -0.1, np.nan, 0.2]) == pytest.approx(2 / 3)


def test_holm_is_monotone_and_bounded():
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == pytest.approx(0.06) and adj["b"] == pytest.approx(0.06)
    assert "d" not in adj and all(v <= 1 for v in adj.values())


def test_staggered_is_the_average_of_phase_shifted_portfolios():
    w = pd.DataFrame(np.random.default_rng(0).normal(size=(30, 4)))
    s = staggered(w, 5)
    assert np.allclose(s.values, sum(hold(w, 5, p).values for p in range(5)) / 5)
    assert np.allclose(staggered(w, 1).values, w.values)


def test_parse_french_csv_converts_percent_and_stops_at_footer():
    text = ("This file was created by CMPT_ME_BEME_OP_INV_RETS_DAILY\n\n"
            ",Mkt-RF,SMB,HML,RMW,CMA,RF\n"
            "20200102,  0.86, -0.97, -0.35,  0.00, -0.18,  0.006\n"
            "20200103, -0.67,  0.30,  0.00, -0.12,  0.01,  0.006\n\n"
            "Copyright 2024 Kenneth R. French\n")
    df = parse_french_csv(text)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"] and len(df) == 2
    assert df.loc["2020-01-02", "Mkt-RF"] == pytest.approx(0.0086)


def test_forward_returns_are_moved_to_the_day_they_are_realised():
    from app.alpha.ff_attribution import align_forward_returns
    fdates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    y = pd.Series([0.01, 0.02], index=pd.to_datetime(["2020-01-02", "2020-01-03"]))   # returns t -> t+1
    a = align_forward_returns(y, fdates)
    assert list(a.index) == list(fdates[1:]) and list(a.values) == [0.01, 0.02]


def test_reality_check_does_not_reject_pure_noise_but_rejects_real_edge():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.01, (750, 20))
    assert reality_check(noise)["p_value"] > 0.05
    edge = noise.copy()
    edge[:, 7] += 0.004
    rc = reality_check(edge)
    assert rc["p_value"] < 0.05 and rc["best_index"] == 7
