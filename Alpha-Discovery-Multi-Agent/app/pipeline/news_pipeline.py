"""Provider-agnostic news layer: unified articles -> FinBERT scores -> PIT alignment -> QA -> daily features.

One shared path for FNSPID (historical) and Finnhub (recent/ongoing):
    load_unified -> attach_scores (cache) -> resolve_effective_dates -> NewsQA -> NewsFeatureEngine
Coverage (anything outside it is NaN, never 0):
  fnspid  : a ticker-year is covered only if it holds >= coverage.min_articles_per_ticker_year articles
  finnhub : only the windows whose raw response was actually saved
Outputs reports (coverage, NaN rates, PIT report), a weekly dated snapshot, and the daily feature table.
"""
import json
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import DATA_DIR, REPORTS_DIR
from app.data.providers.finnhub_news_provider import FinnhubNewsProvider
from app.data.qa.news_qa import NewsQA, normalize_title
from app.features.news_features import NewsFeatureEngine
from app.features.news_pit import load_trading_calendar, resolve_effective_dates
from app.nlp.news_scoring import attach_scores, load_unified

logger = logging.getLogger(__name__)
SNAPSHOT_DIR = DATA_DIR / "snapshots"

NEWS_DB_COLUMNS = [
    "article_hash", "article_id", "ticker", "provider", "provider_fetch_kind", "published_at", "fetched_at",
    "effective_date", "low_precision", "title", "summary", "source", "publisher", "url", "source_domain",
    "time_precision", "topics", "article_type", "title_mentions_company", "relevance_weight", "relevance_score",
    "p_pos", "p_neg", "p_neu", "sentiment", "finbert_label", "finbert_score", "finbert_status", "finbert_model",
    "finbert_revision", "av_relevance_score", "av_ticker_sentiment", "av_ticker_sentiment_label", "event_id",
    "quality_status", "quality_reason", "pit_safe", "is_duplicate",
]


def fnspid_coverage(arts: pd.DataFrame, cfg: Dict) -> Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]]:
    """Covered intervals per ticker = calendar years with >= min_articles_per_ticker_year FNSPID articles."""
    thr = cfg["coverage"]["min_articles_per_ticker_year"]
    p0, p1 = pd.Timestamp(cfg["providers"]["fnspid"]["start"]), pd.Timestamp(cfg["providers"]["fnspid"]["end"])
    f = arts[arts["provider"] == "fnspid"]
    out: Dict[str, List] = {}
    for t, g in f.groupby("ticker"):
        counts = g["published_at"].dt.year.value_counts()
        out[t] = [(max(p0, pd.Timestamp(year=int(y), month=1, day=1)), min(p1, pd.Timestamp(year=int(y), month=12, day=31)))
                  for y, n in counts.items() if n >= thr]
    return out


def build_news_layer(tickers: List[str], market_dates: pd.DataFrame, cfg: Optional[Dict] = None,
                     write_reports: bool = True) -> Dict:
    cfg = cfg or load_news_config()
    arts = load_unified(tickers)
    if arts.empty:
        raise RuntimeError("No unified news articles found (run build_fnspid_news / news_update first)")
    arts["published_at"] = pd.to_datetime(arts["published_at"], utc=True)
    arts = attach_scores(arts, cfg)

    cal = load_trading_calendar()
    pit = resolve_effective_dates(arts["published_at"], cal, cfg)
    arts["effective_date"], arts["low_precision"] = pit["effective_date"], pit["low_precision"]
    arts["event_id"] = (arts["ticker"] + "|" + arts["title"].map(normalize_title) + "|"
                        + arts["published_at"].dt.strftime("%Y-%m-%d")).factorize()[0]

    # compatibility columns for the existing API/UI contract
    arts["publisher"] = arts["source"]
    arts["relevance_score"] = arts["relevance_weight"]
    arts["finbert_score"] = arts["sentiment"]
    for c in ("av_relevance_score", "av_ticker_sentiment", "av_ticker_sentiment_label"):
        arts[c] = np.nan if c != "av_ticker_sentiment_label" else None

    validated_parts, qa_by_provider = [], {}
    for prov, g in arts.groupby("provider"):
        v, summary = NewsQA.validate_articles(g.reset_index(drop=True), universe=tickers)
        validated_parts.append(v)
        qa_by_provider[prov] = summary
    validated = pd.concat(validated_parts, ignore_index=True)

    coverage: Dict[str, Dict] = {"fnspid": fnspid_coverage(validated, cfg)}
    fin = FinnhubNewsProvider(api_key="unused-for-reads", cfg=cfg)
    coverage["finnhub"] = {t: fin.coverage(t) for t in tickers if fin.coverage(t)}
    if "google_news_rss" in cfg["providers"]:          # 2024-2025 Google News RSS sample: fetched windows only
        from app.pipeline.build_gnews_recent import coverage as gnews_coverage
        coverage["google_news_rss"] = {t: iv for t, iv in gnews_coverage(tickers).items()}

    scored = validated[validated["finbert_status"] == "OK"]
    daily = NewsFeatureEngine.aggregate_daily_news(scored, market_dates, coverage=coverage, cfg=cfg)

    # ------------------------------------------------------------ reports
    stats = {
        "articles": int(len(validated)), "scored": int(len(scored)),
        "unscored_articles": int((validated["finbert_status"] != "OK").sum()),
        "by_provider": validated.groupby("provider").size().to_dict(),
        "low_precision_rows": validated.groupby("provider")["low_precision"].sum().astype(int).to_dict(),
        "low_precision_share": validated.groupby("provider")["low_precision"].mean().round(4).to_dict(),
        "effective_date_beyond_calendar": int(validated["effective_date"].isna().sum()),
        "qa": {k: {kk: vv for kk, vv in v.items() if kk != "reasons"} | {"reasons": v["reasons"][:6]} for k, v in qa_by_provider.items()},
        "provider_periods": cfg["providers"],
        "finbert_revision": validated["finbert_revision"].dropna().unique().tolist(),
    }
    nan_report = NewsQA.feature_nan_report(daily)
    if write_reports:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "news_pit_report.json").write_text(json.dumps(stats, indent=2, default=str))
        nan_report.to_csv(REPORTS_DIR / "news_nan_rates.csv", index=False)
        cov = (validated.assign(year=validated["published_at"].dt.year)
               .pivot_table(index=["provider", "ticker"], columns="year", values="article_hash", aggfunc="count", fill_value=0))
        cov.to_csv(REPORTS_DIR / "news_coverage_all_providers.csv")
        write_weekly_snapshot(validated)
    return {"articles": validated, "daily": daily, "stats": stats, "nan_report": nan_report, "coverage": coverage}


def write_weekly_snapshot(articles: pd.DataFrame, today: Optional[date] = None) -> Optional[str]:
    """One dated snapshot per ISO week (named by that week's Monday) so any result traces to an exact dataset."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    path = SNAPSHOT_DIR / f"news_snapshot_{monday.isoformat()}.parquet"
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return None
    cols = [c for c in NEWS_DB_COLUMNS if c in articles.columns]
    articles[cols].to_parquet(path, index=False)
    logger.info(f"Wrote weekly news snapshot {path.name} ({len(articles):,} articles)")
    return str(path)
