"""Step 1 of the news pipeline: raw FNSPID extract -> unified per-ticker news files + coverage report.

    python -m app.pipeline.build_fnspid_news

Writes data/raw/news/{TICKER}_news.parquet with the unified schema
    ticker, published_at (UTC), title, summary, source, url, provider="fnspid"
(+ source_domain, time_precision, section, topics, article_id), replacing the v1 files that contained
synthetic headlines. Reports articles per ticker per year and flags thin ticker-years.
"""
import hashlib
import json
import logging
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import RAW_NEWS_DIR, REPORTS_DIR
from app.data.providers.fnspid_provider import ALIAS_CANDIDATES, FNSPID_RAW_DIR, FnspidExtractor
from app.data.providers.gnews_provider import tag_topics
from app.features.news_enrich import enrich
from app.data.storage.parquet_store import ParquetStore
from app.features.news_pit import is_low_precision
from app.pipeline.harvest_news import universe_tickers

EXTRA_RAW_DIR = FNSPID_RAW_DIR.parent / "news_fnspid_u2"

logger = logging.getLogger("BuildFnspidNews")
UNIFIED_COLUMNS = ["article_hash", "article_id", "ticker", "published_at", "fetched_at", "title", "summary", "source",
                   "url", "provider", "provider_fetch_kind", "source_domain", "time_precision", "section", "topics",
                   "title_mentions_company", "relevance_weight", "article_type", "orig_symbol"]


def ascii_alpha_ratio(s: pd.Series) -> pd.Series:
    letters = s.str.count(r"[^\W\d_]")
    ascii_letters = s.str.count(r"[A-Za-z]")
    return (ascii_letters / letters.where(letters > 0)).fillna(0.0)


