"""Novelty gate: is a new formula just a known factor in disguise?

Reference set = every distinct valid formula of the offline knowledge-base library (built from its 21 documented ideas)
plus seven classic style factors (momentum, value, size, profitability, investment, short-term reversal, low volatility).
For a candidate formula we compute, on the TRAINING window only (sampled every `step` trading days):
  * max_abs_corr : largest mean daily cross-sectional rank correlation with any reference factor
  * closest      : which reference factor that is
  * residual IC  : the rank IC that remains after regressing the candidate's daily cross-sectional ranks on the seven
                   style factors' ranks (OLS per day) - i.e. predictive power NOT explained by known styles
The Critic rejects a formula whose max_abs_corr exceeds T["novelty_max_corr"] (0.5).
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.alpha.dsl import FactorEvaluator

STYLES = {
    "momentum_12_1": "cs_rank(momentum_252_21d)",
    "value_book_to_market": "cs_rank(book_to_market)",
    "size_small": "-cs_rank(market_cap)",
    "profitability_roe": "cs_rank(roe)",
    "investment_conservative": "-cs_rank(asset_growth)",
    "short_term_reversal": "-cs_rank(momentum_5d)",
    "low_volatility": "-cs_rank(volatility_60d)",
}


def _rank(m: pd.DataFrame) -> pd.DataFrame:
    r = m.rank(axis=1, pct=True)
    return r.sub(r.mean(axis=1), axis=0)


class NoveltyReference:
    def __init__(self, evaluator: FactorEvaluator, start: str, end: str, library: Optional[List[str]] = None,
                 step: int = 5, fwd: Optional[pd.DataFrame] = None):
        self.ev, self.start, self.end, self.step = evaluator, pd.Timestamp(start), pd.Timestamp(end), step
        self.fwd = fwd
        if library is None:
            from app.alpha.walkforward import load_library
            library = [x["formula"] for x in load_library("offline")]
        self.refs: Dict[str, pd.DataFrame] = {}
        for name, expr in {**STYLES, **{f: f for f in library}}.items():
            try:
                self.refs[name] = self._sample(self.ev.evaluate(expr))
            except Exception:          # a reference that cannot be evaluated on this panel is skipped
                continue
        self.style_names = [s for s in STYLES if s in self.refs]

    def _sample(self, m: pd.DataFrame) -> pd.DataFrame:
        m = m[(m.index >= self.start) & (m.index <= self.end)]
        return _rank(m.iloc[:: self.step])

    def check(self, factor: pd.DataFrame) -> Dict:
        f = self._sample(factor)
        best, closest = 0.0, None
        for name, ref in self.refs.items():
            a, b = f.align(ref, join="inner")
            c = a.corrwith(b, axis=1).mean()
            if pd.notna(c) and abs(c) > abs(best):
                best, closest = float(c), name
        out = {"max_abs_corr": abs(best), "signed_corr": best, "closest": closest}
        if self.fwd is not None:
            out.update(self.residual_ic(factor))
        return out

    def residual_ic(self, factor: pd.DataFrame, start=None, end=None) -> Dict:
        """Mean daily rank IC of the part of the factor not explained by the style factors (OLS per date)."""
        lo, hi = pd.Timestamp(start or self.start), pd.Timestamp(end or self.end)
        f = _rank(factor[(factor.index >= lo) & (factor.index <= hi)])
        styles = {s: _rank(self.ev.evaluate(STYLES[s]).reindex_like(f)) for s in self.style_names}
        fwd = self.fwd.reindex_like(f)
        ics = []
        for d in f.index:
            y = f.loc[d]
            X = pd.concat([styles[s].loc[d] for s in styles], axis=1)
            ok = y.notna() & X.notna().all(axis=1) & fwd.loc[d].notna()
            if ok.sum() < 20:
                continue
            Xo = np.column_stack([np.ones(ok.sum()), X[ok].values])
            beta, *_ = np.linalg.lstsq(Xo, y[ok].values, rcond=None)
            resid = y[ok].values - Xo @ beta
            ics.append(pd.Series(resid).corr(fwd.loc[d][ok].reset_index(drop=True), method="spearman"))
        ic = pd.Series(ics).dropna()
        t = float(ic.mean() / ic.std() * np.sqrt(len(ic))) if len(ic) > 2 and ic.std() > 0 else float("nan")
        return {"residual_ic": float(ic.mean()) if len(ic) else float("nan"), "residual_ic_t": t, "residual_days": int(len(ic))}
