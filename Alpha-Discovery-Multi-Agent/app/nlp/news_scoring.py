"""One FinBERT scoring path for every news provider.

    python -m app.nlp.news_scoring [--max-minutes 25]

- Model: ProsusAI/finbert, weights loaded tensor-only from the official `main` revision (the hash is
  recorded in data/processed/news/finbert_meta.json together with library versions and the seed).
- Text: title (+ summary truncated to config scoring.summary_chars, default 0 = title only), then truncated
  to the model's max length. Identical texts (many multi-stock headlines) are scored once.
- Caches (reruns are free; interrupted runs resume):
    data/processed/news/finbert_text_cache.parquet   text_hash -> p_pos, p_neg, p_neu
    data/processed/news/articles_scored.parquet      article_hash -> p_pos, p_neg, p_neu, sentiment, label
- Provider-supplied sentiment is never used here; it may only be kept as a comparison column.
"""
import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.config.news_config import load_news_config
from app.config.settings import DATA_DIR, PROCESSED_NEWS_DIR, RAW_NEWS_DIR

logger = logging.getLogger("NewsScoring")
TEXT_CACHE = PROCESSED_NEWS_DIR / "finbert_text_cache.parquet"
ARTICLES_SCORED = PROCESSED_NEWS_DIR / "articles_scored.parquet"
META_PATH = PROCESSED_NEWS_DIR / "finbert_meta.json"
FINNHUB_DIR = DATA_DIR / "raw" / "news_finnhub"


def load_unified(tickers: List[str]) -> pd.DataFrame:
    """All providers' unified-schema articles for the universe (FNSPID raw + Finnhub append-only files)."""
    frames = []
    for t in tickers:
        for d in (RAW_NEWS_DIR, FINNHUB_DIR, Path(RAW_NEWS_DIR) / "gnews_recent"):
            p = Path(d) / f"{t}_news.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                if "provider" in df.columns and df["provider"].isin(["fnspid", "finnhub", "google_news_rss"]).all():
                    frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_text(title: str, summary: str, summary_chars: int) -> str:
    title = (title or "").strip()
    if summary_chars and summary and summary.strip():
        return f"{title}. {summary.strip()[:summary_chars]}"
    return title


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def _revision() -> Optional[str]:
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache("ProsusAI/finbert", "pytorch_model.bin")
        return Path(path).parent.name if isinstance(path, str) else None
    except Exception:  # noqa: BLE001 - metadata is best effort, never blocks scoring
        return None


def _load_model():
    from app.nlp.finbert import FinBERTScorer
    pipe = FinBERTScorer(backend="local")._local_pipeline()
    return pipe.model.eval(), pipe.tokenizer


