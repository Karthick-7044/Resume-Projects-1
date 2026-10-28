"""Point-in-time resolution of news publication times to the first tradable session.

Rule (America/New_York):
  published before 16:00 ET on a trading day           -> that trading day
  published at/after 16:00 ET, or on a weekend/holiday -> the next trading day
  low-precision stamps (minute == second == 0, i.e. date-only or hour-only; FNSPID's nasdaq sections
  are date-only)                                       -> the first trading day STRICTLY AFTER the stamp's
                                                          calendar date (conservative: may delay, never advance)
The trading calendar is derived from the SPY price index already in the repository.
"""
from typing import Optional

import numpy as np
import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import RAW_MARKET_DIR


def load_trading_calendar(price_path=None) -> pd.DatetimeIndex:
    """Trading sessions from the SPY daily series (normalised, unique, sorted)."""
    path = price_path or (RAW_MARKET_DIR / "SPY.parquet")
    d = pd.read_parquet(path, columns=["date"])["date"]
    return pd.DatetimeIndex(sorted(pd.to_datetime(d).dt.normalize().unique()))


def is_low_precision(ts_utc: pd.Series) -> pd.Series:
    """True for stamps without a usable time of day (minute == second == 0 in UTC)."""
    ts = pd.to_datetime(ts_utc, utc=True)
    return (ts.dt.minute == 0) & (ts.dt.second == 0)


def resolve_effective_dates(published_utc: pd.Series, trading_days: pd.DatetimeIndex,
                            cfg: Optional[dict] = None) -> pd.DataFrame:
    """Returns DataFrame[effective_date, low_precision, published_et] aligned to the input index.

    effective_date is NaT when the first eligible session lies beyond the end of `trading_days`.
    """
    cfg = cfg or load_news_config()
    tz = cfg["alignment"]["timezone"]
    hh, mm = (int(x) for x in cfg["alignment"]["close_time"].split(":"))
    cal = pd.DatetimeIndex(trading_days).normalize().values.astype("datetime64[ns]")

    ts = pd.to_datetime(published_utc, utc=True)
    low = is_low_precision(ts)
    ny = ts.dt.tz_convert(tz)
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    utc_date = ts.dt.tz_localize(None).dt.normalize()
    after_close = (ny.dt.hour * 60 + ny.dt.minute) >= (hh * 60 + mm)

    base = np.where(low, utc_date.values, ny_date.values).astype("datetime64[ns]")
    left = np.searchsorted(cal, base, side="left")
    right = np.searchsorted(cal, base, side="right")
    on_session = (left < len(cal)) & (cal[np.minimum(left, len(cal) - 1)] == base)
    same_day = on_session & ~low.values & ~after_close.values
    idx = np.where(same_day, left, right)
    eff = np.where(idx < len(cal), cal[np.minimum(idx, len(cal) - 1)], np.datetime64("NaT"))
    return pd.DataFrame({"effective_date": pd.to_datetime(eff), "low_precision": low.values,
                         "published_et": ny.values}, index=published_utc.index)
