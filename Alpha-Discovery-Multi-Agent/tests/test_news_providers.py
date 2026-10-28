"""Provider tests: unified schema, Finnhub idempotency / append-only behaviour (mocked), FNSPID normalisation."""
import json
from datetime import date

import pandas as pd
import pytest

from app.config.news_config import load_news_config
from app.data.providers.finnhub_news_provider import (
    UNIFIED_COLUMNS, FinnhubAuthError, FinnhubNewsProvider, article_hash, month_windows, to_unified)
from app.pipeline.build_fnspid_news import normalize


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._p, self.text = status, payload, json.dumps(payload)[:100]

    def json(self):
        return self._p


class FakeSession:
    """Serves canned articles per (symbol, from, to) and counts calls."""
    def __init__(self, items_for=None, status=200):
        self.items_for, self.status, self.calls = items_for or (lambda s, a, b: []), status, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((params["symbol"], params["from"], params["to"]))
        if self.status != 200:
            return FakeResponse(self.status, {"error": "x"})
        return FakeResponse(200, self.items_for(params["symbol"], params["from"], params["to"]))


def art(i, ts="2024-03-05 15:00:00", title=None):
    return {"id": i, "headline": title or f"Apple headline {i}", "summary": "s", "source": "Reuters",
            "url": f"https://www.reuters.com/a/{i}", "datetime": int(pd.Timestamp(ts, tz="UTC").timestamp())}


def provider(tmp_path, session, **kw):
    cfg = load_news_config({"finnhub": {"per_call_cap": 3, "pacing_seconds": 0.0}})
    return FinnhubNewsProvider(api_key="test-key", raw_dir=tmp_path / "raw", unified_dir=tmp_path / "uni",
                               session=session, sleep=lambda s: None, cfg=cfg, **kw)


def test_month_windows_cover_range_exactly():
    w = month_windows(date(2024, 1, 15), date(2024, 3, 10))
    assert w == [(date(2024, 1, 15), date(2024, 1, 31)), (date(2024, 2, 1), date(2024, 2, 29)),
                 (date(2024, 3, 1), date(2024, 3, 10))]


def test_unified_schema_and_deterministic_hash():
    df = to_unified("AAPL", [art(1)], pd.Timestamp("2024-04-01", tz="UTC"))
    assert list(df.columns) == UNIFIED_COLUMNS
    r = df.iloc[0]
    assert r["provider"] == "finnhub" and r["provider_fetch_kind"] == "api" and r["ticker"] == "AAPL"
    assert r["article_hash"] == article_hash("AAPL", "Apple headline 1", pd.Timestamp("2024-03-05 15:00:00", tz="UTC"))
    assert r["published_at"].tzinfo is not None and r["fetched_at"] > r["published_at"]
    assert 0.0 < r["relevance_weight"] <= 1.0 and r["article_type"]


def test_raw_json_saved_before_processing_and_backfill_is_idempotent(tmp_path):
    sess = FakeSession(lambda s, a, b: [art(1), art(2)])
    p = provider(tmp_path, sess)
    p.backfill(["AAPL"], date(2024, 3, 1), date(2024, 4, 30))
    saved = sorted((tmp_path / "raw" / "AAPL").glob("*.json"))
    assert [f.name for f in saved] == ["2024-03.json", "2024-04.json"]
    assert len(sess.calls) == 2
    p.backfill(["AAPL"], date(2024, 3, 1), date(2024, 4, 30))          # rerun: nothing is fetched again
    assert len(sess.calls) == 2
    assert p.materialize_backfill(["AAPL"])["AAPL"] == 2                # 2 distinct articles
    assert p.materialize_backfill(["AAPL"])["AAPL"] == 0                # idempotent append


def test_capped_window_is_split_automatically(tmp_path):
    def items(s, a, b):
        span = (date.fromisoformat(b) - date.fromisoformat(a)).days
        return [art(k) for k in range(5)] if span > 10 else [art(k + 100) for k in range(2)]
    sess = FakeSession(items)
    p = provider(tmp_path, sess)
    p.backfill(["AAPL"], date(2024, 3, 1), date(2024, 3, 31))
    names = sorted(f.name for f in (tmp_path / "raw" / "AAPL").glob("*.json"))
    assert names[0] == "2024-03.json" and any("__" in n for n in names)      # split windows were saved too
    assert len(sess.calls) > 1


