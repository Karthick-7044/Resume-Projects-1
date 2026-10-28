"""Comprehensive test suite verifying deterministic pipeline logic."""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from app.data.qa.market_qa import MarketQA
from app.data.qa.sec_qa import SECQA
from app.data.qa.news_qa import NewsQA
from app.data.qa.regime_qa import RegimeQA
from app.features.technical import TechnicalFeatureEngine
from app.features.fundamentals import FundamentalFeatureEngine
from app.features.valuation import ValuationFeatureEngine
from app.config.news_config import load_news_config
from app.features.news_features import NewsFeatureEngine
from app.data.providers.news_provider import score_text_tone
from app.models.regime import MarketRegimeEngine
from app.pipeline.panel_builder import PanelBuilder


def test_market_qa_valid_and_invalid():
    # Valid dataset
    df_valid = pd.DataFrame({
        "date": [date(2025, 1, 1), date(2025, 1, 2)],
        "ticker": ["AAPL", "AAPL"],
        "open": [150.0, 152.0],
        "high": [155.0, 156.0],
        "low": [149.0, 151.0],
        "close": [152.0, 154.0],
        "volume": [1000000, 1200000]
    })
    _, summary = MarketQA.validate_series(df_valid)
    assert summary["overall_status"] == "PASS"

    # Invalid dataset (High < Low violation)
    df_invalid = pd.DataFrame({
        "date": [date(2025, 1, 1)],
        "ticker": ["AAPL"],
        "open": [150.0],
        "high": [140.0],  # Invalid: high < low
        "low": [149.0],
        "close": [145.0],
        "volume": [1000]
    })
    _, sum_inv = MarketQA.validate_series(df_invalid)
    assert sum_inv["fail_count"] > 0


def test_technical_indicators_no_lookahead():
    dates = pd.date_range("2024-01-01", periods=100, freq="B").date
    close_prices = [100.0 + i * 0.5 for i in range(100)]
    df = pd.DataFrame({
        "date": dates,
        "ticker": "AAPL",
        "open": close_prices,
        "high": [p + 2.0 for p in close_prices],
        "low": [p - 2.0 for p in close_prices],
        "close": close_prices,
        "volume": [1000000] * 100
    })

    feats = TechnicalFeatureEngine.calculate_for_ticker(df)
    assert not feats.empty
    assert "rsi_14" in feats.columns
    assert "macd" in feats.columns
    assert "sma_50" in feats.columns
    # Warmup periods for 50d SMA should be strictly NaN
    assert feats["sma_50"].iloc[:49].isnull().all()
    assert feats["sma_50"].iloc[49] is not None


def test_sec_qa_and_point_in_time_alignment():
    """Fundamentals become usable only after the filing date (+1 business day) and only once 4 quarters exist (TTM)."""
    quarters = [  # (period_start, period_end, filed, revenue)
        (date(2023, 4, 1), date(2023, 6, 30), date(2023, 8, 3), 100.0),
        (date(2023, 7, 1), date(2023, 9, 30), date(2023, 11, 2), 110.0),
        (date(2023, 10, 1), date(2023, 12, 31), date(2024, 2, 1), 120.0),
        (date(2024, 1, 1), date(2024, 3, 31), date(2024, 5, 2), 130.0),
        (date(2024, 4, 1), date(2024, 6, 30), date(2024, 8, 1), 140.0),
    ]
    facts_df = pd.DataFrame({
        "ticker": "AAPL", "cik": "0000320193", "taxonomy": "us-gaap", "tag": "Revenues", "metric": "revenue",
        "metric_kind": "duration", "tag_priority": 0, "mapping_status": "PRIMARY", "unit": "USD",
        "value": [q[3] for q in quarters], "start": [q[0] for q in quarters], "period_end": [q[1] for q in quarters],
        "filed_date": [q[2] for q in quarters], "accn": [f"a{i}" for i in range(5)], "fiscal_period": "Q",
        "form": "10-Q", "frame": ""})
    _, qa_sum = SECQA.validate_facts(facts_df)
    assert qa_sum["overall_status"] == "PASS"

    market_dates = pd.DataFrame({
        "date": [date(2024, 4, 15), date(2024, 5, 2), date(2024, 5, 10), date(2024, 8, 5)],
        "ticker": "AAPL"})
    pit_df = FundamentalFeatureEngine.build_daily(market_dates, facts_df)
    rev = pit_df.set_index("date")["revenue"]
    assert pd.isnull(rev[date(2024, 4, 15)])              # only 3 quarters filed so far: no TTM, no look-ahead
    assert pd.isnull(rev[date(2024, 5, 2)])               # filing day itself is not usable (next business day)
    assert rev[date(2024, 5, 10)] == 100.0 + 110.0 + 120.0 + 130.0
    assert rev[date(2024, 8, 5)] == 110.0 + 120.0 + 130.0 + 140.0


