"""Market Regime Detection Engine (v2): walk-forward Gaussian HMM + rule-based baseline.

v1 fitted one HMM on the full sample and decoded it with Viterbi, so every label used future
data. v2 is point-in-time:
- Expanding-window refits every `refit_every` trading days using only data up to that day.
- Between refits, regime probabilities come from the forward (filtering) recursion only,
  i.e. P(state_t | observations_1..t). No backward pass, no Viterbi smoothing.
- States are labelled from the fitted means at each refit (states have no intrinsic labels).
The full-sample in-sample HMM is kept only as a diagnostic reference (column `regime_insample`),
never as a model input.
"""
import logging
import os
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import multivariate_normal

from app.config.settings import PROCESSED_REGIME_DIR, REGIME_VERSION
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)
logging.getLogger("hmmlearn").setLevel(logging.ERROR)  # EM convergence chatter on refits
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

REGIME_LABELS = ["Bull / Low Volatility", "Bull / High Volatility", "Bear / High Volatility",
                 "Sideways / Normal Volatility"]


def label_states(means: np.ndarray, vol_threshold: float = 0.20, sideways_band: float = 0.005) -> list:
    """Economic interpretation of fitted states from (mean 20D momentum, mean annualised volatility).

    A state is "High Volatility" when its mean volatility exceeds the threshold OR it is the most
    volatile state of the fit (so the crisis state is never labelled calm, even when the model was
    trained on calmer history). Direction comes from the sign of the state's mean momentum.
    States have no intrinsic meaning; these labels are interpretations recorded per refit.
    """
    top = int(np.argmax(means[:, 1]))
    labels = []
    for s, (mom, vol) in enumerate(means[:, :2]):
        if vol >= vol_threshold or s == top:
            labels.append("Bull / High Volatility" if mom > sideways_band else "Bear / High Volatility")
        else:
            labels.append("Bull / Low Volatility" if mom > sideways_band else "Sideways / Normal Volatility")
    return labels


def rule_based_regime(momentum_20d: float, volatility_20d: float) -> Optional[str]:
    """Transparent baseline used to validate the HMM."""
    if pd.isna(momentum_20d) or pd.isna(volatility_20d):
        return None
    if momentum_20d > 0 and volatility_20d < 0.18:
        return "Bull / Low Volatility"
    if momentum_20d > 0:
        return "Bull / High Volatility"
    if volatility_20d >= 0.20:
        return "Bear / High Volatility"
    return "Sideways / Normal Volatility"


def forward_filter(X: np.ndarray, startprob: np.ndarray, transmat: np.ndarray,
                   means: np.ndarray, covars: np.ndarray, log_alpha0: Optional[np.ndarray] = None) -> np.ndarray:
    """Normalised filtered state probabilities P(s_t | x_1..t) for a Gaussian HMM."""
    n, k = len(X), len(startprob)
    log_b = np.column_stack([multivariate_normal(means[j], covars[j], allow_singular=True).logpdf(X)
                             for j in range(k)]).reshape(n, k)
    log_A = np.log(transmat + 1e-300)
    out = np.empty((n, k))
    prev = log_alpha0
    for t in range(n):
        if prev is None:
            cur = np.log(startprob + 1e-300) + log_b[t]
        else:
            cur = logsumexp(prev[:, None] + log_A, axis=0) + log_b[t]
        cur = cur - logsumexp(cur)
        out[t] = np.exp(cur)
        prev = cur
    return out


