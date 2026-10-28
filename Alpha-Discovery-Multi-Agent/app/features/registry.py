"""Feature registry: definition, domain, availability rule and PIT status of every panel column.

The registry is the contract between Phase 1 and Phase 2. The Quant Agent may only reference
features registered here with point_in_time_safe=True; labels (forward returns) are registered
as non-PIT so the formula validator rejects them.
"""
from typing import Dict, List

import pandas as pd

from app.config.settings import DATASET_VERSION

DOMAINS = ["technical", "fundamental", "valuation", "news", "regime", "macro", "cross_sectional"]


def _f(name, domain, description, formula, source, lookback, availability, pit=True, null_policy="NULL until warm-up / data available"):
    return {"feature_name": name, "category": domain, "description": description, "formula": formula,
            "source": source, "lookback": lookback, "availability_rule": availability,
            "point_in_time_safe": pit, "null_policy": null_policy, "version": DATASET_VERSION}


_CLOSE_T = "close of day t"
_SEC = "SEC filed_date + 1 business day"
_NEWS = "articles published <= 15:30 ET on day t"
_FRED = "FRED observation date + 1 business day"

FEATURES: List[Dict] = [
    # ---------------- technical
    _f("daily_return", "technical", "Total return close-to-close", "adj_close_t/adj_close_t-1 - 1", "yfinance", 1, _CLOSE_T),
    _f("momentum_5d", "technical", "5-day total return", "adj_close_t/adj_close_t-5 - 1", "yfinance", 5, _CLOSE_T),
    _f("momentum_10d", "technical", "10-day total return", "adj_close_t/adj_close_t-10 - 1", "yfinance", 10, _CLOSE_T),
    _f("momentum_20d", "technical", "20-day total return", "adj_close_t/adj_close_t-20 - 1", "yfinance", 20, _CLOSE_T),
    _f("momentum_60d", "technical", "60-day total return", "adj_close_t/adj_close_t-60 - 1", "yfinance", 60, _CLOSE_T),
    _f("momentum_252_21d", "technical", "12-1 month momentum", "adj_close_t-21/adj_close_t-252 - 1", "yfinance", 252, _CLOSE_T),
    _f("rsi_14", "technical", "Wilder RSI (14)", "100 - 100/(1+RS)", "yfinance", 14, _CLOSE_T),
    _f("macd", "technical", "MACD line (12,26)", "EMA12 - EMA26", "yfinance", 26, _CLOSE_T),
    _f("macd_signal", "technical", "MACD signal (9)", "EMA9(MACD)", "yfinance", 35, _CLOSE_T),
    _f("macd_hist", "technical", "MACD histogram", "MACD - signal", "yfinance", 35, _CLOSE_T),
    _f("volatility_20d", "technical", "20-day annualised volatility", "std(ret,20)*sqrt(252)", "yfinance", 20, _CLOSE_T),
    _f("volatility_60d", "technical", "60-day annualised volatility", "std(ret,60)*sqrt(252)", "yfinance", 60, _CLOSE_T),
    _f("close_to_sma20", "technical", "Distance from 20D SMA", "close/SMA20 - 1", "yfinance", 20, _CLOSE_T),
    _f("close_to_sma50", "technical", "Distance from 50D SMA", "close/SMA50 - 1", "yfinance", 50, _CLOSE_T),
    _f("close_to_sma200", "technical", "Distance from 200D SMA", "close/SMA200 - 1", "yfinance", 200, _CLOSE_T),
    _f("sma20_to_sma50", "technical", "SMA20 vs SMA50", "SMA20/SMA50 - 1", "yfinance", 50, _CLOSE_T),
    _f("sma50_to_sma200", "technical", "SMA50 vs SMA200 (golden cross)", "SMA50/SMA200 - 1", "yfinance", 200, _CLOSE_T),
    _f("volume_growth_5d", "technical", "5-day volume growth", "vol_t/vol_t-5 - 1", "yfinance", 5, _CLOSE_T),
    _f("volume_growth_20d", "technical", "20-day volume growth", "vol_t/vol_t-20 - 1", "yfinance", 20, _CLOSE_T),
    _f("volume_ratio_20d", "technical", "Volume vs 20D average", "vol_t/mean(vol,20)", "yfinance", 20, _CLOSE_T),
    _f("dollar_volume_20d", "technical", "20D average dollar volume", "mean(close*volume,20)", "yfinance", 20, _CLOSE_T),
    # ---------------- fundamental (TTM flows, latest balance sheet)
    _f("revenue", "fundamental", "Revenue, trailing twelve months", "sum of 4 quarters", "SEC XBRL", 365, _SEC),
    _f("net_income", "fundamental", "Net income, TTM", "sum of 4 quarters", "SEC XBRL", 365, _SEC),
    _f("operating_income", "fundamental", "Operating income, TTM (pre-tax income proxy for banks)", "sum of 4 quarters", "SEC XBRL", 365, _SEC),
    _f("operating_cash_flow", "fundamental", "Operating cash flow, TTM", "sum of 4 quarters (YTD differenced)", "SEC XBRL", 365, _SEC),
    _f("eps", "fundamental", "Diluted EPS, TTM, split-adjusted to price basis", "sum of 4 quarters / split factor", "SEC XBRL", 365, _SEC),
    _f("roe", "fundamental", "Return on equity", "net_income_ttm / equity", "SEC XBRL", 365, _SEC),
    _f("revenue_growth", "fundamental", "YoY growth of TTM revenue", "rev_ttm / rev_ttm(t-1y) - 1", "SEC XBRL", 730, _SEC),
    _f("eps_growth", "fundamental", "YoY growth of TTM EPS", "eps_ttm / eps_ttm(t-1y) - 1", "SEC XBRL", 730, _SEC),
    _f("net_income_growth", "fundamental", "YoY growth of TTM net income", "ni_ttm / ni_ttm(t-1y) - 1", "SEC XBRL", 730, _SEC),
    _f("asset_growth", "fundamental", "YoY total asset growth", "assets / assets(t-1y) - 1", "SEC XBRL", 365, _SEC),
    _f("profit_margin", "fundamental", "Net margin", "net_income_ttm / revenue_ttm", "SEC XBRL", 365, _SEC),
    _f("operating_margin", "fundamental", "Operating margin", "operating_income_ttm / revenue_ttm", "SEC XBRL", 365, _SEC),
    _f("debt_to_equity", "fundamental", "Leverage", "debt / equity", "SEC XBRL", 0, _SEC),
    _f("debt_to_assets", "fundamental", "Debt to assets", "debt / total_assets", "SEC XBRL", 0, _SEC),
    _f("cash_to_assets", "fundamental", "Cash to assets", "cash / total_assets", "SEC XBRL", 0, _SEC),
    _f("accruals_ratio", "fundamental", "Accruals (earnings quality)", "(ni_ttm - ocf_ttm) / total_assets", "SEC XBRL", 365, _SEC),
    # ---------------- valuation
    _f("pe_ratio", "valuation", "Price / earnings", "market_cap / ni_ttm (ni>0)", "yfinance+SEC", 365, _SEC),
    _f("pb_ratio", "valuation", "Price / book", "market_cap / equity (equity>0)", "yfinance+SEC", 0, _SEC),
    _f("ps_ratio", "valuation", "Price / sales", "market_cap / revenue_ttm", "yfinance+SEC", 365, _SEC),
    _f("earnings_yield", "valuation", "Earnings yield", "ni_ttm / market_cap", "yfinance+SEC", 365, _SEC),
    _f("book_to_market", "valuation", "Book to market", "equity / market_cap", "yfinance+SEC", 0, _SEC),
    _f("sales_yield", "valuation", "Sales yield", "revenue_ttm / market_cap", "yfinance+SEC", 365, _SEC),
    _f("ocf_yield", "valuation", "Operating cash-flow yield (FCF proxy)", "ocf_ttm / market_cap", "yfinance+SEC", 365, _SEC),
    _f("ev_to_sales", "valuation", "Enterprise value / sales", "(mcap+debt-cash)/revenue_ttm", "yfinance+SEC", 365, _SEC),
    _f("market_cap", "valuation", "Market capitalisation (split-consistent)", "close * shares", "yfinance+SEC", 0, _SEC),
    # ---------------- news
    _f("news_count", "news", "Relevant articles in decision window", "count", "Alpha Vantage", 1, _NEWS, null_policy="NULL when NO_COVERAGE; 0 when covered with no articles"),
    _f("unique_event_count", "news", "Distinct events (near-duplicates grouped)", "nunique(event_id)", "Alpha Vantage", 1, _NEWS, null_policy="NULL when NO_COVERAGE"),
    _f("positive_news_count", "news", "FinBERT-positive articles", "count(label=positive)", "FinBERT", 1, _NEWS, null_policy="NULL when NO_COVERAGE"),
    _f("negative_news_count", "news", "FinBERT-negative articles", "count(label=negative)", "FinBERT", 1, _NEWS, null_policy="NULL when NO_COVERAGE"),
    _f("avg_av_sentiment", "news", "Mean Alpha Vantage ticker sentiment", "mean", "Alpha Vantage", 1, _NEWS, null_policy="NULL when no articles"),
    _f("avg_finbert_sentiment", "news", "Mean FinBERT score P(pos)-P(neg)", "mean", "FinBERT", 1, _NEWS, null_policy="NULL when no articles"),
    _f("news_volume_5d", "news", "Articles over 5 days", "sum(news_count,5)", "Alpha Vantage", 5, _NEWS, null_policy="NULL unless window fully covered"),
    _f("news_volume_20d", "news", "Articles over 20 days", "sum(news_count,20)", "Alpha Vantage", 20, _NEWS, null_policy="NULL unless window fully covered"),
    _f("news_volume_zscore_20d", "news", "Abnormal news volume", "(count - mean_prev20)/std_prev20", "Alpha Vantage", 21, _NEWS, null_policy="NULL unless window fully covered"),
    _f("sentiment_5d", "news", "Article-weighted FinBERT sentiment, 5 days", "sum(score)/n", "FinBERT", 5, _NEWS, null_policy="NULL unless window fully covered"),
    _f("sentiment_20d", "news", "Article-weighted FinBERT sentiment, 20 days", "sum(score)/n", "FinBERT", 20, _NEWS, null_policy="NULL unless window fully covered"),
    _f("av_sentiment_5d", "news", "Article-weighted AV sentiment, 5 days", "sum(score)/n", "Alpha Vantage", 5, _NEWS, null_policy="NULL unless window fully covered"),
    _f("av_sentiment_20d", "news", "Article-weighted AV sentiment, 20 days", "sum(score)/n", "Alpha Vantage", 20, _NEWS, null_policy="NULL unless window fully covered"),
    _f("earnings_count", "news", "Earnings-topic articles", "count(topic)", "Alpha Vantage", 1, _NEWS, null_policy="NULL when NO_COVERAGE"),
    _f("merger_count", "news", "M&A-topic articles", "count(topic)", "Alpha Vantage", 1, _NEWS, null_policy="NULL when NO_COVERAGE"),
    _f("source_count", "news", "Distinct publishers", "nunique(publisher)", "Alpha Vantage", 1, _NEWS, null_policy="NULL when NO_COVERAGE"),
    # ---------------- regime (market-wide, same value for all tickers on a date)
    _f("regime_bull", "regime", "1 if walk-forward HMM regime is Bull", "indicator", "SPY+HMM", 504, "HMM refit on data < t, forward-filtered to t"),
    _f("regime_high_vol", "regime", "1 if walk-forward HMM regime is High Volatility", "indicator", "SPY+HMM", 504, "HMM refit on data < t, forward-filtered to t"),
    _f("regime_prob_bull", "regime", "Filtered probability of Bull states", "P(bull | x_1..t)", "SPY+HMM", 504, "forward filter"),
    _f("regime_prob_high_vol", "regime", "Filtered probability of High-Vol states", "P(highvol | x_1..t)", "SPY+HMM", 504, "forward filter"),
    _f("benchmark_momentum_20d", "regime", "SPY 20-day return", "SPY_t/SPY_t-20 - 1", "yfinance", 20, _CLOSE_T),
    _f("benchmark_volatility_20d", "regime", "SPY 20-day volatility", "std*sqrt(252)", "yfinance", 20, _CLOSE_T),
    # ---------------- macro
    _f("treasury_10y", "macro", "10Y Treasury yield (DGS10)", "level", "FRED", 1, _FRED),
    _f("treasury_2y", "macro", "2Y Treasury yield (DGS2)", "level", "FRED", 1, _FRED),
    _f("yield_curve_10y2y", "macro", "10Y-2Y spread (T10Y2Y)", "level", "FRED", 1, _FRED),
    _f("vix", "macro", "CBOE VIX (VIXCLS)", "level", "FRED", 1, _FRED),
    _f("fed_funds_rate", "macro", "Effective fed funds (DFF)", "level", "FRED", 1, _FRED),
    _f("treasury_10y_chg_20d", "macro", "20D change in 10Y yield", "diff(20)", "FRED", 20, _FRED),
    _f("yield_curve_chg_20d", "macro", "20D change in 10Y-2Y", "diff(20)", "FRED", 20, _FRED),
    _f("vix_chg_5d", "macro", "5D VIX change", "pct_change(5)", "FRED", 5, _FRED),
    _f("vix_zscore_60d", "macro", "VIX z-score, 60D", "(vix-mean60)/std60", "FRED", 60, _FRED),
    _f("fed_funds_chg_60d", "macro", "60D change in fed funds", "diff(60)", "FRED", 60, _FRED),
    # ---------------- cross-sectional (precomputed)
    _f("pe_rel_sector", "cross_sectional", "P/E relative to sector median (universe median if sector < 2 names)", "pe / median(pe | sector, t)", "derived", 0, _SEC),
] + [
    _f(f"{b}_cs_rank", "cross_sectional", f"Universe percentile rank of {b}", "rank/N", "derived", 0, "same-date cross-section")
    for b in ["momentum_20d", "momentum_60d", "volatility_20d", "rsi_14", "earnings_yield", "book_to_market",
              "sales_yield", "roe", "revenue_growth", "profit_margin", "avg_finbert_sentiment", "sentiment_20d"]
] + [
    # ---------------- labels (never usable in factors)
    _f(f"fwd_ret_{h}d", "label", f"Forward {h}-day total return (evaluation label)",
       f"adj_close_t+{h}/adj_close_t - 1", "yfinance", -h, "FUTURE - evaluation only", pit=False,
       null_policy="NULL at sample end") for h in (1, 5, 21)
]

