"""Macro factor features aligned point-in-time to trading dates.

A FRED observation dated d is treated as usable from the next business day (publication lag),
then carried forward across holidays/missing prints (as-of join, never backward-filled).
"""
import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from app.config.settings import MACRO_SERIES

MACRO_FEATURE_COLUMNS = list(MACRO_SERIES.values()) + [
    "treasury_10y_chg_20d", "yield_curve_chg_20d", "vix_chg_5d", "vix_zscore_60d", "fed_funds_chg_60d",
]


class MacroFeatureEngine:
    @staticmethod
    def build_daily(macro_raw: pd.DataFrame, trading_dates, lag_days: int = 1) -> pd.DataFrame:
        dates = pd.DatetimeIndex(sorted(pd.to_datetime(pd.Series(list(trading_dates))).unique()))
        out = pd.DataFrame({"date": dates})
        if macro_raw is None or macro_raw.empty:
            for c in MACRO_FEATURE_COLUMNS:
                out[c] = np.nan
            out["date"] = out["date"].dt.date
            return out
        for sid, name in MACRO_SERIES.items():
            s = macro_raw[macro_raw["series_id"] == sid].dropna(subset=["value"]).copy()
            if s.empty:
                out[name] = np.nan
                continue
            s["available_date"] = pd.to_datetime(s["date"]) + BDay(lag_days)
            s = s.sort_values("available_date")
            j = pd.merge_asof(out[["date"]], s[["available_date", "value"]], left_on="date",
                              right_on="available_date", direction="backward")
            out[name] = j["value"].values
        # Changes are computed on the trading-day series (already PIT)
        out["treasury_10y_chg_20d"] = out["treasury_10y"].diff(20)
        out["yield_curve_chg_20d"] = out["yield_curve_10y2y"].diff(20)
        out["vix_chg_5d"] = out["vix"].pct_change(5, fill_method=None)
        roll = out["vix"].rolling(60, min_periods=60)
        out["vix_zscore_60d"] = (out["vix"] - roll.mean()) / roll.std()
        out["fed_funds_chg_60d"] = out["fed_funds_rate"].diff(60)
        out["date"] = out["date"].dt.date
        return out
