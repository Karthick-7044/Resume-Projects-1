"""Unified Master Daily Stock Panel Builder (DATE + TICKER)."""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from app.config.settings import DATASET_VERSION, UNIFIED_PANEL_DIR
from app.data.storage.duckdb_manager import DuckDBManager
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

# Columns used for the per-row feature-coverage ratio (one representative per domain group).
COVERAGE_FEATURES = [
    "momentum_20d", "rsi_14", "volatility_20d", "sma50_to_sma200", "revenue", "net_income", "roe",
    "pe_ratio", "earnings_yield", "news_count", "avg_finbert_sentiment", "market_regime", "vix",
    "treasury_10y",
]


def _prep(df: Optional[pd.DataFrame], keys) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.date
    if "ticker" in keys:
        out["ticker"] = out["ticker"].str.upper()
    return out


class PanelBuilder:
    """Builds and materializes the unified daily stock panel across all feature domains."""

    def __init__(self, duckdb_mgr: Optional[DuckDBManager] = None):
        self.duckdb_mgr = duckdb_mgr or DuckDBManager()
        self.unified_dir = UNIFIED_PANEL_DIR
        self.unified_dir.mkdir(parents=True, exist_ok=True)

    def build_panel(
        self,
        market_df: pd.DataFrame,
        technical_df: pd.DataFrame,
        fundamentals_df: pd.DataFrame,
        valuation_df: pd.DataFrame,
        news_df: pd.DataFrame,
        regime_df: pd.DataFrame,
        macro_df: Optional[pd.DataFrame] = None,
        universe_df: Optional[pd.DataFrame] = None,
        cross_sectional_fn=None,
        pipeline_run_id: Optional[str] = None,
        persist: bool = True,
    ) -> pd.DataFrame:
        """Left-joins every domain onto the market (date, ticker) grid; source tables stay separate."""
        if market_df.empty:
            logger.warning("Empty market dataset supplied to panel builder.")
            return pd.DataFrame()

        base = _prep(market_df, ["date", "ticker"])
        if "quality_status" in base.columns:
            base = base.rename(columns={"quality_status": "market_data_quality"})

        if universe_df is not None and not universe_df.empty:
            u = universe_df.copy()
            u["ticker"] = u["ticker"].str.upper()
            base = base.merge(u[[c for c in ["ticker", "company_name", "sector", "industry"] if c in u.columns]],
                              on="ticker", how="left")

        for df in (technical_df, fundamentals_df, valuation_df, news_df):
            d = _prep(df, ["date", "ticker"])
            if d is None:
                continue
            if "quality_status" in d.columns and df is fundamentals_df:
                d = d.rename(columns={"quality_status": "fundamental_data_quality"})
            cols = ["date", "ticker"] + [c for c in d.columns if c not in base.columns]
            base = base.merge(d[cols], on=["date", "ticker"], how="left")

        for df in (regime_df, macro_df):
            d = _prep(df, ["date"])
            if d is None:
                continue
            cols = ["date"] + [c for c in d.columns if c not in base.columns]
            base = base.merge(d[cols], on="date", how="left")

        if cross_sectional_fn is not None:
            cs = cross_sectional_fn(base)
            cs_cols = ["date", "ticker"] + [c for c in cs.columns if c not in base.columns]
            base = base.merge(cs[cs_cols], on=["date", "ticker"], how="left")

        if "news_status" in base.columns:
            base["news_data_quality"] = base["news_status"]
        present = [c for c in COVERAGE_FEATURES if c in base.columns]
        base["feature_coverage_ratio"] = base[present].notna().mean(axis=1).round(4) if present else np.nan
        base["dataset_version"] = DATASET_VERSION
        base["pipeline_run_id"] = pipeline_run_id

        master_panel = base.sort_values(["date", "ticker"]).reset_index(drop=True)
        dup = master_panel.duplicated(subset=["date", "ticker"]).sum()
        if dup:
            raise ValueError(f"DATE + TICKER uniqueness violated: {dup} duplicate rows")

        if persist:
            parquet_path = self.unified_dir / "master_panel.parquet"
            ParquetStore.write(master_panel, parquet_path)
            logger.info(f"Saved unified master panel to {parquet_path} ({len(master_panel)} rows, "
                        f"{master_panel.shape[1]} columns)")
            self.duckdb_mgr.replace_table("daily_stock_panel", master_panel)
        return master_panel
