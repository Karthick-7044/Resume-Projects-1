"""Completeness validation of the in-house news harvester against an independent reference source.

The Alpha Vantage archive already collected for the universe is used ONLY as a reference. For each
ticker and each day in the period both sources cover, the report measures:
  - story recall: share of reference headlines that have a matching harvester headline within +-1
    day (token Jaccard >= 0.4 after stop-word removal),
  - day recall: share of reference "busy days" (>= 3 reference articles) with at least one
    harvester article,
  - daily volume correlation (Spearman) between the two sources,
  - publisher overlap.
Because headlines from different syndication paths are rarely identical, story recall is a
conservative (lower-bound) estimate of completeness.
"""
import json
import re
from typing import Dict, List

import numpy as np
import pandas as pd

from app.config.settings import REPORTS_DIR
from app.data.providers.alphavantage_news_provider import AlphaVantageNewsProvider
from app.data.providers.gnews_provider import GoogleNewsHarvester

STOP = set("the a an of to in on for and or is are was were be as at by with from its it this that stock stocks shares "
           "share why how what will after before new says said could may amid vs".split())


def tokens(title: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z0-9$%.]+", str(title).lower()) if w not in STOP and len(w) > 1)


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def compare_ticker(ref: pd.DataFrame, hv: pd.DataFrame, start: str, end: str, thr: float = 0.4) -> Dict:
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    r = ref[(pd.to_datetime(ref["published_at"]) >= lo) & (pd.to_datetime(ref["published_at"]) <= hi)
            & (ref["av_relevance_score"].fillna(0) >= 0.5)].copy()
    h = hv[(pd.to_datetime(hv["published_at"]) >= lo - pd.Timedelta(days=1)) &
           (pd.to_datetime(hv["published_at"]) <= hi + pd.Timedelta(days=1))].copy()
    if r.empty or h.empty:
        return {"reference_articles": len(r), "harvester_articles": len(h)}
    r["day"] = pd.to_datetime(r["published_at"]).dt.normalize()
    h["day"] = pd.to_datetime(h["published_at"]).dt.normalize()
    h["tok"] = h["title"].map(tokens)
    by_day = {d: g["tok"].tolist() for d, g in h.groupby("day")}
    matched = 0
    for _, row in r.iterrows():
        t = tokens(row["title"])
        cands = []
        for dd in (-1, 0, 1):
            cands += by_day.get(row["day"] + pd.Timedelta(days=dd), [])
        if any(jaccard(t, c) >= thr for c in cands):
            matched += 1
    dc_r = r.groupby("day").size()
    dc_h = h.groupby("day").size()
    idx = pd.date_range(lo.normalize(), hi.normalize())
    a, b = dc_r.reindex(idx, fill_value=0), dc_h.reindex(idx, fill_value=0)
    busy = a[a >= 3].index
    pub_r, pub_h = set(r["publisher"].str.lower()), set(h["publisher"].str.lower())
    return {
        "reference_articles": int(len(r)), "harvester_articles": int(len(h)),
        "story_recall": matched / len(r),
        "busy_days": int(len(busy)), "busy_day_recall": float((b.reindex(busy) > 0).mean()) if len(busy) else None,
        "daily_volume_spearman": float(a.corr(b, method="spearman")),
        "publisher_overlap": len(pub_r & pub_h) / max(len(pub_r), 1),
    }


def run(tickers: List[str], start: str = "2022-03-01", end: str = "2025-12-31") -> Dict:
    av, gn = AlphaVantageNewsProvider(), GoogleNewsHarvester()
    out = {}
    for t in tickers:
        ref = av.load_articles(t)
        # Only compare inside the reference's own covered period
        cov = av.coverage_intervals(t)
        ref_end = min(pd.Timestamp(end), max((b for _, b in cov), default=pd.Timestamp(start)))
        out[t] = compare_ticker(ref, gn.load_articles(t), start, str(ref_end.date())) if not ref.empty else {}
    frame = pd.DataFrame(out).T
    summary = {"per_ticker": out,
               "mean": {c: float(pd.to_numeric(frame[c], errors="coerce").mean())
                        for c in ["story_recall", "busy_day_recall", "daily_volume_spearman", "publisher_overlap"] if c in frame}}
    (REPORTS_DIR / "news_source_comparison.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    from app.pipeline.harvest_news import universe_tickers
    res = run(universe_tickers())
    print(pd.DataFrame(res["per_ticker"]).T.round(3).to_string())
    print("MEAN", {k: round(v, 3) for k, v in res["mean"].items()})
