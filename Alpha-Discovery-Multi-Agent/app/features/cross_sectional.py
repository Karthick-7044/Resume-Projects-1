"""Cross-sectional (universe-relative) features and forward-return labels.

Cross-sectional features compare each stock with the rest of the universe on the SAME date, so
they use no information beyond date t. With a 10-stock universe most sectors contain a single
name; sector-relative valuation therefore uses the sector median only when the sector has at
least two constituents with valid data that day, and the universe median otherwise.

Forward returns are LABELS for evaluation only. They are stored in a separate table and are
registered as non-PIT so the formula validator rejects any factor that references them.
"""
from typing import List

import numpy as np
import pandas as pd

CS_BASE_FEATURES = [
    "momentum_20d", "momentum_60d", "volatility_20d", "rsi_14", "earnings_yield", "book_to_market",
    "sales_yield", "roe", "revenue_growth", "profit_margin", "avg_finbert_sentiment", "sentiment_20d",
]


class CrossSectionalFeatureEngine:
    @staticmethod
    def build(panel: pd.DataFrame, features: List[str] = CS_BASE_FEATURES, min_names: int = 5) -> pd.DataFrame:
        df = panel[["date", "ticker", "sector"] + [f for f in features if f in panel.columns]
                   + [c for c in ["pe_ratio"] if c in panel.columns]].copy()
        out = df[["date", "ticker"]].copy()
        g = df.groupby("date")
        for f in features:
            if f not in df.columns:
                continue
            n = g[f].transform("count")
            rank = g[f].rank(method="average", pct=True)
            z = (df[f] - g[f].transform("mean")) / g[f].transform("std")
            out[f"{f}_cs_rank"] = rank.where(n >= min_names)
            out[f"{f}_cs_z"] = z.where(n >= min_names)
        if "pe_ratio" in df.columns:
            sector_med = df.groupby(["date", "sector"])["pe_ratio"].transform("median")
            sector_n = df.groupby(["date", "sector"])["pe_ratio"].transform("count")
            uni_med = g["pe_ratio"].transform("median")
            ref = np.where(sector_n >= 2, sector_med, uni_med)
            out["pe_rel_sector"] = df["pe_ratio"] / pd.Series(ref, index=df.index).where(lambda x: x > 0)
            out["pe_rel_basis"] = np.where(df["pe_ratio"].isna(), None, np.where(sector_n >= 2, "SECTOR", "UNIVERSE"))
        return out

    @staticmethod
    def forward_returns(market_df: pd.DataFrame, horizons=(1, 5, 21)) -> pd.DataFrame:
        """Total-return labels from adj_close: fwd_ret_h(t) = adj_close[t+h] / adj_close[t] - 1."""
        m = market_df[["date", "ticker", "adj_close"]].copy()
        m["date"] = pd.to_datetime(m["date"])
        m = m.sort_values(["ticker", "date"])
        for h in horizons:
            m[f"fwd_ret_{h}d"] = m.groupby("ticker")["adj_close"].shift(-h) / m["adj_close"] - 1.0
        m["date"] = m["date"].dt.date
        return m.drop(columns=["adj_close"]).reset_index(drop=True)
