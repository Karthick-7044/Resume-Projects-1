"""Integration test for full panel building and DuckDB storage."""
import pytest
import pandas as pd
import numpy as np
from datetime import date
from app.data.storage.duckdb_manager import DuckDBManager
from app.pipeline.panel_builder import PanelBuilder


def test_panel_builder_integration(tmp_path):
    db_path = tmp_path / "test_quant.duckdb"
    duckdb_mgr = DuckDBManager(db_path=db_path)
    builder = PanelBuilder(duckdb_mgr=duckdb_mgr)
    builder.unified_dir = tmp_path

    market_df = pd.DataFrame({
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "ticker": ["AAPL", "AAPL"],
        "open": [150.0, 152.0],
        "high": [155.0, 156.0],
        "low": [149.0, 151.0],
        "close": [152.0, 154.0],
        "adj_close": [152.0, 154.0],
        "volume": [1000000, 1100000],
        "source": ["yfinance", "yfinance"],
        "dataset_version": ["v1.0", "v1.0"],
        "quality_status": ["PASS", "PASS"]
    })

    tech_df = pd.DataFrame({
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "ticker": ["AAPL", "AAPL"],
        "daily_return": [0.01, 0.013],
        "rsi_14": [55.0, 58.0]
    })

    fund_df = pd.DataFrame({
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "ticker": ["AAPL", "AAPL"],
        "revenue": [400000.0, 400000.0],
        "roe": [0.35, 0.35]
    })

    val_df = pd.DataFrame({
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "ticker": ["AAPL", "AAPL"],
        "pe_ratio": [25.0, 25.5]
    })

    news_df = pd.DataFrame({
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "ticker": ["AAPL", "AAPL"],
        "news_count": [3, 5],
        "average_news_tone": [0.4, 0.6]
    })

    regime_df = pd.DataFrame({
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "market_regime": ["Bull / Low Volatility", "Bull / Low Volatility"],
        "hmm_state": [0, 0]
    })

    master = builder.build_panel(
        market_df=market_df,
        technical_df=tech_df,
        fundamentals_df=fund_df,
        valuation_df=val_df,
        news_df=news_df,
        regime_df=regime_df
    )

    assert not master.empty
    assert len(master) == 2
    assert "daily_return" in master.columns
    assert "revenue" in master.columns
    assert "pe_ratio" in master.columns
    assert "news_count" in master.columns
    assert "market_regime" in master.columns

    # Verify DuckDB table was created
    duck_df = duckdb_mgr.query("SELECT * FROM daily_stock_panel")
    assert len(duck_df) == 2
