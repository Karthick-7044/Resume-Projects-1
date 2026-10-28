"""News Data Quality Assurance (v2): validation, PIT-safety and duplicate/event grouping."""
import re
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd

SENTIMENT_COLUMNS = ["av_ticker_sentiment", "overall_sentiment_score", "finbert_score", "tone", "sentiment"]
PROBABILITY_COLUMNS = ["p_pos", "p_neg", "p_neu"]


def normalize_title(title: str) -> str:
    """Lower-case alphanumeric title used for near-duplicate / event grouping."""
    t = re.sub(r"[^a-z0-9 ]+", " ", str(title or "").lower())
    return re.sub(r"\s+", " ", t).strip()


class NewsQA:
    """Deterministic validation of raw news articles (one row per article x ticker)."""

    @staticmethod
    def validate_articles(
        df: pd.DataFrame,
        universe: Optional[Iterable[str]] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Annotates articles with quality_status, quality_reason, pit_safe, is_duplicate, event_id."""
        if df.empty:
            return df, {"total_rows": 0, "overall_status": "FAIL", "reasons": ["Empty news dataset"],
                        "passed_count": 0, "warning_count": 0, "fail_count": 0}

        res = df.copy().reset_index(drop=True)
        res["quality_status"] = "PASS"
        res["quality_reason"] = ""
        res["pit_safe"] = True
        reasons = []
        now = pd.Timestamp(now or datetime.utcnow())

        def flag(mask: pd.Series, status: str, reason: str, pit_unsafe: bool = False):
            n = int(mask.sum())
            if n == 0:
                return
            reasons.append(f"{n} rows: {reason}")
            if status == "FAIL":
                res.loc[mask, "quality_status"] = "FAIL"
            else:
                res.loc[mask & (res["quality_status"] == "PASS"), "quality_status"] = "WARNING"
            res.loc[mask, "quality_reason"] = res.loc[mask, "quality_reason"] + "; " + reason
            if pit_unsafe:
                res.loc[mask, "pit_safe"] = False

        # 1. Headline
        flag(res["title"].isna() | (res["title"].astype(str).str.strip() == ""), "FAIL", "Missing title")

        # 2. Publication timestamp validity (unparseable timestamps are PIT-unsafe). Compare in naive UTC.
        pub = pd.to_datetime(res["published_at"], errors="coerce", utc=True).dt.tz_localize(None)
        flag(pub.isna(), "FAIL", "Invalid publication timestamp", pit_unsafe=True)

        # 3. Future publication timestamp
        flag(pub > now + pd.Timedelta(minutes=5), "FAIL", "Future publication timestamp", pit_unsafe=True)

        # 4. published_at must not be later than the fetch time
        fetch_col = "fetched_at" if "fetched_at" in res.columns else ("collected_at" if "collected_at" in res.columns else None)
        if fetch_col:
            col = pd.to_datetime(res[fetch_col], errors="coerce", utc=True).dt.tz_localize(None)
            flag(pub.notna() & col.notna() & (pub > col), "FAIL", "Published after fetch time", pit_unsafe=True)

        # 4b. Duplicate article_hash (unified schema): keep the first occurrence, flag the rest
        if "article_hash" in res.columns:
            flag(res.duplicated(subset=["article_hash"], keep="first"), "FAIL", "Duplicate article_hash")

        # 4c. Alignment: effective_date must not precede the publication session, and an article may map to
        #     exactly one effective date
        if "effective_date" in res.columns:
            eff = pd.to_datetime(res["effective_date"], errors="coerce")
            pub_et_date = (pd.to_datetime(res["published_at"], errors="coerce", utc=True)
                           .dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize())
            flag(eff.notna() & pub_et_date.notna() & (eff < pub_et_date), "FAIL",
                 "effective_date earlier than the published date", pit_unsafe=True)
            key = "article_hash" if "article_hash" in res.columns else "article_id"
            multi = res.groupby(key)["effective_date"].transform("nunique") > 1
            flag(multi, "FAIL", "Article assigned to more than one effective_date", pit_unsafe=True)

        # 5. Ticker in configured universe
        if universe is not None:
            uni = {u.upper() for u in universe}
            flag(~res["ticker"].astype(str).str.upper().isin(uni), "FAIL", "Ticker not in universe")

        # 6. URL / source metadata
        if "url" in res.columns:
            flag(res["url"].isna() | (res["url"].astype(str).str.strip() == ""), "WARNING", "Missing URL")

        # 7. Sentiment ranges
        for c in SENTIMENT_COLUMNS:
            if c in res.columns:
                v = pd.to_numeric(res[c], errors="coerce")
                flag(v.notna() & ((v < -1.0) | (v > 1.0)), "FAIL", f"{c} outside [-1, 1]")
        for c in PROBABILITY_COLUMNS:
            if c in res.columns:
                v = pd.to_numeric(res[c], errors="coerce")
                flag(v.notna() & ((v < 0.0) | (v > 1.0)), "FAIL", f"{c} outside [0, 1]")

        # 8. Exact duplicates (same article_id for the same ticker): keep first, mark the rest
        dup = res.duplicated(subset=["article_id", "ticker"], keep="first")
        res["is_duplicate"] = dup
        flag(dup, "WARNING", "Duplicate article_id")

        # 9. Near-duplicate event grouping: same ticker, same normalized title, same UTC day
        res["_norm_title"] = res["title"].map(normalize_title)
        res["_day"] = pub.dt.date
        res["event_id"] = (res.groupby(["ticker", "_norm_title", "_day"], dropna=False).ngroup()).astype("int64")
        res = res.drop(columns=["_norm_title", "_day"])
        res["quality_reason"] = res["quality_reason"].str.lstrip("; ")

        passed = int((res["quality_status"] == "PASS").sum())
        warning = int((res["quality_status"] == "WARNING").sum())
        fail = int((res["quality_status"] == "FAIL").sum())
        overall = "PASS"
        if fail > 0:
            overall = "FAIL" if fail > len(res) * 0.1 else "WARNING"
        elif warning > 0:
            overall = "WARNING"

        summary = {
            "total_rows": len(res),
            "overall_status": overall,
            "reasons": reasons or ["All news validations passed"],
            "passed_count": passed,
            "warning_count": warning,
            "fail_count": fail,
            "pit_unsafe_count": int((~res["pit_safe"]).sum()),
            "duplicate_count": int(res["is_duplicate"].sum()),
            "unique_events": int(res["event_id"].nunique()),
            "min_date": str(pub.min().date()) if pub.notna().any() else None,
            "max_date": str(pub.max().date()) if pub.notna().any() else None,
        }
        return res, summary

    # ------------------------------------------------------------------ feature-level QA
    @staticmethod
    def feature_nan_report(features: pd.DataFrame, feature_cols=None,
                           group_cols=("ticker", "news_provider")) -> pd.DataFrame:
        """NaN rate of every news feature per ticker per provider (covered days only), plus coverage share."""
        from app.features.news_features import CORE_FEATURES
        cols = [c for c in (feature_cols or CORE_FEATURES) if c in features.columns]
        covered = features[features["news_status"] != "NO_COVERAGE"]
        rows = []
        for keys, g in covered.groupby(list(group_cols), dropna=False):
            for c in cols:
                rows.append({**dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,))), "feature": c,
                             "rows": len(g), "nan_rate": float(g[c].isna().mean())})
        out = pd.DataFrame(rows)
        if not out.empty:
            total = features.groupby("ticker").size()
            cov = covered.groupby("ticker").size()
            out["ticker_coverage_share"] = out["ticker"].map((cov / total).fillna(0.0))
        return out

    @staticmethod
    def leakage_check(articles: pd.DataFrame, market_dates: pd.DataFrame, build, cutoffs) -> list:
        """Features on date t must not change when every article with effective_date > t is removed.

        `build(articles, market_dates)` must return the feature table. Returns a list of violations
        (empty = no look-ahead found).
        """
        full = build(articles, market_dates).copy()
        full["date"] = pd.to_datetime(full["date"])
        violations = []
        for cut in cutoffs:
            t = pd.Timestamp(cut)
            part = articles[pd.to_datetime(articles["effective_date"]) <= t]
            trunc = build(part, market_dates).copy()
            trunc["date"] = pd.to_datetime(trunc["date"])
            a = full[full["date"] <= t].set_index(["date", "ticker"]).select_dtypes("number")
            b = trunc[trunc["date"] <= t].set_index(["date", "ticker"]).select_dtypes("number")
            bad = ~np.isclose(a.values.astype(float), b.reindex(a.index)[a.columns].values.astype(float),
                              rtol=1e-9, atol=1e-12, equal_nan=True)
            if bad.any():
                cols = sorted(set(a.columns[np.where(bad.any(axis=0))[0]]))
                violations.append({"cutoff": str(t.date()), "columns": cols})
        return violations
