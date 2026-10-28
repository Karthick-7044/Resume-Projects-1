"""Splice diagnostics: flags real shifts, and refuses to call the splice clean when there is no post-split data."""
import pandas as pd

from scripts.splice_diagnostics import compute, tv_distance

DAYS = pd.DatetimeIndex(pd.bdate_range("2023-06-01", "2024-07-31"))


def make(pre_n, post_n, post_sent=0.1, post_domain="finnhub-source.com", post_mention=True):
    rows = []
    for i in range(pre_n):
        rows.append({"ticker": "AAPL", "effective_date": pd.Timestamp("2023-09-01") + pd.Timedelta(days=i % 90), "sentiment": 0.1,
                     "source_domain": "nasdaq.com", "title_mentions_company": True})
    for i in range(post_n):
        rows.append({"ticker": "AAPL", "effective_date": pd.Timestamp("2024-02-01") + pd.Timedelta(days=i % 90),
                     "sentiment": post_sent, "source_domain": post_domain, "title_mentions_company": post_mention})
    return pd.DataFrame(rows)


def test_no_post_split_data_is_reported_not_hidden():
    table, verdict = compute(make(200, 0), DAYS)
    assert "CANNOT be assessed" in verdict and table.loc[0, "flag"] == "no coverage on one side of the split"


def test_large_shifts_are_flagged_with_reasons():
    table, verdict = compute(make(200, 1000, post_sent=0.5, post_mention=False), DAYS)
    flag = table.loc[0, "flag"]
    assert "article volume" in flag and "mean sentiment" in flag and "title-mention share" in flag
    assert "publisher mix" in flag and "large shift" in verdict


def test_matching_sources_are_not_flagged():
    table, verdict = compute(make(300, 300, post_domain="nasdaq.com"), DAYS)
    assert table.loc[0, "flag"] == "" and "no ticker exceeds" in verdict


def test_tv_distance_bounds():
    a = pd.Series({"x": 1.0})
    assert tv_distance(a, a) == 0.0 and tv_distance(a, pd.Series({"y": 1.0})) == 1.0
