"""Multiple-testing statistics for factor selection (Bailey & Lopez de Prado, deflated Sharpe ratio).

Testing many formulas and keeping the best inflates the observed Sharpe ratio. The deflated Sharpe ratio (DSR)
is the probability that the true Sharpe ratio is positive AFTER accounting for (a) the number of trials N, (b) the
spread of Sharpe ratios across those trials, and (c) the non-normality (skew, kurtosis) and length T of the return
series. All Sharpe ratios here are PER-PERIOD (daily), not annualised.

    PSR(SR*) = Phi( (SR - SR*) * sqrt(T - 1) / sqrt(1 - skew*SR + (kurt - 1)/4 * SR^2) )
    SR0      = sqrt(Var[SR_trials]) * ((1 - g) * Phi^-1(1 - 1/N) + g * Phi^-1(1 - 1/(N e)))     (g = Euler-Mascheroni)
    DSR      = PSR(SR0)
"""
import math
from typing import Dict, Sequence

import numpy as np
from scipy.stats import kurtosis, norm, skew

EULER_GAMMA = 0.5772156649015329


def probabilistic_sharpe(sr: float, sr_benchmark: float, n_obs: int, skewness: float = 0.0, kurt: float = 3.0) -> float:
    """P(true SR > sr_benchmark) given the observed per-period SR (kurt = raw kurtosis, 3 for a normal)."""
    if n_obs < 3 or not np.isfinite(sr):
        return float("nan")
    denom = 1.0 - skewness * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        return float("nan")
    return float(norm.cdf((sr - sr_benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom)))


def expected_max_sharpe(n_trials: int, var_sr_trials: float) -> float:
    """Expected maximum per-period Sharpe among n_trials independent trials with zero true skill."""
    if n_trials <= 1 or var_sr_trials <= 0:
        return 0.0
    return float(math.sqrt(var_sr_trials) * ((1 - EULER_GAMMA) * norm.ppf(1 - 1.0 / n_trials)
                                            + EULER_GAMMA * norm.ppf(1 - 1.0 / (n_trials * math.e))))


def deflated_sharpe(returns: Sequence[float], n_trials: int, sr_trials: Sequence[float]) -> Dict[str, float]:
    """DSR of a daily return series given the per-period Sharpe ratios of ALL trials that were tried."""
    r = np.asarray([x for x in returns if np.isfinite(x)], dtype=float)
    if len(r) < 30 or r.std(ddof=1) == 0:
        return {"dsr": float("nan"), "sr_daily": float("nan"), "sr0": float("nan"), "n_obs": int(len(r)), "n_trials": n_trials}
    sr = float(r.mean() / r.std(ddof=1))
    var_trials = float(np.var([s for s in sr_trials if np.isfinite(s)], ddof=1)) if len(sr_trials) > 1 else 0.0
    sr0 = expected_max_sharpe(max(n_trials, 1), var_trials)
    dsr = probabilistic_sharpe(sr, sr0, len(r), float(skew(r)), float(kurtosis(r, fisher=False)))
    return {"dsr": dsr, "sr_daily": sr, "sr_annual": sr * math.sqrt(252), "sr0_daily": sr0, "sr0_annual": sr0 * math.sqrt(252),
            "psr_vs_zero": probabilistic_sharpe(sr, 0.0, len(r), float(skew(r)), float(kurtosis(r, fisher=False))),
            "n_obs": int(len(r)), "n_trials": int(n_trials)}
