"""Daily news features (v3): provider-agnostic, point-in-time safe, relevance-weighted.

Inputs are articles that already carry `effective_date` (see app/features/news_pit.py), a FinBERT
`sentiment` in [-1, 1] and a `relevance_weight`. Features are computed per (ticker, provider period):
the FNSPID period and the Finnhub period never share a baseline, a decay state or a z-score, so the
source change at the splice date cannot create an artificial jump inside any feature.

Definitions (w_i = relevance weight, s_i = FinBERT sentiment, day t = effective_date)
  news_count            raw number of articles effective on t   (0 on a covered day with no article)
  news_count_weighted   sum of w_i
  sent_mean             sum(w_i s_i) / sum(w_i)                  (NaN if no article)
  sent_decay            decayed sum(w s) / decayed sum(w), half-life H trading days; NaN if the decayed
                        weight mass < decay_min_mass
  sent_surprise         (sent_mean_t - mean_prev20) / std_prev20 using ONLY the 20 days before t,
                        needs >= min_baseline_days days with news in that window
  news_vol_surprise     same z-score for news_count_weighted
  sent_dispersion       relevance-weighted std of article sentiment within t; NaN if < min_articles_dispersion
  sent_momentum         sent_decay_t - sent_decay_{t-5}
  source_count          distinct source domains on t
  sent_earnings / sent_analyst_rating   weighted mean sentiment of that article type on t (NaN if none)
  *_pstd                expanding within-provider-period z-score (baseline = strictly earlier days of the
                        same ticker and provider only); the raw feature is always kept
NaN means "not enough information", never 0. Days outside provider coverage are NO_COVERAGE (all NaN).
No value on day t depends on any article whose effective_date is after t.
"""
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import DATASET_VERSION, MARKET_TIMEZONE

TOPIC_FEATURES = ["earnings", "merger", "technology", "macro", "financial_market"]
TOPIC_TO_FEATURE = {
    "earnings": "earnings", "mergers_and_acquisitions": "merger", "technology": "technology",
    "economy_macro": "macro", "financial_markets": "financial_market",
}
CORE_FEATURES = ["news_count", "news_count_weighted", "sent_mean", "sent_decay", "sent_surprise",
                 "news_vol_surprise", "sent_dispersion", "sent_momentum", "source_count",
                 "sent_earnings", "sent_analyst_rating"]
STANDARDIZED = ["news_count", "news_count_weighted", "sent_mean", "sent_decay", "sent_dispersion",
                "sent_momentum", "source_count", "sent_earnings", "sent_analyst_rating"]
COMPAT_FEATURES = ["unique_event_count", "positive_news_count", "negative_news_count", "neutral_news_count",
                   "avg_finbert_sentiment", "avg_av_sentiment", "sentiment_5d", "sentiment_20d", "av_sentiment_5d",
                   "av_sentiment_20d", "news_volume_5d", "news_volume_20d", "news_volume_zscore_20d", "earnings_count",
                   "merger_count", "technology_count", "macro_count", "financial_market_count"]
NEWS_FEATURE_COLUMNS = CORE_FEATURES + [f"{c}_pstd" for c in STANDARDIZED] + COMPAT_FEATURES + [
    "news_provider", "news_status", "news_quality", "news_cutoff_timestamp", "latest_news_timestamp", "dataset_version"]


def _rolling_prior_z(x: np.ndarray, window: int, min_obs: int) -> np.ndarray:
    """z-score of x[t] against x[t-window..t-1] (NaNs ignored); NaN if < min_obs prior observations or std == 0."""
    s = pd.Series(x)
    prior = s.shift(1).rolling(window, min_periods=min_obs)
    mu, sd = prior.mean(), prior.std()
    z = (s - mu) / sd.where(sd > 0)
    return z.values