_NEWS_PIT = "articles with effective_date <= t (published before 16:00 ET on a trading day, else next session)"
_NEWS_NULL = "NULL when no news coverage for the ticker/period or insufficient articles/history"
FEATURES += [
    _f("news_count_weighted", "news", "Relevance-weighted article count", "sum(w_i)", "FNSPID/Finnhub", 1, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_mean", "news", "Relevance-weighted mean FinBERT sentiment", "sum(w s)/sum(w)", "FinBERT", 1, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_decay", "news", "Decay-weighted FinBERT sentiment (half-life 3 trading days)", "decayed sum(w s)/decayed sum(w)", "FinBERT", 20, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_surprise", "news", "Sentiment z-score vs trailing 20d (strictly prior)", "(s_t - mean20)/std20", "FinBERT", 21, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("news_vol_surprise", "news", "News volume z-score vs trailing 20d (strictly prior)", "(n_t - mean20)/std20", "FNSPID/Finnhub", 21, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_dispersion", "news", "Weighted std of article sentiment within the day (>= 3 articles)", "weighted std", "FinBERT", 1, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_momentum", "news", "Change of decayed sentiment over 5 trading days", "decay_t - decay_{t-5}", "FinBERT", 25, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_earnings", "news", "Weighted sentiment of earnings-type articles", "keyword type tag", "FinBERT", 1, _NEWS_PIT, null_policy=_NEWS_NULL),
    _f("sent_analyst_rating", "news", "Weighted sentiment of analyst-rating articles", "keyword type tag", "FinBERT", 1, _NEWS_PIT, null_policy=_NEWS_NULL),
] + [
    _f(f"{c}_pstd", "news", f"{c} standardised within its provider period (expanding, strictly prior baseline)",
       "(x_t - mean_prior)/std_prior inside the provider period", "FNSPID/Finnhub", 60, _NEWS_PIT, null_policy=_NEWS_NULL)
    for c in ["news_count", "news_count_weighted", "sent_mean", "sent_decay", "sent_dispersion", "sent_momentum",
              "source_count", "sent_earnings", "sent_analyst_rating"]
]


def registry_frame() -> pd.DataFrame:
    return pd.DataFrame(FEATURES)


def pit_safe_features(domains=None) -> Dict[str, str]:
    """feature -> domain for PIT-safe features, optionally restricted to a set of domains."""
    return {f["feature_name"]: f["category"] for f in FEATURES
            if f["point_in_time_safe"] and (domains is None or f["category"] in domains)}


def feature_domain(name: str) -> str:
    for f in FEATURES:
        if f["feature_name"] == name:
            return f["category"]
    return "unknown"
