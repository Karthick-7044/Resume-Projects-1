"""Factor attribution: which features / feature domains drive a factor's predictive power.

Leave-one-feature-out: a feature leaf is replaced by its cross-sectional mean, which removes
that feature's ranking information while keeping the expression intact. The resulting drop in
rank IC is that feature's contribution. Market-wide features (regime, macro) have no
cross-sectional variation, so they are neutralised with their own time-series mean instead.
Style exposures show whether the factor is a disguised version of a well-known factor.
"""
from typing import Dict

import numpy as np
import pandas as pd

from app.alpha.backtester import Backtester
from app.alpha.dsl import FactorEvaluator, referenced_features
from app.features.registry import feature_domain

STYLE_FACTORS = {
    "momentum": "momentum_60d", "low_volatility": "-volatility_60d", "value": "earnings_yield",
    "size": "market_cap", "quality": "roe", "reversal": "-momentum_5d",
}
MARKET_WIDE_DOMAINS = {"regime", "macro"}


def attribute(expr: str, evaluator: FactorEvaluator, backtester: Backtester, start: str, end: str) -> Dict:
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)

    def mean_ic(factor: pd.DataFrame) -> float:
        ic = backtester.daily_ic(factor)
        v = ic[(ic.index >= lo) & (ic.index <= hi)].mean()
        return float(v) if pd.notna(v) else 0.0

    base_factor = evaluator.evaluate(expr)
    base_ic = mean_ic(base_factor)
    feats = referenced_features(expr)
    by_feature, by_domain = {}, {}
    for f in feats:
        m = evaluator.matrix(f)
        dom = feature_domain(f)
        if dom in MARKET_WIDE_DOMAINS:
            neutral = pd.DataFrame(np.nanmean(m.values), index=m.index, columns=m.columns).where(m.notna())
        else:
            neutral = pd.DataFrame(np.repeat(m.mean(axis=1).values[:, None], m.shape[1], axis=1),
                                   index=m.index, columns=m.columns).where(m.notna())
        drop = base_ic - mean_ic(evaluator.evaluate(expr, overrides={f: neutral}))
        by_feature[f] = {"domain": dom, "ic_contribution": float(drop)}
        by_domain[dom] = by_domain.get(dom, 0.0) + float(drop)

    total = sum(abs(v) for v in by_domain.values())
    shares = {d: (abs(v) / total if total > 0 else 0.0) for d, v in by_domain.items()}

    # Style exposures: average cross-sectional rank correlation with canonical factors
    exposures = {}
    fr = base_factor[(base_factor.index >= lo) & (base_factor.index <= hi)].rank(axis=1)
    for name, e in STYLE_FACTORS.items():
        try:
            s = evaluator.evaluate(e)
        except Exception:
            continue
        sr = s.reindex_like(fr).rank(axis=1)
        c = fr.corrwith(sr, axis=1).mean()
        exposures[name] = float(c) if pd.notna(c) else None

    return {"base_rank_ic": base_ic, "by_feature": by_feature, "by_domain": by_domain,
            "domain_share": shares, "style_exposure": exposures,
            "dominant_domain": max(shares, key=shares.get) if shares else None}


# ---------------------------------------------------------------------- v5 fast attribution
_RANK_CACHE: Dict = {}


def _month_ends(index: pd.DatetimeIndex, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DatetimeIndex:
    idx = index[(index >= lo) & (index <= hi)]
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).max().values)


def _cached_rank(evaluator: FactorEvaluator, feature: str, dates: pd.DatetimeIndex) -> pd.DataFrame:
    key = (id(evaluator), feature, dates[0], dates[-1], len(dates))
    if key not in _RANK_CACHE:
        m = evaluator.matrix(feature).reindex(dates)
        r = m.rank(axis=1, pct=True)
        _RANK_CACHE[key] = r.sub(r.mean(axis=1), axis=0)
    return _RANK_CACHE[key]


def attribute_fast(expr: str, evaluator: FactorEvaluator, backtester: Backtester, start: str, end: str) -> Dict:
    """Fast attribution on month-end dates only.
    Stock-level features: per date, OLS of the factor's cross-sectional ranks on the features' ranks; importance =
    mean |beta| x std(feature rank). Market-wide features (regime, macro; constant across stocks on a date): importance =
    1 - mean rank correlation between the factor and the factor with that feature neutralised. Shares = importance / total.
    The leave-one-out IC drop (attribute) stays available as a check for finally selected factors."""
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    full = evaluator.evaluate(expr)
    dates = _month_ends(full.index, lo, hi)
    fr = full.reindex(dates).rank(axis=1, pct=True)
    fr = fr.sub(fr.mean(axis=1), axis=0)
    feats = referenced_features(expr)
    stock = [f for f in feats if feature_domain(f) not in MARKET_WIDE_DOMAINS]
    market = [f for f in feats if feature_domain(f) in MARKET_WIDE_DOMAINS]
    imp: Dict[str, float] = {}
    if stock:
        X = {f: _cached_rank(evaluator, f, dates) for f in stock}
        acc = {f: [] for f in stock}
        for d in dates:
            y = fr.loc[d]
            M = pd.concat([X[f].loc[d] for f in stock], axis=1)
            ok = y.notna() & M.notna().all(axis=1)
            if ok.sum() < max(10, len(stock) + 3):
                continue
            A = np.column_stack([np.ones(ok.sum()), M[ok].values])
            beta, *_ = np.linalg.lstsq(A, y[ok].values, rcond=None)
            sd = M[ok].std().values
            for j, f in enumerate(stock):
                acc[f].append(abs(beta[j + 1]) * sd[j])
        imp.update({f: float(np.mean(v)) if v else 0.0 for f, v in acc.items()})
    for f in market:
        m = evaluator.matrix(f)
        neutral = pd.DataFrame(np.nanmean(m.values), index=m.index, columns=m.columns).where(m.notna())
        nr = evaluator.evaluate(expr, overrides={f: neutral}).reindex(dates).rank(axis=1)
        c = fr.corrwith(nr, axis=1).mean()
        imp[f] = float(1 - c) if pd.notna(c) else 0.0
    total = sum(imp.values())
    by_feature = {f: {"domain": feature_domain(f), "importance": v, "share": (v / total if total > 0 else 0.0)} for f, v in imp.items()}
    shares: Dict[str, float] = {}
    for f, v in by_feature.items():
        shares[v["domain"]] = shares.get(v["domain"], 0.0) + v["share"]
    ic = backtester.daily_ic(full).reindex(dates)
    return {"method": "fast_month_end_regression", "dates": int(len(dates)), "base_rank_ic": float(ic.mean()) if ic.notna().any() else None,
            "by_feature": by_feature, "domain_share": shares, "style_exposure": {},
            "dominant_domain": max(shares, key=shares.get) if shares else None}
