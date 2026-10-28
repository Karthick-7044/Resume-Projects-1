"""Deflated Sharpe ratio and formula-originality tests."""
import numpy as np
import pytest

from app.alpha.similarity import most_similar, signatures, similarity
from app.alpha.stats import deflated_sharpe, expected_max_sharpe, probabilistic_sharpe


def test_expected_max_sharpe_grows_with_the_number_of_trials():
    vals = [expected_max_sharpe(n, 0.0004) for n in (2, 10, 100, 1000)]
    assert vals == sorted(vals) and vals[0] > 0 and expected_max_sharpe(1, 0.0004) == 0.0


def test_single_trial_dsr_equals_probabilistic_sharpe_against_zero():
    rng = np.random.default_rng(1)
    r = rng.normal(0.0008, 0.01, 750)
    d = deflated_sharpe(r, n_trials=1, sr_trials=[r.mean() / r.std(ddof=1)])
    assert d["sr0_daily"] == 0.0 and d["dsr"] == pytest.approx(d["psr_vs_zero"])


def test_more_trials_lowers_the_deflated_sharpe():
    rng = np.random.default_rng(2)
    r = rng.normal(0.0006, 0.01, 750)
    sr = r.mean() / r.std(ddof=1)
    few = deflated_sharpe(r, 5, [sr * 0.2, sr * 0.6, sr * 0.1, 0.0, sr])["dsr"]
    many = deflated_sharpe(r, 500, list(np.random.default_rng(3).normal(0.0, 0.06, 500)))["dsr"]
    assert many < few


def test_best_of_many_noise_strategies_is_not_significant_after_deflation():
    rng = np.random.default_rng(7)
    trials = rng.normal(0.0, 0.01, (200, 500))                       # 200 strategies with ZERO true skill
    srs = trials.mean(1) / trials.std(1, ddof=1)
    best = trials[int(np.argmax(srs))]
    naive = probabilistic_sharpe(srs.max(), 0.0, 500)                # looks significant if you ignore the 200 trials
    deflated = deflated_sharpe(best, n_trials=200, sr_trials=list(srs))["dsr"]
    assert naive > 0.9 and deflated < 0.8


def test_dsr_handles_degenerate_series():
    assert np.isnan(deflated_sharpe([0.0] * 100, 10, [0.1, 0.2])["dsr"])
    assert np.isnan(deflated_sharpe([0.01, 0.02], 10, [0.1, 0.2])["dsr"])


def test_originality_similarity():
    a = "cs_rank(momentum_60d)"
    assert similarity(a, a) == 1.0
    assert similarity("cs_rank(roe) + cs_rank(volatility_60d)", "cs_rank(volatility_60d) + cs_rank(roe)") == 1.0     # commutative
    assert similarity("cs_rank(ts_mean(momentum_20d, 5))", "cs_rank(ts_mean(momentum_20d, 10))") == 1.0              # only the window differs
    assert similarity(a, "-cs_rank(volatility_60d)") < 0.3
    assert signatures("cs_rank(((") == frozenset()


def test_most_similar_picks_the_closest_formula():
    sim, other = most_similar("cs_rank(momentum_60d) + cs_rank(roe)", ["cs_rank(roe)", "-cs_rank(volatility_20d)", "cs_rank(momentum_60d)"])
    assert other in ("cs_rank(roe)", "cs_rank(momentum_60d)") and 0.3 < sim < 1.0
