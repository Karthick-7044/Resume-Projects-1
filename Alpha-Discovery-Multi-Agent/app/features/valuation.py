"""Deterministic Daily Valuation Feature Engine (v2).

All ratios are computed from market capitalisation, so they are invariant to stock splits:
    market_cap_t = close_t (yfinance, split-adjusted to today's basis) x shares (PIT, same basis)
Fundamentals come from the point-in-time daily table, i.e. only filings available on date t.
Invalid denominators (non-positive earnings, equity, revenue, missing shares) produce NULL rather
than fabricated ratios. Yields (earnings/book/sales/cash-flow over price) are also provided because
they stay defined and monotone when earnings turn negative, which makes them better ranking inputs.
"""
import numpy as np
import pandas as pd

VALUATION_COLUMNS = [
    "market_cap", "pe_ratio", "pb_ratio", "ps_ratio", "earnings_yield", "book_to_market",
    "sales_yield", "ocf_yield", "enterprise_value", "ev_to_sales",
]


class ValuationFeatureEngine:
    """Computes daily market valuation ratios combining daily closing prices and PIT fundamentals."""

    @staticmethod
    def calculate_valuation_daily(market_df: pd.DataFrame, fundamentals_daily_df: pd.DataFrame) -> pd.DataFrame:
        if market_df.empty:
            return pd.DataFrame()
        m = market_df[["date", "ticker", "close"]].copy()
        m["date"] = pd.to_datetime(m["date"]).dt.date
        if fundamentals_daily_df.empty:
            for c in VALUATION_COLUMNS:
                m[c] = np.nan
            return m

        f = fundamentals_daily_df.copy()
        f["date"] = pd.to_datetime(f["date"]).dt.date
        cols = ["date", "ticker", "revenue", "net_income", "shareholders_equity", "shares",
                "operating_cash_flow", "debt", "cash"]
        merged = m.merge(f[[c for c in cols if c in f.columns]], on=["date", "ticker"], how="left")
        for c in cols[2:]:
            if c not in merged.columns:
                merged[c] = np.nan

        shares = merged["shares"].where(merged["shares"] > 0)
        mcap = merged["close"] * shares
        ni, eq, rev = merged["net_income"], merged["shareholders_equity"], merged["revenue"]

        out = merged[["date", "ticker", "close"]].copy()
        out["market_cap"] = mcap
        out["pe_ratio"] = (mcap / ni.where(ni > 0)).where(lambda x: x < 2000)
        out["pb_ratio"] = (mcap / eq.where(eq > 0)).where(lambda x: x < 500)
        out["ps_ratio"] = (mcap / rev.where(rev > 0)).where(lambda x: x < 200)
        out["earnings_yield"] = ni / mcap
        out["book_to_market"] = eq / mcap
        out["sales_yield"] = rev / mcap
        out["ocf_yield"] = merged["operating_cash_flow"] / mcap
        out["enterprise_value"] = mcap + merged["debt"].fillna(0.0) - merged["cash"].fillna(0.0)
        out.loc[mcap.isna(), "enterprise_value"] = np.nan
        out["ev_to_sales"] = (out["enterprise_value"] / rev.where(rev > 0)).where(lambda x: (x > 0) & (x < 200))
        return out.sort_values(["date", "ticker"]).reset_index(drop=True)
