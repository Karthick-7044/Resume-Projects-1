"""Deterministic Technical Feature Engine."""
from typing import List, Optional
import numpy as np
import pandas as pd

class TechnicalFeatureEngine:
    """Calculates deterministic technical indicators without look-ahead bias.

    Rules strictly enforced:
    - Zero future observations (rolling windows only look backward: t-N to t)
    - No centered windows
    - Warm-up periods remain strictly NaN / NULL (no forward fill)
    - Complete ticker isolation
    """

    @staticmethod
    def calculate_for_ticker(df: pd.DataFrame) -> pd.DataFrame:
        """Calculates all technical indicators for a single ticker's sorted daily OHLCV."""
        if df.empty:
            return pd.DataFrame()

        data = df.sort_values("date").copy().reset_index(drop=True)
        close = data["close"]
        volume = data["volume"].astype(float)
        # Return-based features use the dividend-adjusted series (total return); price-level
        # indicators (SMA, MACD, RSI) use the split-adjusted close.
        total_ret_px = data["adj_close"].fillna(close) if "adj_close" in data.columns else close

        res = pd.DataFrame()
        res["date"] = data["date"]
        res["ticker"] = data["ticker"]

        # 1. Returns
        res["daily_return"] = total_ret_px.pct_change(fill_method=None)

        # 2. Momentum
        res["momentum_5d"] = total_ret_px.pct_change(periods=5, fill_method=None)
        res["momentum_10d"] = total_ret_px.pct_change(periods=10, fill_method=None)
        res["momentum_20d"] = total_ret_px.pct_change(periods=20, fill_method=None)
        res["momentum_60d"] = total_ret_px.pct_change(periods=60, fill_method=None)
        # 12-1 month momentum (skips the most recent month to avoid short-term reversal)
        res["momentum_252_21d"] = total_ret_px.shift(21) / total_ret_px.shift(252) - 1.0

        # 3. RSI 14 (Wilder's RSI / Exponential Moving Average)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Standard Wilder smoothing with min_periods=14 to ensure warm-up remains NaN
        avg_gain = gain.ewm(com=13, adjust=False, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, adjust=False, min_periods=14).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        res["rsi_14"] = 100 - (100 / (1 + rs))
        # Handle zero loss edge case
        res.loc[(avg_loss == 0) & (avg_gain > 0), "rsi_14"] = 100.0
        res.loc[(avg_loss == 0) & (avg_gain == 0), "rsi_14"] = 50.0

        # 4. MACD (12, 26, 9)
        ema_12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
        ema_26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
        res["macd"] = ema_12 - ema_26
        res["macd_signal"] = res["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
        res["macd_hist"] = res["macd"] - res["macd_signal"]

        # 5. Volatility (Annualized standard deviation of daily returns)
        res["volatility_20d"] = res["daily_return"].rolling(window=20, min_periods=20).std() * np.sqrt(252)
        res["volatility_60d"] = res["daily_return"].rolling(window=60, min_periods=60).std() * np.sqrt(252)

        # 6. Moving Averages
        res["sma_5"] = close.rolling(window=5, min_periods=5).mean()
        res["sma_20"] = close.rolling(window=20, min_periods=20).mean()
        res["sma_50"] = close.rolling(window=50, min_periods=50).mean()
        res["sma_100"] = close.rolling(window=100, min_periods=100).mean()
        res["sma_200"] = close.rolling(window=200, min_periods=200).mean()

        # 7. Price Relationships
        res["close_to_sma20"] = (close / res["sma_20"]) - 1.0
        res["close_to_sma50"] = (close / res["sma_50"]) - 1.0
        res["close_to_sma200"] = (close / res["sma_200"]) - 1.0

        # 8. Moving Average Relationships
        res["sma20_to_sma50"] = (res["sma_20"] / res["sma_50"]) - 1.0
        res["sma50_to_sma200"] = (res["sma_50"] / res["sma_200"]) - 1.0

        # 9. Volume Dynamics
        res["volume_growth_5d"] = volume.pct_change(periods=5, fill_method=None)
        res["volume_growth_20d"] = volume.pct_change(periods=20, fill_method=None)
        res["dollar_volume_20d"] = (close * volume).rolling(window=20, min_periods=20).mean()
        vol_sma20 = volume.rolling(window=20, min_periods=20).mean()
        res["volume_ratio_20d"] = volume / vol_sma20.replace(0, np.nan)

        return res

    @classmethod
    def calculate_universe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates indicators across a multi-ticker panel with strict isolation."""
        if df.empty:
            return pd.DataFrame()

        results = []
        for ticker, group in df.groupby("ticker"):
            features = cls.calculate_for_ticker(group)
            results.append(features)

        if not results:
            return pd.DataFrame()

        combined = pd.concat(results, ignore_index=True)
        return combined.sort_values(["date", "ticker"]).reset_index(drop=True)