def _expanding_prior_z(x: np.ndarray, min_obs: int) -> np.ndarray:
    """z-score of x[t] against ALL earlier observations of the same series (expanding, strictly prior)."""
    s = pd.Series(x)
    prior = s.shift(1).expanding(min_periods=min_obs)
    mu, sd = prior.mean(), prior.std()
    return ((s - mu) / sd.where(sd > 0)).values


def _decay(num: np.ndarray, den: np.ndarray, half_life: float, min_mass: float) -> np.ndarray:
    lam = 0.5 ** (1.0 / half_life)
    out = np.full(len(num), np.nan)
    a = b = 0.0
    for i in range(len(num)):
        a = lam * a + (num[i] if np.isfinite(num[i]) else 0.0)
        b = lam * b + (den[i] if np.isfinite(den[i]) else 0.0)
        if b >= min_mass:
            out[i] = a / b
    return out


def _period_frame(dates: pd.DatetimeIndex, arts: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Features for one ticker inside one provider period (dates = covered trading days of that period)."""
    f = cfg["features"]
    n = len(dates)
    d = pd.DataFrame(index=dates)
    if arts.empty:
        arts = arts.assign(effective_date=pd.NaT)
    a = arts.copy()
    a["w"] = a["relevance_weight"].astype(float)
    a["ws"] = a["w"] * a["sentiment"]
    a["ws2"] = a["w"] * a["sentiment"] ** 2
    a["w2"] = a["w"] ** 2
    g = a.groupby("effective_date")
    agg = g.agg(n=("w", "size"), w=("w", "sum"), w2=("w2", "sum"), ws=("ws", "sum"), ws2=("ws2", "sum"),
                src=("source_domain", "nunique"), last_pub=("published_at", "max"))
    agg = agg.reindex(dates)
    n_art = agg["n"].fillna(0).values.astype(float)
    w, w2, ws, ws2 = (agg[c].fillna(0.0).values.astype(float) for c in ("w", "w2", "ws", "ws2"))

    d["news_count"] = n_art
    d["news_count_weighted"] = w
    d["sent_mean"] = np.where(w > 0, ws / np.where(w > 0, w, 1.0), np.nan)
    d["source_count"] = agg["src"].fillna(0).values.astype(float)
    d["latest_news_timestamp"] = agg["last_pub"].values

    # weighted standard deviation (reliability weights), needs >= min_articles_dispersion articles
    denom = w - w2 / np.where(w > 0, w, 1.0)
    mu_w = np.where(w > 0, ws / np.where(w > 0, w, 1.0), 0.0)
    var = (ws2 - 2 * mu_w * ws + mu_w ** 2 * w) / np.where(denom > 1e-12, denom, np.nan)
    d["sent_dispersion"] = np.where(n_art >= f["min_articles_dispersion"], np.sqrt(np.maximum(var, 0.0)), np.nan)

    d["sent_decay"] = _decay(ws, w, f["decay_half_life_days"], f["decay_min_mass"])
    lag = f["momentum_lag_days"]
    d["sent_momentum"] = d["sent_decay"] - d["sent_decay"].shift(lag)

    # z-scores against the trailing window, strictly prior, gated on days WITH news in that window
    base_w, min_days = f["baseline_window_days"], f["min_baseline_days"]
    has_news = pd.Series((n_art > 0).astype(float))
    news_days_prior = has_news.shift(1).rolling(base_w, min_periods=1).sum().values
    z_sent = _rolling_prior_z(d["sent_mean"].values, base_w, min_days)
    # volume baseline uses every covered day (zeros included) but only once >= min_days prior news days exist
    z_vol = _rolling_prior_z(w, base_w, base_w // 2)
    z_vol_raw = _rolling_prior_z(n_art, base_w, base_w // 2)
    ok = news_days_prior >= min_days
    d["sent_surprise"] = np.where(np.isfinite(d["sent_mean"].values), z_sent, np.nan)
    d["news_vol_surprise"] = np.where(ok, z_vol, np.nan)
    d["news_volume_zscore_20d"] = np.where(ok, z_vol_raw, np.nan)

    # per article type
    for typ, col in (("earnings", "sent_earnings"), ("analyst_rating", "sent_analyst_rating")):
        sub = a[a["article_type"] == typ] if "article_type" in a.columns else a.iloc[0:0]
        if sub.empty:
            d[col] = np.nan
            d[f"{typ}_news_count"] = 0.0
            continue
        gs = sub.groupby("effective_date").agg(w=("w", "sum"), ws=("ws", "sum"), n=("w", "size")).reindex(dates)
        d[col] = np.where(gs["w"].fillna(0) > 0, gs["ws"] / gs["w"].where(gs["w"] > 0), np.nan)
        d[f"{typ}_news_count"] = gs["n"].fillna(0).values

    # compatibility columns (v2 names stay populated)
    d["avg_finbert_sentiment"] = d["sent_mean"]
    for win in (5, 20):
        sw = pd.Series(ws).rolling(win, min_periods=win).sum()
        ww = pd.Series(w).rolling(win, min_periods=win).sum()
        d[f"sentiment_{win}d"] = (sw / ww.where(ww > 0)).values
        d[f"news_volume_{win}d"] = pd.Series(n_art).rolling(win, min_periods=win).sum().values
        d[f"av_sentiment_{win}d"] = np.nan
    d["avg_av_sentiment"] = np.nan
    if "event_id" in a.columns:
        d["unique_event_count"] = a.groupby("effective_date")["event_id"].nunique().reindex(dates).fillna(0).values
    else:
        d["unique_event_count"] = n_art
    if "finbert_label" in a.columns:
        for lab, col in (("positive", "positive_news_count"), ("negative", "negative_news_count"),
                         ("neutral", "neutral_news_count")):
            d[col] = a[a["finbert_label"] == lab].groupby("effective_date").size().reindex(dates).fillna(0).values
    else:
        for col in ("positive_news_count", "negative_news_count", "neutral_news_count"):
            d[col] = np.nan
    topics = a["topics"].fillna("").astype(str) if "topics" in a.columns else pd.Series("", index=a.index)
    for t in TOPIC_FEATURES:
        names = [k for k, v in TOPIC_TO_FEATURE.items() if v == t]
        flag = topics.map(lambda s: any(x in s.split(";") for x in names)).astype(bool).values
        d[f"{t}_count"] = a.loc[flag].groupby("effective_date").size().reindex(dates).fillna(0).values
    return d


class NewsFeatureEngine:
    """Builds the daily news feature table for a universe."""

    @staticmethod
    def aggregate_daily_news(
        news_df: pd.DataFrame,
        market_dates_df: pd.DataFrame,
        coverage: Optional[Dict[str, Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]]]] = None,
        cfg: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """Args:
            news_df: articles with ticker, provider, effective_date, sentiment, relevance_weight, source_domain,
                     published_at and (optional) article_type, event_id, finbert_label, topics.
            market_dates_df: DataFrame[date, ticker] of trading days.
            coverage: {provider: {ticker: [(start, end), ...]}} inclusive covered date intervals. A provider
                      period date is covered only if it falls in one of its intervals; default = whole period.
        """
        cfg = cfg or load_news_config()
        periods = {p: (pd.Timestamp(v["start"]), pd.Timestamp(v["end"]) if v["end"] else pd.Timestamp.today().normalize())
                   for p, v in cfg["providers"].items()}
        m = market_dates_df[["date", "ticker"]].copy()
        m["date"] = pd.to_datetime(m["date"])
        m["ticker"] = m["ticker"].str.upper()
        arts = news_df.copy() if news_df is not None and not news_df.empty else pd.DataFrame(
            columns=["ticker", "provider", "effective_date", "sentiment", "relevance_weight", "source_domain",
                     "published_at", "article_type"])
        if not arts.empty:
            arts["ticker"] = arts["ticker"].str.upper()
            arts["effective_date"] = pd.to_datetime(arts["effective_date"])
            arts = arts[arts["effective_date"].notna() & arts["sentiment"].notna()]
            if "pit_safe" in arts.columns:
                arts = arts[arts["pit_safe"].astype(bool)]
            if "quality_status" in arts.columns:
                arts = arts[arts["quality_status"] != "FAIL"]
            if "is_duplicate" in arts.columns:
                arts = arts[~arts["is_duplicate"].astype(bool)]

        out_frames = []
        for ticker, mt in m.groupby("ticker"):
            all_dates = pd.DatetimeIndex(sorted(mt["date"].unique()))
            res = pd.DataFrame(index=all_dates)
            res["news_provider"] = None
            res["news_status"] = "NO_COVERAGE"
            pieces = []
            for prov, (p0, p1) in periods.items():
                in_p = all_dates[(all_dates >= p0) & (all_dates <= p1)]
                if len(in_p) == 0:
                    continue
                iv = (coverage or {}).get(prov, {}).get(ticker)
                if iv is None and coverage is not None and prov in coverage:
                    continue                      # provider has no coverage record for this ticker
                if iv is not None:
                    cov = np.zeros(len(in_p), dtype=bool)
                    for a0, a1 in iv:
                        cov |= (in_p >= pd.Timestamp(a0)) & (in_p <= pd.Timestamp(a1))
                    in_p = in_p[cov]
                if len(in_p) == 0:
                    continue
                sub = arts[(arts["ticker"] == ticker) & (arts["provider"] == prov)] if not arts.empty else arts
                sub = sub[(sub["effective_date"] >= in_p.min()) & (sub["effective_date"] <= in_p.max())] if len(sub) else sub
                fr = _period_frame(in_p, sub, cfg)
                fr["news_provider"] = prov
                # expanding within-period standardisation, strictly prior baseline
                mo = cfg["features"].get("pstd_min_obs", 60)
                if cfg.get("standardize_within_provider_period", True):
                    for c in STANDARDIZED:
                        fr[f"{c}_pstd"] = _expanding_prior_z(fr[c].values.astype(float), mo)
                fr["news_status"] = np.where(fr["news_count"] > 0, "NEWS", "NO_ARTICLES")
                pieces.append(fr)
            if pieces:
                res = pd.concat(pieces)
                res = res[~res.index.duplicated(keep="first")].reindex(all_dates)   # overlap: first provider in config order wins
                res["news_status"] = res["news_status"].fillna("NO_COVERAGE")
            res["ticker"] = ticker
            out_frames.append(res.rename_axis("date").reset_index())

        out = pd.concat(out_frames, ignore_index=True)
        for c in NEWS_FEATURE_COLUMNS:
            if c not in out.columns:
                out[c] = np.nan
        # data-quality label: ticker-years below the configured floor are flagged but values are kept
        thr = cfg["coverage"]["min_articles_per_ticker_year"]
        out["_year"] = out["date"].dt.year
        yearly = out.groupby(["ticker", "_year"])["news_count"].transform(lambda s: s.sum(min_count=1))
        out["news_quality"] = np.where(out["news_status"] == "NO_COVERAGE", "NO_COVERAGE",
                                       np.where(yearly < thr, "LOW_COVERAGE", "OK"))
        hh, mm = (int(x) for x in cfg["alignment"]["close_time"].split(":"))
        out["news_cutoff_timestamp"] = (out["date"] + pd.Timedelta(hours=hh, minutes=mm)).dt.tz_localize(
            MARKET_TIMEZONE).dt.tz_convert("UTC").dt.tz_localize(None)
        out["dataset_version"] = DATASET_VERSION
        out["date"] = out["date"].dt.date
        return out.drop(columns=["_year"]).sort_values(["date", "ticker"]).reset_index(drop=True)
