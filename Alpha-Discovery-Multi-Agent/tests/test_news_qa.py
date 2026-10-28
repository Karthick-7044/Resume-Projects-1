"""News QA tests: schema validation, alignment checks, NaN-rate report and the reusable leakage check."""
import numpy as np
import pandas as pd

from app.config.news_config import load_news_config
from app.data.qa.news_qa import NewsQA
from app.features.news_features import NewsFeatureEngine

NOW = pd.Timestamp("2026-01-01")


def good(**over):
    base = {"article_hash": "h1", "article_id": "h1", "ticker": "AAPL", "title": "Apple beats estimates", "url": "u",
            "published_at": pd.Timestamp("2023-05-02 14:00:07", tz="UTC"),
            "fetched_at": pd.Timestamp("2025-01-01", tz="UTC"), "provider": "fnspid", "sentiment": 0.4,
            "p_pos": 0.6, "p_neg": 0.2, "p_neu": 0.2, "effective_date": pd.Timestamp("2023-05-02")}
    base.update(over)
    return base


def check(rows, **kw):
    return NewsQA.validate_articles(pd.DataFrame(rows), universe=["AAPL"], now=NOW, **kw)


def test_clean_article_passes():
    out, s = check([good()])
    assert out["quality_status"].iloc[0] == "PASS" and out["pit_safe"].iloc[0]


def test_future_timestamp_is_rejected():
    out, _ = check([good(published_at=pd.Timestamp("2026-06-01", tz="UTC"))])
    assert out["quality_status"].iloc[0] == "FAIL" and not out["pit_safe"].iloc[0]


def test_sentiment_and_probability_ranges():
    out, _ = check([good(article_hash="a", sentiment=1.4), good(article_hash="b", p_pos=1.2)])
    assert (out["quality_status"] == "FAIL").all()


def test_effective_date_before_published_date_is_rejected():
    out, _ = check([good(effective_date=pd.Timestamp("2023-05-01"))])
    assert out["quality_status"].iloc[0] == "FAIL" and "earlier than the published date" in out["quality_reason"].iloc[0]


def test_article_assigned_to_two_effective_dates_is_rejected():
    out, _ = check([good(effective_date=pd.Timestamp("2023-05-02")), good(effective_date=pd.Timestamp("2023-05-03"))])
    assert (out["quality_status"] == "FAIL").all()
    assert out["quality_reason"].str.contains("more than one effective_date").all()


def test_duplicate_article_hash_is_rejected():
    out, s = check([good(), good()])
    assert out["is_duplicate"].tolist() == [False, True] and "Duplicate article_hash" in out["quality_reason"].iloc[1]


def test_published_after_fetch_is_rejected():
    out, _ = check([good(fetched_at=pd.Timestamp("2023-05-01", tz="UTC"))])
    assert out["quality_status"].iloc[0] == "FAIL"


# --------------------------------------------------------------------- feature-level QA
CFG = load_news_config({"providers": {"fnspid": {"start": "2023-01-02", "end": "2023-03-31"},
                                      "finnhub": {"start": "2023-04-03", "end": "2023-06-30"}}})
DAYS = pd.DatetimeIndex(pd.bdate_range("2023-01-02", "2023-06-30"))
MARKET = pd.DataFrame({"date": DAYS, "ticker": "AAPL"})


def synthetic_articles(seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for d in DAYS:
        for i in range(rng.choice([0, 1, 2, 3])):
            rows.append({"ticker": "AAPL", "provider": "fnspid" if d < pd.Timestamp("2023-04-03") else "finnhub",
                         "effective_date": d, "published_at": d + pd.Timedelta(hours=10), "sentiment": float(rng.normal(0, .4)),
                         "relevance_weight": 1.0, "source_domain": "a.com", "article_type": "other"})
    return pd.DataFrame(rows)


def build(arts, market):
    return NewsFeatureEngine.aggregate_daily_news(arts, market, cfg=CFG)


def test_nan_rate_report_has_one_row_per_ticker_provider_feature():
    feats = build(synthetic_articles(), MARKET)
    rep = NewsQA.feature_nan_report(feats)
    assert {"fnspid", "finnhub"} <= set(rep["news_provider"])
    assert {"ticker", "news_provider", "feature", "nan_rate", "rows"} <= set(rep.columns)
    assert rep["nan_rate"].between(0, 1).all()


def test_leakage_check_reports_no_violation_for_the_engine():
    arts = synthetic_articles()
    assert NewsQA.leakage_check(arts, MARKET, build, ["2023-02-10", "2023-03-20", "2023-05-15"]) == []


def test_leakage_check_detects_a_deliberately_leaky_builder():
    arts = synthetic_articles()

    def leaky(a, m):                       # peeks at the FULL article set regardless of the truncation
        out = build(arts, m)
        out["sent_mean"] = out["sent_mean"] + 1e-3 * len(a)
        return out

    assert NewsQA.leakage_check(arts, MARKET, leaky, ["2023-03-20"]) != []
