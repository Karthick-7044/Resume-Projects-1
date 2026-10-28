"""News feature tests: definitions, gating, provider-period isolation and the no-look-ahead (leakage) check."""
import numpy as np
import pandas as pd

from app.config.news_config import load_news_config
from app.features.news_features import NewsFeatureEngine, STANDARDIZED

CFG = load_news_config({"providers": {"fnspid": {"start": "2023-01-02", "end": "2023-03-31"},
                                      "finnhub": {"start": "2023-04-03", "end": "2023-06-30"}}})
DAYS = pd.DatetimeIndex(pd.bdate_range("2023-01-02", "2023-06-30"))
MARKET = pd.DataFrame({"date": DAYS, "ticker": "AAPL"})


def make_articles(seed=0, n_per_day=(0, 1, 2, 3, 4), provider_split="2023-04-03"):
    rng = np.random.default_rng(seed)
    rows = []
    for d in DAYS:
        for i in range(rng.choice(n_per_day)):
            rows.append({
                "ticker": "AAPL", "provider": "fnspid" if d < pd.Timestamp(provider_split) else "finnhub",
                "effective_date": d, "published_at": d + pd.Timedelta(hours=14 + i),
                "sentiment": float(np.clip(rng.normal(0.1, 0.4), -1, 1)),
                "relevance_weight": float(rng.choice([1.0, 0.3])), "source_domain": f"site{i % 3}.com",
                "article_type": str(rng.choice(["earnings", "analyst_rating", "other"])), "article_hash": f"{d}-{i}"})
    return pd.DataFrame(rows)


def features(arts, **kw):
    out = NewsFeatureEngine.aggregate_daily_news(arts, MARKET, cfg=CFG, **kw)
    out["date"] = pd.to_datetime(out["date"])
    return out.set_index("date")


def test_definitions_on_a_known_day():
    d = pd.Timestamp("2023-02-15")
    arts = pd.DataFrame([
        {"ticker": "AAPL", "provider": "fnspid", "effective_date": d, "published_at": d, "sentiment": 0.8,
         "relevance_weight": 1.0, "source_domain": "a.com", "article_type": "earnings"},
        {"ticker": "AAPL", "provider": "fnspid", "effective_date": d, "published_at": d, "sentiment": -0.4,
         "relevance_weight": 0.3, "source_domain": "b.com", "article_type": "other"},
        {"ticker": "AAPL", "provider": "fnspid", "effective_date": d, "published_at": d, "sentiment": 0.2,
         "relevance_weight": 1.0, "source_domain": "a.com", "article_type": "other"}])
    r = features(arts).loc[d]
    assert r["news_count"] == 3 and r["source_count"] == 2
    assert np.isclose(r["news_count_weighted"], 2.3)
    assert np.isclose(r["sent_mean"], (0.8 * 1 - 0.4 * 0.3 + 0.2 * 1) / 2.3)
    assert np.isclose(r["sent_earnings"], 0.8) and np.isnan(r["sent_analyst_rating"])
    assert not np.isnan(r["sent_dispersion"])                       # 3 articles -> defined


def test_dispersion_requires_three_articles_and_nan_not_zero():
    d = pd.Timestamp("2023-02-15")
    two = pd.DataFrame([{"ticker": "AAPL", "provider": "fnspid", "effective_date": d, "published_at": d,
                         "sentiment": s, "relevance_weight": 1.0, "source_domain": "a.com", "article_type": "other"}
                        for s in (0.5, -0.5)])
    r = features(two).loc[d]
    assert np.isnan(r["sent_dispersion"])
    r_empty = features(two).loc[pd.Timestamp("2023-02-16")]       # covered day without articles
    assert r_empty["news_count"] == 0 and np.isnan(r_empty["sent_mean"]) and r_empty["news_status"] == "NO_ARTICLES"


def test_zscores_are_nan_without_enough_trailing_news_days():
    arts = make_articles(seed=1)
    f = features(arts)
    first = f.index[:8]
    assert f.loc[first, "sent_surprise"].isna().all()
    assert f.loc[first, "news_vol_surprise"].isna().all()
    assert f["sent_surprise"].notna().any()                          # but defined once >= 10 prior news days exist


def test_coverage_gaps_are_nan_not_zero():
    f = features(make_articles(), coverage={"fnspid": {"AAPL": [(pd.Timestamp("2023-01-02"), pd.Timestamp("2023-02-10"))]},
                                           "finnhub": {}})
    gap = f.loc["2023-02-20"]
    assert gap["news_status"] == "NO_COVERAGE" and np.isnan(gap["news_count"]) and np.isnan(gap["sent_mean"])
    assert f.loc["2023-05-10", "news_status"] == "NO_COVERAGE"       # finnhub period without coverage record


def test_provider_periods_do_not_share_state():
    f = features(make_articles(seed=2))
    start = pd.Timestamp("2023-04-03")
    assert f.loc[start, "news_provider"] == "finnhub"
    # first days of the finnhub period have no baseline of their own -> NaN, even though fnspid had history
    assert f.loc[f.index[(f.index >= start)][:5], "sent_surprise"].isna().all()
    assert f.loc[f.index[(f.index >= start)][:5], "sent_decay"].notna().sum() <= 5
    for c in STANDARDIZED:                                            # standardised columns exist, raw kept
        assert c in f.columns and f"{c}_pstd" in f.columns


def test_leakage_features_unchanged_when_future_articles_are_deleted():
    arts = make_articles(seed=3)
    full = features(arts)
    cols = list(full.select_dtypes("number").columns)
    for cutoff in ("2023-02-01", "2023-03-15", "2023-04-20", "2023-06-01"):
        t = pd.Timestamp(cutoff)
        trunc = features(arts[arts["effective_date"] <= t])
        a, b = full.loc[full.index <= t, cols], trunc.loc[trunc.index <= t, cols]
        pd.testing.assert_frame_equal(a.astype(float), b.astype(float), check_exact=False, rtol=1e-9, atol=1e-12)


def test_future_article_cannot_change_an_earlier_day():
    arts = make_articles(seed=4)
    base = features(arts)
    spike = arts.iloc[[0]].copy()
    spike["effective_date"] = pd.Timestamp("2023-05-15")
    spike["sentiment"] = 1.0
    spike["published_at"] = pd.Timestamp("2023-05-15 10:00")
    altered = features(pd.concat([arts, spike], ignore_index=True))
    earlier = base.index < pd.Timestamp("2023-05-15")
    num = base.select_dtypes("number").columns
    pd.testing.assert_frame_equal(base.loc[earlier, num], altered.loc[earlier, num], check_exact=False, rtol=1e-9, atol=1e-12)