class MarketRegimeEngine:
    """Detects market regimes from benchmark (SPY) dynamics without look-ahead."""

    def __init__(self, n_components: int = 3, random_state: int = 42, refit_every: int = 21,
                 min_train: int = 504, burn_in: int = 252, label_start: str = "2018-01-01",
                 regime_version: str = REGIME_VERSION):
        self.n_components = n_components
        self.burn_in = burn_in
        self.label_start = pd.Timestamp(label_start)
        self.random_state = random_state
        self.refit_every = refit_every
        self.min_train = min_train
        self.regime_version = regime_version
        self.fit_log = []

    @staticmethod
    def benchmark_features(benchmark_market_df: pd.DataFrame) -> pd.DataFrame:
        df = benchmark_market_df.sort_values("date").copy().reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])
        px = df["adj_close"].fillna(df["close"]) if "adj_close" in df.columns else df["close"]
        df["benchmark_return"] = px.pct_change(fill_method=None)
        df["benchmark_momentum_20d"] = px.pct_change(20, fill_method=None)
        df["benchmark_volatility_20d"] = df["benchmark_return"].rolling(20, min_periods=20).std() * np.sqrt(252)
        return df

    def _fit(self, X: np.ndarray):
        from hmmlearn.hmm import GaussianHMM
        model = GaussianHMM(n_components=self.n_components, covariance_type="full", n_iter=200,
                            random_state=self.random_state, min_covar=1e-6)
        model.fit(X)
        return model

    def detect_regimes(self, benchmark_market_df: pd.DataFrame, force_refresh: bool = False) -> pd.DataFrame:
        if benchmark_market_df.empty:
            return pd.DataFrame()
        cache_path = PROCESSED_REGIME_DIR / "market_regime.parquet"
        if cache_path.exists() and not force_refresh:
            cached = ParquetStore.read(cache_path)
            if not cached.empty and "regime_rule_based" in cached.columns:
                return cached

        df = self.benchmark_features(benchmark_market_df)
        obs_cols = ["benchmark_momentum_20d", "benchmark_volatility_20d"]
        valid = df[obs_cols].notna().all(axis=1)
        idx = np.where(valid.values)[0]
        X_all = df.loc[valid, obs_cols].values

        n = len(df)
        labels = np.array(["Warmup"] * n, dtype=object)
        states = np.full(n, -1)
        pmax = np.full(n, np.nan)
        p_bull = np.full(n, np.nan)
        p_highvol = np.full(n, np.nan)
        method = np.array(["Warmup"] * n, dtype=object)

        # --- walk-forward HMM (expanding window, forward filtering between refits)
        first_label = int(np.searchsorted(df.loc[valid, "date"].values, np.datetime64(self.label_start)))
        pos = max(self.min_train, first_label)
        while pos < len(X_all):
            block_end = min(pos + self.refit_every, len(X_all))
            try:
                model = self._fit(X_all[:pos])  # trained on observations strictly before `pos`
                # Filtering forgets its initial condition quickly: a 252-day burn-in is enough
                lo = max(0, pos - self.burn_in)
                probs = forward_filter(X_all[lo:block_end], model.startprob_, model.transmat_,
                                       model.means_, model.covars_)[pos - lo:]
                state_labels = label_states(model.means_)
                # Stable ordering: 0 = lowest-volatility state
                vol_order = np.argsort(model.means_[:, 1])
                vol_rank = {int(s): r for r, s in enumerate(vol_order)}
                for j, row in enumerate(probs):
                    t = idx[pos + j]
                    s = int(np.argmax(row))
                    labels[t] = state_labels[s]
                    states[t] = vol_rank[s]
                    pmax[t] = float(row.max())
                    p_bull[t] = float(sum(row[q] for q in range(self.n_components) if state_labels[q].startswith("Bull")))
                    p_highvol[t] = float(sum(row[q] for q in range(self.n_components) if "High" in state_labels[q]))
                    method[t] = "HMM-WalkForward"
                    # Novelty override: an observation far outside the training range (e.g. SPY 20D vol
                    # of 0.8 in March 2020 vs < 0.45 in all prior data) gets near-uniform posteriors.
                    # Such days are labelled from the current observation only (still point-in-time).
                    mom_t, vol_t = X_all[pos + j]
                    if vol_t > 1.25 * X_all[:pos, 1].max() or (vol_t >= 0.35 and row.max() < 0.6):
                        labels[t] = "Bear / High Volatility" if mom_t <= 0 else "Bull / High Volatility"
                        method[t] = "HMM-NoveltyOverride"
                self.fit_log.append({"fit_end": str(df.loc[idx[pos - 1], "date"].date()), "n_obs": pos,
                                     "means": model.means_.round(5).tolist(), "labels": state_labels})
            except Exception as e:  # fall back to rules for this block only
                logger.warning(f"HMM refit failed at obs {pos}: {e}; using rule-based labels for block")
                for j in range(pos, block_end):
                    t = idx[j]
                    labels[t] = rule_based_regime(df.loc[t, "benchmark_momentum_20d"], df.loc[t, "benchmark_volatility_20d"])
                    method[t] = "Rule-Based-Fallback"
            pos = block_end

        # --- rule-based baseline and in-sample reference
        rule = [rule_based_regime(m, v) for m, v in zip(df["benchmark_momentum_20d"], df["benchmark_volatility_20d"])]
        insample = np.array([None] * n, dtype=object)
        try:
            ref = self._fit(X_all)
            ref_states = ref.predict(X_all)
            ref_labels = label_states(ref.means_)
            for j, t in enumerate(idx):
                insample[t] = ref_labels[ref_states[j]]
        except Exception as e:
            logger.warning(f"In-sample reference HMM failed: {e}")

        res = pd.DataFrame({
            "date": df["date"].dt.date,
            "market_regime": labels,
            "hmm_state": states,
            "regime_probability": pmax,
            "regime_prob_bull": p_bull,
            "regime_prob_high_vol": p_highvol,
            "regime_bull": pd.Series(labels).str.startswith("Bull").astype(float).where(pd.Series(labels) != "Warmup").values,
            "regime_high_vol": pd.Series(labels).str.contains("High").astype(float).where(pd.Series(labels) != "Warmup").values,
            "regime_method": method,
            "regime_version": self.regime_version,
            "regime_rule_based": rule,
            "regime_insample": insample,
            "benchmark_return": df["benchmark_return"],
            "benchmark_momentum_20d": df["benchmark_momentum_20d"],
            "benchmark_volatility_20d": df["benchmark_volatility_20d"],
        })
        ParquetStore.write(res, cache_path)
        return res

    @staticmethod
    def validation_report(regime_df: pd.DataFrame, start: Optional[str] = None) -> Dict:
        """State statistics, durations and agreement with baselines (Section 12.1 of the design)."""
        df = regime_df[regime_df["market_regime"] != "Warmup"].copy()
        if start:
            df = df[pd.to_datetime(df["date"]) >= pd.Timestamp(start)]
        if df.empty:
            return {}
        run_id = (df["market_regime"] != df["market_regime"].shift()).cumsum()
        runs = df.groupby(run_id).agg(label=("market_regime", "first"), length=("market_regime", "size"))
        stats = df.groupby("market_regime").agg(
            days=("date", "count"),
            ann_return=("benchmark_return", lambda r: r.mean() * 252),
            ann_vol=("benchmark_return", lambda r: r.std() * np.sqrt(252)),
            mean_momentum_20d=("benchmark_momentum_20d", "mean"),
            mean_probability=("regime_probability", "mean"),
        )
        stats["share"] = stats["days"] / stats["days"].sum()
        stats["mean_duration_days"] = runs.groupby("label")["length"].mean()
        return {
            "period": [str(df["date"].min()), str(df["date"].max())],
            "state_stats": stats.round(4).reset_index().to_dict("records"),
            "transitions": int(len(runs) - 1),
            "mean_run_length": float(runs["length"].mean()),
            "agreement_with_rule_based": float((df["market_regime"] == df["regime_rule_based"]).mean()),
            "agreement_with_insample_hmm": float((df["market_regime"] == df["regime_insample"]).mean()),
        }
