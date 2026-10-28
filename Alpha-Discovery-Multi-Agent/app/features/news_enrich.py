"""Shared article enrichment used by every provider: relevance weight and keyword article type.

Relevance weight: mention_weight (default 1.0) if the company name/alias or the ticker appears in the
title, other_weight (default 0.3) otherwise. Article type: config-driven keyword lists; the first type
(in config order) with a matching keyword wins, else "other". Both are transparent and auditable.
"""
import re
from functools import lru_cache
from io import StringIO
from typing import Dict, List, Optional

import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import COMPANY_ALIASES_FILE, UNIVERSE_FILE

ARTICLE_TYPES_FALLBACK = "other"


@lru_cache(maxsize=1)
def name_terms() -> Dict[str, List[str]]:
    """ticker -> company-name terms (universe company_name, its short form, and configured aliases)."""
    terms: Dict[str, List[str]] = {}
    if UNIVERSE_FILE.exists():
        lines = [l for l in UNIVERSE_FILE.read_text().splitlines() if not l.strip().startswith("#")]
        uni = pd.read_csv(StringIO("\n".join(lines)))
        for _, r in uni.iterrows():
            full = str(r["company_name"])
            short = re.sub(r"\b(inc|corp|corporation|co|company|platforms|holdings|ltd|plc)\b\.?,?", "", full, flags=re.I).strip(" ,.&")
            terms[str(r["ticker"]).upper()] = [t for t in {full, short} if len(t) >= 3]
    if COMPANY_ALIASES_FILE.exists():
        al = pd.read_csv(COMPANY_ALIASES_FILE)
        for _, r in al.iterrows():
            t = str(r["ticker"]).upper()
            extra = [a.strip() for a in str(r.get("aliases", "")).split(";") if len(a.strip()) >= 3]
            terms[t] = list(dict.fromkeys(terms.get(t, []) + extra))
    return terms


@lru_cache(maxsize=512)
def _mention_rx(ticker: str):
    parts = [re.escape(t) for t in name_terms().get(ticker, [])]
    if len(ticker) >= 2:            # one-letter tickers (V) are far too ambiguous to match on their own
        parts.append(rf"\(?{re.escape(ticker)}\)?")
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9])", re.I if len(ticker) < 2 else 0) if parts else None


def mentions_company(title: str, ticker: str) -> bool:
    t = (title or "")
    ticker = ticker.upper()
    names = [re.escape(x) for x in name_terms().get(ticker, [])]
    if names and re.search(r"(?<![A-Za-z0-9])(?:" + "|".join(names) + r")(?![A-Za-z0-9])", t, re.I):
        return True
    return len(ticker) >= 2 and re.search(rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])", t) is not None


@lru_cache(maxsize=8)
def _type_rx(key: str):
    cfg = load_news_config()["article_types"]
    return [(name, re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(k) for k in kws) + r")(?![A-Za-z0-9])", re.I))
            for name, kws in cfg.items() if kws]


def article_type(title: str, cfg: Optional[dict] = None) -> str:
    for name, rx in _type_rx(str(sorted(load_news_config()["article_types"].items()))):
        if rx.search(title or ""):
            return name
    return ARTICLE_TYPES_FALLBACK


def enrich(df: pd.DataFrame, cfg: Optional[dict] = None) -> pd.DataFrame:
    """Adds title_mentions_company, relevance_weight and article_type (vectorised; identical rules to the row-wise helpers)."""
    cfg = cfg or load_news_config()
    out = df.copy()
    titles = out["title"].fillna("").astype(str)
    mention = pd.Series(False, index=out.index)
    for ticker, idx in out.groupby("ticker").groups.items():
        t = ticker.upper()
        sub = titles.loc[idx]
        hit = pd.Series(False, index=idx)
        names = [re.escape(x) for x in name_terms().get(t, [])]
        if names:
            hit |= sub.str.contains(r"(?<![A-Za-z0-9])(?:" + "|".join(names) + r")(?![A-Za-z0-9])", case=False, regex=True)
        if len(t) >= 2:
            hit |= sub.str.contains(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", case=True, regex=True)
        mention.loc[idx] = hit
    out["title_mentions_company"] = mention.values
    out["relevance_weight"] = out["title_mentions_company"].map(
        {True: cfg["relevance"]["mention_weight"], False: cfg["relevance"]["other_weight"]}).astype(float)
    typ = pd.Series(ARTICLE_TYPES_FALLBACK, index=out.index)
    for name, rx in reversed(_type_rx(str(sorted(load_news_config()["article_types"].items())))):   # first listed type wins
        typ[titles.str.contains(rx.pattern, case=False, regex=True)] = name
    out["article_type"] = typ.values
    return out