def normalize(raw: pd.DataFrame, tickers: List[str], cfg: Dict) -> Tuple[pd.DataFrame, Dict]:
    """Applies the spec's filters. Returns (unified articles for exact universe tickers, drop statistics)."""
    stats: Dict[str, int] = {"raw_rows": len(raw)}
    df = raw.copy()
    df["orig_symbol"] = df["symbol"].str.upper()
    alias_map = {a.upper(): t.upper() for t, al in (cfg.get("ticker_aliases") or {}).items() for a in al}
    df["ticker"] = df["orig_symbol"].map(lambda s: alias_map.get(s, s))
    stats["alias_rows_mapped"] = {a: int((df["orig_symbol"] == a).sum()) for a in alias_map}
    df = df[df["ticker"].isin(tickers)]
    stats["universe_rows"] = len(df)

    df["published_at"] = pd.to_datetime(df["date_raw"], errors="coerce", utc=True)
    df = df[df["published_at"].notna()]
    w0, w1 = pd.Timestamp(cfg["window"]["start"], tz="UTC"), pd.Timestamp(cfg["window"]["end"], tz="UTC") + pd.Timedelta(days=1)
    df = df[(df["published_at"] >= w0) & (df["published_at"] < w1)]
    stats["in_window"] = len(df)

    df["title"] = df["title"].fillna("").str.strip()
    df = df[df["title"] != ""]
    stats["non_empty_title"] = len(df)

    text = df["title"] + " " + df["summary"].fillna("")
    df = df[ascii_alpha_ratio(text) >= cfg["language"]["min_ascii_alpha_ratio"]]
    stats["english_only"] = len(df)

    df = df.drop_duplicates(subset=["ticker", "title", "published_at"], keep="first")
    stats["after_exact_dedup"] = len(df)

    df["url"] = df["url"].fillna("")
    df["source_domain"] = df["url"].map(lambda u: urlsplit(u).netloc.lower().replace("www.", "") if u else "")
    pub = df["publisher"].fillna("").str.strip()
    df["source"] = pub.where(pub != "", df["source_domain"])
    df["summary"] = df["summary"].fillna("").str.strip()
    df["provider"] = "fnspid"
    df["time_precision"] = is_low_precision(df["published_at"]).map({True: "LOW", False: "EXACT"})
    df["topics"] = df["title"].map(tag_topics)
    # article_hash = sha1(ticker + title + published_at) per the unified schema
    key = df["ticker"] + "|" + df["title"] + "|" + df["published_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df["article_hash"] = key.map(lambda k: hashlib.sha1(k.encode("utf-8")).hexdigest())
    df["article_id"] = df["article_hash"].str[:20]
    df["fetched_at"] = pd.Timestamp.now(tz="UTC")          # static dataset: time of this load
    df["provider_fetch_kind"] = "static"
    df = enrich(df.reset_index(drop=True), cfg)
    return df[UNIFIED_COLUMNS].sort_values(["ticker", "published_at"]).reset_index(drop=True), stats


def coverage_table(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    y = df.assign(year=df["published_at"].dt.year)
    pv = y.pivot_table(index="ticker", columns="year", values="article_id", aggfunc="count", fill_value=0)
    years = range(pd.Timestamp(cfg["window"]["start"]).year, pd.Timestamp(cfg["window"]["end"]).year + 1)
    return pv.reindex(columns=list(years), fill_value=0)


def run(cfg: Dict = None, resume: bool = True) -> Dict:
    """Builds data/raw/news/{TICKER}_news.parquet per ticker (resumable: finished tickers are skipped), then the report."""
    cfg = cfg or load_news_config()
    tickers = universe_tickers()
    extra = [EXTRA_RAW_DIR] + [d for d in (EXTRA_RAW_DIR.parent / f"news_fnspid_{s}" for s in ("u3", "u3_H", "u3_M", "u3b", "u3s")) if d.exists()]
    raw = pd.concat([FnspidExtractor(tickers).load_parts()] + [FnspidExtractor(tickers, raw_dir=d).load_parts() for d in extra],
                    ignore_index=True)
    if raw.empty:
        raise RuntimeError("No FNSPID extract found; run `python -m app.pipeline.fetch_fnspid` first")
    alias_map = {a.upper(): t.upper() for t, al in (cfg.get("ticker_aliases") or {}).items() for a in al}
    raw["_t"] = raw["symbol"].str.upper().map(lambda s: alias_map.get(s, s))
    totals: Dict[str, int] = {}
    alias_rows = {}
    for t in tickers:
        path = RAW_NEWS_DIR / f"{t}_news.parquet"
        if resume and path.exists() and "relevance_weight" in pd.read_parquet(path, columns=None).columns:
            continue
        sub = raw[raw["_t"] == t].drop(columns=["_t"])
        part, st = normalize(sub, [t], cfg)
        ParquetStore.write(part, path)                              # replaces v1 (synthetic) files
        for k, v in st.items():
            if isinstance(v, int):
                totals[k] = totals.get(k, 0) + v
        logger.info(f"{t}: {len(part):,} unique articles")
    frames = [pd.read_parquet(RAW_NEWS_DIR / f"{t}_news.parquet") for t in tickers if (RAW_NEWS_DIR / f"{t}_news.parquet").exists()]
    df = pd.concat(frames, ignore_index=True)
    alias_rows = {a: int((raw["symbol"].str.upper() == a).sum()) for a in alias_map}

    cov = coverage_table(df, cfg)
    thr = cfg["coverage"]["min_articles_per_ticker_year"]
    flagged = [(t, int(y), int(cov.loc[t, y])) for t in cov.index for y in cov.columns if cov.loc[t, y] < thr]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cov.to_csv(REPORTS_DIR / "news_coverage_fnspid.csv")
    prec = df.groupby(["section", "time_precision"]).size().unstack(fill_value=0)
    stats = {**totals, "alias_rows_mapped": alias_rows, "time_precision_by_section": prec.to_dict("index"),
             "title_mentions_company_share": {k: round(float(v), 3) for k, v in df.groupby("ticker")["title_mentions_company"].mean().items()},
             "flagged_ticker_years": flagged, "articles_per_ticker": df.groupby("ticker").size().to_dict()}
    (REPORTS_DIR / "news_fnspid_filter_stats.json").write_text(json.dumps(stats, indent=1, default=str))
    return {"articles": df, "coverage": cov, "stats": stats}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    res = run()
    pd.set_option("display.width", 250)
    print("\nARTICLES PER TICKER PER YEAR\n", res["coverage"].to_string())
    s = res["stats"]
    print("\nFILTER FUNNEL:", {k: v for k, v in s.items() if isinstance(v, int)})
    print("TIME PRECISION BY SECTION:", s["time_precision_by_section"])
    print("SHARE OF TITLES MENTIONING THE COMPANY/TICKER:", s["title_mentions_company_share"])
    print("ALIAS ROWS MAPPED TO UNIVERSE TICKERS:", s["alias_rows_mapped"])
    print(f"FLAGGED ticker-years (< {load_news_config()['coverage']['min_articles_per_ticker_year']} articles):",
          s["flagged_ticker_years"])