def test_valuation_features():
    market_df = pd.DataFrame({
        "date": [date(2025, 1, 2)],
        "ticker": ["AAPL"],
        "close": [150.0]
    })
    fund_df = pd.DataFrame({
        "date": [date(2025, 1, 2)],
        "ticker": ["AAPL"],
        "eps": [6.0],
        "net_income": [90000.0],
        "revenue": [400000.0],
        "shareholders_equity": [60000.0],
        "shares": [15000.0]
    })
    val_df = ValuationFeatureEngine.calculate_valuation_daily(market_df, fund_df)
    assert not val_df.empty
    assert val_df["pe_ratio"].iloc[0] == 25.0  # market cap (150*15000) / net income 90000


def test_news_sentiment_and_qa():
    assert score_text_tone("Company reports record profit growth beating estimates") > 0.0
    assert score_text_tone("Company faces severe plunge and massive losses in probe") < 0.0

    news_df = pd.DataFrame({
        "article_id": ["art1", "art2"],
        "ticker": ["AAPL", "AAPL"],
        "source": ["Bloomberg", "Reuters"],
        "url": ["http://a.com", "http://b.com"],
        "title": ["Apple surges", "Apple beats revenue"],
        "published_at": [pd.to_datetime("2025-01-02 10:00:00"), pd.to_datetime("2025-01-02 14:00:00")],
        "collected_at": [pd.to_datetime("2025-01-02 15:00:00"), pd.to_datetime("2025-01-02 15:00:00")],
        "language": ["en", "en"],
        "tone": [0.8, 0.6],
        "ticker_mapping": ["EXACT", "EXACT"]
    })
    _, qa_sum = NewsQA.validate_articles(news_df)
    assert qa_sum["overall_status"] == "PASS"

    arts = pd.DataFrame({
        "ticker": "AAPL", "provider": "fnspid", "effective_date": pd.Timestamp("2025-01-02"),
        "published_at": pd.to_datetime(["2025-01-02 10:00:00", "2025-01-02 14:00:00"]),
        "sentiment": [0.8, 0.6], "relevance_weight": 1.0, "source_domain": ["bloomberg.com", "reuters.com"],
        "article_type": "other", "finbert_label": "positive"})
    market = pd.DataFrame({"date": pd.to_datetime(["2025-01-02", "2025-01-03"]), "ticker": "AAPL"})
    cfg = load_news_config({"providers": {"fnspid": {"start": "2025-01-01", "end": "2025-01-31"},
                                          "finnhub": {"start": "2026-01-01", "end": "2026-01-31"}}})
    agg_df = NewsFeatureEngine.aggregate_daily_news(arts, market, cfg=cfg)
    day = agg_df[agg_df["date"] == date(2025, 1, 2)].iloc[0]
    assert day["news_count"] == 2 and day["positive_news_count"] == 2
    assert abs(day["avg_finbert_sentiment"] - 0.7) < 1e-9 and day["source_count"] == 2


def test_market_regime_qa():
    regime_df = pd.DataFrame({
        "date": [date(2025, 1, 1), date(2025, 1, 2)],
        "market_regime": ["Bull / Low Volatility", "Bull / Low Volatility"],
        "benchmark_volatility_20d": [0.12, 0.13]
    })
    _, qa_sum = RegimeQA.validate_regimes(regime_df)
    assert qa_sum["overall_status"] == "PASS"
