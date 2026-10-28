"""Loader for data/config/news.yaml (single source of truth for news-pipeline thresholds)."""
import copy
from functools import lru_cache
from typing import Any, Dict

import yaml

from app.config.settings import CONFIG_DIR

NEWS_CONFIG_PATH = CONFIG_DIR / "news.yaml"

DEFAULTS: Dict[str, Any] = {
    "provider": "fnspid",
    "window": {"start": "2013-01-01", "end": "2023-12-31"},
    "tickers": "universe",
    "ticker_aliases": {},
    "language": {"min_ascii_alpha_ratio": 0.90},
    "alignment": {"timezone": "America/New_York", "close_time": "16:00", "low_precision_rule": "next_trading_day"},
    "scoring": {"model": "ProsusAI/finbert", "max_length": 128, "batch_size": 32, "summary_chars": 0,
                "backend": "local", "seed": 42},
    "features": {"decay_half_life_days": 3, "decay_lookback_days": 20, "decay_min_mass": 0.25,
                 "baseline_window_days": 20, "min_baseline_days": 10, "min_articles_dispersion": 3,
                 "momentum_lag_days": 5},
    "coverage": {"min_articles_per_ticker_year": 20},
    "relevance": {"mention_weight": 1.0, "other_weight": 0.3},
    "article_types": {},
    "providers": {"fnspid": {"start": "2013-01-01", "end": "2023-12-31"}, "finnhub": {"start": "2024-01-01", "end": None}},
    "standardize_within_provider_period": True,
    "splice": {"split_date": "2024-01-01", "months": 6, "count_ratio": 2.0, "sentiment_shift": 0.15,
               "mention_share_shift": 0.20, "publisher_tv_distance": 0.50},
    "finnhub": {"calls_per_minute": 60, "pacing_seconds": 1.0, "per_call_cap": 200, "daily_lookback_days": 3},
}


def _merge(base: Dict, over: Dict) -> Dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@lru_cache(maxsize=1)
def _cached() -> Dict[str, Any]:
    data = yaml.safe_load(NEWS_CONFIG_PATH.read_text()) if NEWS_CONFIG_PATH.exists() else {}
    return _merge(DEFAULTS, data or {})


def load_news_config(overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    """Config dict (file values over defaults, optional overrides on top). Returns a copy."""
    return _merge(_cached(), overrides or {})