def test_daily_update_appends_only_new_rows_and_never_edits_old(tmp_path):
    state = {"items": [art(1), art(2)]}
    sess = FakeSession(lambda s, a, b: state["items"])
    p = provider(tmp_path, sess)
    r1 = p.daily_update(["AAPL"], days=3)
    assert r1["AAPL"] == {"fetched": 2, "new": 2}
    before = pd.read_parquet(p.unified_path("AAPL"))
    state["items"] = [art(1), art(2), art(3)]                           # overlapping window + one new article
    r2 = p.daily_update(["AAPL"], days=3)
    assert r2["AAPL"] == {"fetched": 3, "new": 1}
    after = pd.read_parquet(p.unified_path("AAPL"))
    assert len(after) == 3
    # old rows are byte-for-byte unchanged (including their original fetched_at)
    merged = before.merge(after, on="article_hash", suffixes=("_b", "_a"))
    assert (merged["fetched_at_b"] == merged["fetched_at_a"]).all() and (merged["title_b"] == merged["title_a"]).all()
    assert (tmp_path / "uni" / "daily_log.csv").exists()


def test_auth_failure_raises_and_writes_nothing(tmp_path):
    p = provider(tmp_path, FakeSession(status=401))
    with pytest.raises(FinnhubAuthError):
        p.fetch_window("AAPL", date(2024, 3, 1), date(2024, 3, 31))
    assert not list((tmp_path / "raw").rglob("*.json"))


def test_missing_key_is_an_error_not_a_hardcoded_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    p = FinnhubNewsProvider(api_key=None, raw_dir=tmp_path / "r", unified_dir=tmp_path / "u", sleep=lambda s: None)
    with pytest.raises(FinnhubAuthError):
        p.fetch_window("AAPL", date(2024, 3, 1), date(2024, 3, 31))


# ---------------------------------------------------------------------- FNSPID normalisation
def raw_rows():
    base = {"url": "https://www.nasdaq.com/articles/x", "publisher": "", "summary": "", "section": "nasdaq_sorted",
            "source_file": "f", "row_format": "B"}
    return pd.DataFrame([
        {**base, "date_raw": "2020-06-05 06:30:54", "title": "Apple beats earnings estimates", "symbol": "AAPL"},
        {**base, "date_raw": "2020-06-05 06:30:54", "title": "Apple beats earnings estimates", "symbol": "AAPL"},   # exact dup
        {**base, "date_raw": "2020-06-06 00:00:00", "title": "", "symbol": "AAPL"},                              # empty title
        {**base, "date_raw": "2020-06-07 00:00:00", "title": "Facebook launches new product", "symbol": "FB"},    # alias
        {**base, "date_raw": "2020-06-07 00:00:00", "title": "Привет мир news", "symbol": "AAPL"},  # Russian
        {**base, "date_raw": "2024-02-01 10:00:00", "title": "Outside window", "symbol": "AAPL"},
        {**base, "date_raw": "2020-06-08 10:00:00", "title": "Unknown ticker news", "symbol": "ZZZZ"},
    ])


def test_fnspid_normalisation_filters_dedups_and_maps_aliases():
    cfg = load_news_config()
    df, stats = normalize(raw_rows(), ["AAPL", "META"], cfg)
    assert sorted(df["title"]) == ["Apple beats earnings estimates", "Facebook launches new product"]
    assert df.loc[df["title"].str.startswith("Facebook"), "ticker"].iloc[0] == "META"
    assert (df["provider"] == "fnspid").all() and (df["provider_fetch_kind"] == "static").all()
    assert df["article_hash"].is_unique and df["published_at"].dt.tz is not None
    assert set(["article_hash", "ticker", "published_at", "fetched_at", "title", "summary", "source", "url",
                "provider"]) <= set(df.columns)
    assert stats["english_only"] < stats["non_empty_title"]                     # the Russian row was dropped
    assert (df["time_precision"] == "LOW").any()                                # midnight stamp = date-only


def test_daily_update_splits_a_capped_window_so_no_articles_are_lost(tmp_path):
    def items(sym, a, b):
        span = (date.fromisoformat(b) - date.fromisoformat(a)).days
        if span >= 2:                                              # 3-day window hits the cap (3 articles)
            return [art(1), art(2), art(3)]
        d = a.replace("-", "")
        return [art(int(d) * 10 + k, ts=f"{a} 12:00:00") for k in range(2)]      # distinct articles per day
    sess = FakeSession(items)
    p = provider(tmp_path, sess)
    rep = p.daily_update(["AAPL"], days=3)
    assert len(sess.calls) > 1                                      # the capped window was split
    assert rep["AAPL"]["fetched"] > 3 and len(pd.read_parquet(p.unified_path("AAPL"))) == rep["AAPL"]["new"]