def score_texts(max_minutes: Optional[float] = None, cfg: Optional[Dict] = None) -> int:
    """Scores every not-yet-cached unique text of the current unified articles. Returns number scored."""
    import torch
    cfg = cfg or load_news_config()
    sc = cfg["scoring"]
    from app.pipeline.harvest_news import universe_tickers
    arts = load_unified(universe_tickers())
    if arts.empty:
        raise RuntimeError("No unified articles found; build the provider files first")
    texts = pd.DataFrame({"text": [build_text(t, s, sc["summary_chars"]) for t, s in zip(arts["title"], arts.get("summary", ""))]})
    texts["text_hash"] = texts["text"].map(text_hash)
    uniq = texts.drop_duplicates("text_hash")
    cache = pd.read_parquet(TEXT_CACHE) if TEXT_CACHE.exists() else pd.DataFrame(
        columns=["text_hash", "p_pos", "p_neg", "p_neu"])
    todo = uniq[~uniq["text_hash"].isin(set(cache["text_hash"]))].copy()
    logger.info(f"{len(uniq):,} unique texts, {len(cache):,} cached, {len(todo):,} to score")
    if todo.empty:
        return 0

    torch.manual_seed(sc["seed"])
    np.random.seed(sc["seed"])
    torch.set_num_threads(int(os.getenv("NEWS_SCORING_THREADS", os.cpu_count() or 4)))   # fewer threads = less memory pressure
    model, tok = _load_model()
    labels = [model.config.id2label[i].lower() for i in range(model.config.num_labels)]
    ip, ineg, ineu = labels.index("positive"), labels.index("negative"), labels.index("neutral")
    todo = todo.assign(n=todo["text"].str.len()).sort_values("n")        # similar lengths -> little padding

    t0, scored, chunk_rows = time.time(), 0, []
    bs, chunk = int(os.getenv("NEWS_SCORING_BATCH", sc["batch_size"] * 2)), int(os.getenv("NEWS_SCORING_CHUNK", 2048))
    texts_list, hashes = todo["text"].tolist(), todo["text_hash"].tolist()
    for start in range(0, len(texts_list), bs):
        enc = tok(texts_list[start:start + bs], padding=True, truncation=True, max_length=sc["max_length"], return_tensors="pt")
        with torch.inference_mode():
            p = torch.softmax(model(**enc).logits, dim=-1).numpy()
        for h, row in zip(hashes[start:start + bs], p):
            chunk_rows.append({"text_hash": h, "p_pos": float(row[ip]), "p_neg": float(row[ineg]), "p_neu": float(row[ineu])})
        scored += len(p)
        done_chunk = len(chunk_rows) >= chunk
        out_of_time = max_minutes is not None and (time.time() - t0) / 60 >= max_minutes
        if done_chunk or out_of_time or start + bs >= len(texts_list):
            cache = pd.concat([cache, pd.DataFrame(chunk_rows)], ignore_index=True).drop_duplicates("text_hash")
            cache.to_parquet(TEXT_CACHE, index=False)
            chunk_rows = []
            rate = scored / max((time.time() - t0) / 60, 1e-9)
            logger.info(f"scored {scored:,}/{len(todo):,} ({rate:,.0f}/min); cache {len(cache):,}")
            _write_meta(sc, len(cache))
        if out_of_time:
            logger.info("time budget reached; progress saved (rerun to resume)")
            break
    return scored


def _write_meta(sc: Dict, n_cached: int):
    import torch
    import transformers
    meta = {"model": sc["model"], "revision": _revision(), "revision_source": "huggingface cache snapshot of pytorch_model.bin (main)",
            "backend": "local-cpu", "seed": sc["seed"], "max_length": sc["max_length"], "batch_size": sc["batch_size"],
            "summary_chars": sc["summary_chars"], "torch": torch.__version__, "transformers": transformers.__version__,
            "texts_cached": n_cached, "updated_at": datetime.now(timezone.utc).isoformat()}
    META_PATH.write_text(json.dumps(meta, indent=2))


def attach_scores(arts: pd.DataFrame, cfg: Optional[Dict] = None) -> pd.DataFrame:
    """Adds p_pos/p_neg/p_neu/sentiment/finbert_label/finbert_status (+ model/revision) from the cache."""
    cfg = cfg or load_news_config()
    sc = cfg["scoring"]
    out = arts.copy()
    out["text_hash"] = [text_hash(build_text(t, s, sc["summary_chars"])) for t, s in zip(out["title"], out.get("summary", ""))]
    cache = pd.read_parquet(TEXT_CACHE) if TEXT_CACHE.exists() else pd.DataFrame(columns=["text_hash", "p_pos", "p_neg", "p_neu"])
    out = out.merge(cache, on="text_hash", how="left")
    out["sentiment"] = out["p_pos"] - out["p_neg"]
    lab = np.array(["positive", "negative", "neutral"])
    out["finbert_label"] = np.where(out["p_pos"].isna(), None, lab[np.nanargmax(out[["p_pos", "p_neg", "p_neu"]].fillna(0).values, axis=1)])
    out["finbert_status"] = np.where(out["p_pos"].notna(), "OK", "NOT_SCORED")
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    out["finbert_model"] = sc["model"]
    out["finbert_revision"] = meta.get("revision")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=None, help="stop cleanly after this many minutes (resumable)")
    a = ap.parse_args()
    n = score_texts(a.max_minutes)
    from app.pipeline.harvest_news import universe_tickers
    arts = attach_scores(load_unified(universe_tickers()))
    ParquetCols = ["article_hash", "ticker", "provider", "p_pos", "p_neg", "p_neu", "sentiment", "finbert_label",
                   "finbert_status", "finbert_model", "finbert_revision"]
    arts[ParquetCols].to_parquet(ARTICLES_SCORED, index=False)
    print(f"scored this run: {n:,}; articles with scores: {(arts['finbert_status'] == 'OK').sum():,}/{len(arts):,}")
