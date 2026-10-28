"""Cross-sectional factor backtester.

Timing: a signal computed with information up to the close of day t is held from the close of
t to the close of t+1 and earns the forward total return fwd_ret_1d(t). Portfolios are
dollar-neutral, rank-weighted, rebalanced every `rebalance_days`, and pay a one-way cost per unit
of turnover. Labels (forward returns) are only ever read here, never by the factor language.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.config.settings import (
    ALPHA_WINDOWS, ALPHA_REBALANCE_DAYS, ALPHA_TEST_END, ALPHA_TEST_START, ALPHA_TRAIN_END, ALPHA_TRAIN_START,
    ALPHA_TRANSACTION_COST_BPS, ALPHA_VALID_END, ALPHA_VALID_START,
)

MIN_BREADTH = 5
COST_GRID_BPS = [0, 5, 10, 20, 50]
PERIODS = {
    "train": (ALPHA_TRAIN_START, ALPHA_TRAIN_END),
    "valid": (ALPHA_VALID_START, ALPHA_VALID_END),
    "test": (ALPHA_TEST_START, ALPHA_TEST_END),
}


def _max_drawdown(returns: pd.Series) -> float:
    eq = (1.0 + returns.fillna(0.0)).cumprod()
    return float((eq / eq.cummax() - 1.0).min()) if len(eq) else np.nan


def perf_stats(r: pd.Series) -> Dict[str, float]:
    r = r.dropna()
    if len(r) < 20:
        return {"ann_return": np.nan, "ann_vol": np.nan, "sharpe": np.nan, "sortino": np.nan,
                "max_drawdown": np.nan, "calmar": np.nan, "hit_rate": np.nan, "days": int(len(r))}
    mu, sd = r.mean() * 252, r.std() * np.sqrt(252)
    downside = r[r < 0].std() * np.sqrt(252)
    mdd = _max_drawdown(r)
    return {"ann_return": float(mu), "ann_vol": float(sd), "sharpe": float(mu / sd) if sd > 0 else np.nan,
            "sortino": float(mu / downside) if downside and downside > 0 else np.nan,
            "max_drawdown": mdd, "calmar": float(mu / abs(mdd)) if mdd and mdd < 0 else np.nan,
            "hit_rate": float((r > 0).mean()), "days": int(len(r))}


def ic_stats(ic: pd.Series) -> Dict[str, float]:
    ic = ic.dropna()
    if len(ic) < 20:
        return {"mean": np.nan, "icir": np.nan, "t_stat": np.nan, "positive_share": np.nan, "n": int(len(ic))}
    sd = ic.std()
    return {"mean": float(ic.mean()), "icir": float(ic.mean() / sd) if sd > 0 else np.nan,
            "t_stat": float(ic.mean() / sd * np.sqrt(len(ic))) if sd > 0 else np.nan,
            "positive_share": float((ic > 0).mean()), "n": int(len(ic))}


class Backtester:
    def __init__(self, labels: pd.DataFrame, regimes: Optional[pd.DataFrame] = None,
                 rebalance_days: int = ALPHA_REBALANCE_DAYS, cost_bps: float = ALPHA_TRANSACTION_COST_BPS,
                 window: str = "recent"):
        self.window = window
        self.periods = ALPHA_WINDOWS[window]
        lab = labels.copy()
        lab["date"] = pd.to_datetime(lab["date"])
        self.fwd1 = lab.pivot(index="date", columns="ticker", values="fwd_ret_1d").sort_index()
        self.fwd5 = lab.pivot(index="date", columns="ticker", values="fwd_ret_5d").sort_index()
        self.rebalance_days = rebalance_days
        self.cost_bps = cost_bps
        self.regime = None
        if regimes is not None and not regimes.empty:
            rg = regimes.copy()
            rg["date"] = pd.to_datetime(rg["date"])
            self.regime = rg.drop_duplicates("date").set_index("date")["market_regime"]

    # ------------------------------------------------------------------ building blocks
    def weights(self, factor: pd.DataFrame) -> pd.DataFrame:
        """Dollar-neutral rank weights with gross exposure 1, held between rebalance dates."""
        f = factor.reindex(index=self.fwd1.index, columns=self.fwd1.columns)
        rank = f.rank(axis=1, pct=True)
        dem = rank.sub(rank.mean(axis=1), axis=0)
        w = dem.div(dem.abs().sum(axis=1).replace(0, np.nan), axis=0)
        w[f.notna().sum(axis=1) < MIN_BREADTH] = np.nan
        w = w.fillna(0.0)
        keep = np.zeros(len(w), dtype=bool)
        keep[::self.rebalance_days] = True
        w[~keep] = np.nan
        return w.ffill().fillna(0.0)

    def daily_ic(self, factor: pd.DataFrame, horizon: int = 1, method: str = "spearman") -> pd.Series:
        fwd = self.fwd1 if horizon == 1 else self.fwd5
        f = factor.reindex(index=fwd.index, columns=fwd.columns)
        ok = (f.notna() & fwd.notna()).sum(axis=1) >= MIN_BREADTH
        a, b = (f.rank(axis=1), fwd.rank(axis=1)) if method == "spearman" else (f, fwd)
        b = b.where(f.notna())
        a = a.where(b.notna())
        ic = a.corrwith(b, axis=1)
        ic[~ok] = np.nan
        if horizon > 1:  # non-overlapping samples
            ic = ic.iloc[::horizon]
        return ic

    # ------------------------------------------------------------------ full evaluation
    def run(self, factor: pd.DataFrame, periods: Optional[List[str]] = None) -> Dict:
        periods = periods or ["train", "valid"]
        w = self.weights(factor)
        gross_by_name = w * self.fwd1.reindex_like(w)
        gross = gross_by_name.sum(axis=1)
        turnover = w.diff().abs().sum(axis=1).fillna(0.0)
        active = (w.abs().sum(axis=1) > 0)
        ic = self.daily_ic(factor)
        ic5 = self.daily_ic(factor, horizon=5)
        ic_p = self.daily_ic(factor, method="pearson")

        out: Dict = {}
        for name in periods:
            lo, hi = (pd.Timestamp(x) for x in self.periods[name])
            m = (w.index >= lo) & (w.index <= hi) & self.fwd1.notna().any(axis=1).values
            g, t, act = gross[m], turnover[m], active[m]
            net = g - t * self.cost_bps / 1e4
            stats = perf_stats(net[act] if act.any() else net)
            years = max(len(g) / 252.0, 1e-9)
            res = {
                **stats,
                "gross_sharpe": perf_stats(g[act] if act.any() else g)["sharpe"],
                "annual_turnover": float(t.sum() / years),
                "active_day_share": float(act.mean()) if len(act) else 0.0,
                "rank_ic": ic_stats(ic[(ic.index >= lo) & (ic.index <= hi)]),
                "rank_ic_5d": ic_stats(ic5[(ic5.index >= lo) & (ic5.index <= hi)]),
                "pearson_ic": ic_stats(ic_p[(ic_p.index >= lo) & (ic_p.index <= hi)]),
                "cost_sensitivity": {str(c): perf_stats((g - t * c / 1e4)[act] if act.any() else g)["sharpe"]
                                     for c in COST_GRID_BPS},
            }
            # per-year stability
            yr_ic = ic[(ic.index >= lo) & (ic.index <= hi)].groupby(lambda d: d.year).mean()
            res["ic_by_year"] = {int(k): float(v) for k, v in yr_ic.dropna().items()}
            # concentration of P&L by name
            contrib = gross_by_name[m].sum()
            denom = contrib.abs().sum()
            res["pnl_share_by_ticker"] = {k: float(v / denom) for k, v in contrib.items()} if denom > 0 else {}
            res["max_ticker_pnl_share"] = float(contrib.abs().max() / denom) if denom > 0 else np.nan
            # regime-specific behaviour
            if self.regime is not None:
                reg = self.regime.reindex(g.index)
                by = {}
                for label in reg.dropna().unique():
                    rm = (reg == label).values
                    by[label] = {"days": int(rm.sum()), "sharpe": perf_stats(net[rm])["sharpe"],
                                 "ann_return": perf_stats(net[rm])["ann_return"],
                                 "rank_ic": float(ic.reindex(g.index)[rm].mean()) if rm.sum() else np.nan}
                res["by_regime"] = by
            out[name] = res
        out["_series"] = {"net": gross - turnover * self.cost_bps / 1e4, "ic": ic, "gross": gross}
        return out

    def equity_curve(self, factor: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        w = self.weights(factor)
        net = (w * self.fwd1.reindex_like(w)).sum(axis=1) - w.diff().abs().sum(axis=1).fillna(0) * self.cost_bps / 1e4
        net = net[(net.index >= pd.Timestamp(start)) & (net.index <= pd.Timestamp(end))]
        return pd.DataFrame({"date": net.index, "net_return": net.values, "equity": (1 + net.fillna(0)).cumprod().values})
