"""Splice diagnostics: does the news change character at the FNSPID -> Finnhub join (2024-01-01)?

    python scripts/splice_diagnostics.py

Compares the 6 months before the split date with the 6 months after, per ticker: mean daily article
count (per covered trading day), mean/std of FinBERT sentiment, publisher mix (top source domains and
total-variation distance), and the share of titles that mention the company/ticker. Writes
reports/splice_diagnostics.csv and reports/splice_verdict.txt and flags tickers with a large shift
(thresholds in data/config/news.yaml -> splice). If there is no post-split coverage, the verdict says so
instead of pretending the splice is clean.
"""
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config.news_config import load_news_config  # noqa: E402
from app.config.settings import PROCESSED_NEWS_DIR, REPORTS_DIR  # noqa: E402


def _mix(domains: pd.Series) -> pd.Series:
    return domains.value_counts(normalize=True) if len(domains) else pd.Series(dtype=float)


def tv_distance(a: pd.Series, b: pd.Series) -> float:
    if a.empty or b.empty:
        return float("nan")
    idx = a.index.union(b.index)
    return 0.5 * float(np.abs(a.reindex(idx, fill_value=0) - b.reindex(idx, fill_value=0)).sum())


def compute(articles: pd.DataFrame, trading_days: pd.DatetimeIndex, cfg: Optional[Dict] = None):
    """Returns (table, verdict_text). `articles` needs ticker, effective_date, sentiment, source_domain,
    title_mentions_company; `trading_days` is the trading calendar."""
    cfg = cfg or load_news_config()
    sp = cfg["splice"]
    split = pd.Timestamp(sp["split_date"])
    pre0, post1 = split - pd.DateOffset(months=sp["months"]), split + pd.DateOffset(months=sp["months"]) - pd.Timedelta(days=1)
    pre_days = trading_days[(trading_days >= pre0) & (trading_days < split)]
    post_days = trading_days[(trading_days >= split) & (trading_days <= post1)]
    a = articles.copy()
    a["effective_date"] = pd.to_datetime(a["effective_date"])
    rows, flagged = [], []
    for t in sorted(a["ticker"].unique()):
        g = a[a["ticker"] == t]
        pre = g[(g["effective_date"] >= pre0) & (g["effective_date"] < split)]
        post = g[(g["effective_date"] >= split) & (g["effective_date"] <= post1)]
        row = {"ticker": t, "pre_articles": len(pre), "post_articles": len(post),
               "pre_mean_daily_count": len(pre) / max(len(pre_days), 1), "post_mean_daily_count": len(post) / max(len(post_days), 1),
               "pre_sent_mean": pre["sentiment"].mean(), "post_sent_mean": post["sentiment"].mean(),
               "pre_sent_std": pre["sentiment"].std(), "post_sent_std": post["sentiment"].std(),
               "pre_mention_share": pre["title_mentions_company"].mean() if len(pre) else np.nan,
               "post_mention_share": post["title_mentions_company"].mean() if len(post) else np.nan,
               "pre_top_sources": ", ".join(_mix(pre["source_domain"]).head(3).index),
               "post_top_sources": ", ".join(_mix(post["source_domain"]).head(3).index),
               "publisher_tv_distance": tv_distance(_mix(pre["source_domain"]), _mix(post["source_domain"]))}
        reasons = []
        if len(pre) == 0 or len(post) == 0:
            reasons.append("no coverage on one side of the split")
        else:
            ratio = (row["post_mean_daily_count"] + 1e-9) / (row["pre_mean_daily_count"] + 1e-9)
            if ratio > sp["count_ratio"] or ratio < 1 / sp["count_ratio"]:
                reasons.append(f"article volume x{ratio:.2f}")
            if abs(row["post_sent_mean"] - row["pre_sent_mean"]) > sp["sentiment_shift"]:
                reasons.append(f"mean sentiment {row['pre_sent_mean']:+.2f} -> {row['post_sent_mean']:+.2f}")
            if abs(row["post_mention_share"] - row["pre_mention_share"]) > sp["mention_share_shift"]:
                reasons.append(f"title-mention share {row['pre_mention_share']:.0%} -> {row['post_mention_share']:.0%}")
            if row["publisher_tv_distance"] > sp["publisher_tv_distance"]:
                reasons.append(f"publisher mix distance {row['publisher_tv_distance']:.2f}")
        row["flag"] = "; ".join(reasons)
        rows.append(row)
        if reasons:
            flagged.append((t, row["flag"]))
    table = pd.DataFrame(rows)
    has_post = bool((table["post_articles"] > 0).any()) if len(table) else False
    lines = [f"Splice diagnostics: {pre0.date()}..{(split - pd.Timedelta(days=1)).date()} (before) vs "
             f"{split.date()}..{post1.date()} (after)"]
    if not has_post:
        lines.append("VERDICT: the splice CANNOT be assessed - there is no news coverage after the split date "
                     "(Finnhub backfill has not run or returned nothing). News features are NaN from 2024-01-01.")
    elif flagged:
        lines.append(f"VERDICT: {len(flagged)} of {len(table)} tickers show a large shift at the join; treat cross-period "
                     "comparisons with care and rely on the provider-period standardised features (*_pstd).")
        lines += [f"  - {t}: {why}" for t, why in flagged]
    else:
        lines.append("VERDICT: no ticker exceeds the configured shift thresholds.")
    return table, "\n".join(lines)


def main() -> int:
    from app.features.news_pit import load_trading_calendar
    path = PROCESSED_NEWS_DIR / "news_processed.parquet"
    if not path.exists():
        print("Run the pipeline first (news_processed.parquet not found)")
        return 2
    arts = pd.read_parquet(path)
    arts = arts[arts["finbert_status"] == "OK"] if "finbert_status" in arts.columns else arts
    table, verdict = compute(arts, load_trading_calendar())
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(REPORTS_DIR / "splice_diagnostics.csv", index=False)
    (REPORTS_DIR / "splice_verdict.txt").write_text(verdict + "\n", encoding="utf-8")
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
