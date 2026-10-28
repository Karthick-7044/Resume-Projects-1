"""ProsusAI/FinBERT sentiment scoring with article-level caching (Section 11 of the design).

Backends
- hosted: Hugging Face Inference API (router.huggingface.co), requires HF_TOKEN.
- local:  transformers pipeline on CPU (model weights are downloaded once to the HF cache).
- auto:   hosted when HF_TOKEN is configured, otherwise local.

Guarantees
- Results are cached by article_id together with model name, backend, all three class
  probabilities, label, score = P(positive) - P(negative), timestamp and status.
- A failed article is marked finbert_status = FAILED/UNAVAILABLE; the pipeline never stops for
  one article and never copies provider (Alpha Vantage) sentiment into FinBERT fields.
"""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import requests

from app.config.settings import FINBERT_BACKEND, FINBERT_MODEL, HF_TOKEN, PROCESSED_NEWS_DIR
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

HF_INFERENCE_URL = f"https://router.huggingface.co/hf-inference/models/{FINBERT_MODEL}"
FINBERT_CACHE_PATH = PROCESSED_NEWS_DIR / "finbert_cache.parquet"
CACHE_COLUMNS = [
    "article_id", "finbert_positive", "finbert_negative", "finbert_neutral", "finbert_label",
    "finbert_score", "finbert_model", "finbert_backend", "finbert_scored_at", "finbert_status",
]


def build_text(title: str, summary: str = "", max_chars: int = 600) -> str:
    """Headline plus the start of the summary; FinBERT truncates to 128 tokens anyway."""
    title = (title or "").strip()
    summary = (summary or "").strip()
    text = f"{title}. {summary}" if summary else title
    return text[:max_chars]


def parse_finbert_output(output) -> Optional[Dict[str, float]]:
    """Normalizes pipeline / Inference API output into {'positive','negative','neutral'} probabilities."""
    if output is None:
        return None
    # Inference API returns [[{label, score}, ...]] for a single input; pipeline returns [{...}, ...]
    if isinstance(output, list) and output and isinstance(output[0], list):
        output = output[0]
    if not isinstance(output, list):
        return None
    probs = {}
    for entry in output:
        if not isinstance(entry, dict) or "label" not in entry or "score" not in entry:
            return None
        probs[str(entry["label"]).lower()] = float(entry["score"])
    if not {"positive", "negative", "neutral"} <= set(probs):
        return None
    total = sum(probs[k] for k in ("positive", "negative", "neutral"))
    if not np.isfinite(total) or total <= 0:
        return None
    return {k: probs[k] / total for k in ("positive", "negative", "neutral")}


def result_row(article_id: str, probs: Optional[Dict[str, float]], backend: str, status: str) -> Dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if probs is None:
        return {"article_id": article_id, "finbert_positive": np.nan, "finbert_negative": np.nan,
                "finbert_neutral": np.nan, "finbert_label": None, "finbert_score": np.nan,
                "finbert_model": FINBERT_MODEL, "finbert_backend": backend,
                "finbert_scored_at": now, "finbert_status": status}
    label = max(probs, key=probs.get)
    return {"article_id": article_id, "finbert_positive": probs["positive"],
            "finbert_negative": probs["negative"], "finbert_neutral": probs["neutral"],
            "finbert_label": label, "finbert_score": probs["positive"] - probs["negative"],
            "finbert_model": FINBERT_MODEL, "finbert_backend": backend,
            "finbert_scored_at": now, "finbert_status": status}


class FinBERTScorer:
    """Scores articles with FinBERT, reusing cached successful results."""

    def __init__(
        self,
        backend: str = FINBERT_BACKEND,
        hf_token: Optional[str] = HF_TOKEN,
        cache_path: Path = FINBERT_CACHE_PATH,
        batch_size: int = 32,
        hosted_caller: Optional[Callable[[str], object]] = None,
        local_pipeline=None,
    ):
        if backend == "auto":
            backend = "hosted" if hf_token else "local"
        self.backend = backend
        self.hf_token = hf_token
        self.cache_path = Path(cache_path)
        self.batch_size = batch_size
        self._hosted_caller = hosted_caller
        self._pipeline = local_pipeline

    # ------------------------------------------------------------------ cache
    def load_cache(self) -> pd.DataFrame:
        df = ParquetStore.read(self.cache_path)
        return df if not df.empty else pd.DataFrame(columns=CACHE_COLUMNS)

    def save_cache(self, df: pd.DataFrame):
        ParquetStore.write(df[CACHE_COLUMNS].reset_index(drop=True), self.cache_path)

    # ------------------------------------------------------------------ backends
    def _hosted_one(self, text: str) -> object:
        if self._hosted_caller is not None:
            return self._hosted_caller(text)
        if not self.hf_token:
            raise RuntimeError("HF_TOKEN not configured for hosted FinBERT")
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        for attempt in range(1, 4):
            resp = requests.post(HF_INFERENCE_URL, headers=headers,
                                 json={"inputs": text, "parameters": {"top_k": 3}}, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 503):  # rate limited / model loading
                time.sleep(2.0 * attempt)
                continue
            raise RuntimeError(f"HF inference HTTP {resp.status_code}: {resp.text[:200]}")
        raise RuntimeError("HF inference retries exhausted")

    def _local_pipeline(self):
        if self._pipeline is None:
            import torch
            from transformers import pipeline  # imported lazily: heavy dependency
            major_minor = tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2])
            if major_minor < (2, 6):
                # transformers>=5 refuses .bin checkpoints on torch<2.6 and ProsusAI/finbert ships only pytorch_model.bin:
                # go straight to the tensor-only loader (skips a slow, memory-hungry attempt that is certain to fail).
                self._pipeline = self._weights_only_pipeline()
            else:
                try:
                    self._pipeline = pipeline("text-classification", model=FINBERT_MODEL, top_k=None,
                                              truncation=True, max_length=128, device=-1)
                except (ValueError, OSError) as e:
                    logger.info(f"Standard FinBERT load failed ({str(e)[:120]}...); using weights-only loader")
                    self._pipeline = self._weights_only_pipeline()
        return self._pipeline

    @staticmethod
    def _weights_only_pipeline():
        """Loads the official main-branch weights with a LOW memory peak.

        First load converts pytorch_model.bin (tensor-only, memory-mapped) into a local safetensors file; later loads
        memory-map that file. The checkpoint is verified against the model's state dict (no silent partial load)."""
        import torch
        from huggingface_hub import hf_hub_download
        import gc
        from safetensors import safe_open
        from safetensors.torch import save_file
        from transformers import AutoConfig, AutoTokenizer, BertForSequenceClassification, pipeline
        from app.config.settings import DATA_DIR

        weights = hf_hub_download(FINBERT_MODEL, "pytorch_model.bin", revision="main")
        revision = Path(weights).parent.name
        st_dir = DATA_DIR / "models" / "finbert"
        st_path = st_dir / f"model_{revision[:12]}.safetensors"
        if not st_path.exists():                      # one-time conversion (legacy .bin cannot be memory-mapped)
            state = torch.load(weights, map_location="cpu", weights_only=True)
            st_dir.mkdir(parents=True, exist_ok=True)
            save_file({k: v.contiguous() for k, v in state.items()}, str(st_path), metadata={"format": "pt", "revision": revision})
            del state
            gc.collect()
        config = AutoConfig.from_pretrained(FINBERT_MODEL, revision="main")
        model = BertForSequenceClassification(config)
        target = model.state_dict()                   # references into the model: tensors are copied in ONE AT A TIME
        loaded = set()
        with safe_open(str(st_path), framework="pt", device="cpu") as f:
            for k in f.keys():
                if k in target and target[k].shape == f.get_tensor(k).shape:
                    target[k].copy_(f.get_tensor(k))
                    loaded.add(k)
        missing = [k for k in target if k not in loaded]
        unexpected = []
        # position_ids buffers are version-dependent; any other mismatch means the wrong checkpoint
        if [k for k in missing if "position_ids" not in k and "token_type_ids" not in k]:
            raise RuntimeError(f"FinBERT checkpoint mismatch: missing={missing}")
        model.eval()
        tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL, revision="main")
        return pipeline("text-classification", model=model, tokenizer=tokenizer, top_k=None,
                        truncation=True, max_length=128, device=-1)

    def _score_batch(self, texts: List[str]) -> List[Optional[Dict[str, float]]]:
        if self.backend == "hosted":
            out = []
            for t in texts:
                try:
                    out.append(parse_finbert_output(self._hosted_one(t)))
                except Exception as e:  # one failed article must not stop the pipeline
                    logger.warning(f"Hosted FinBERT failure: {e}")
                    out.append(None)
            return out
        raw = self._local_pipeline()(texts, batch_size=self.batch_size)
        return [parse_finbert_output(r) for r in raw]

    # ------------------------------------------------------------------ public
    def score_articles(self, articles: pd.DataFrame, progress_every: int = 2000,
                       checkpoint_every: int = 1000) -> pd.DataFrame:
        """Returns FinBERT results for every article_id in `articles` (columns: article_id, title, summary)."""
        if articles.empty:
            return pd.DataFrame(columns=CACHE_COLUMNS)
        cache = self.load_cache()
        ok_ids = set(cache.loc[cache["finbert_status"] == "OK", "article_id"])
        todo = articles.drop_duplicates("article_id")
        todo = todo[~todo["article_id"].isin(ok_ids)]
        logger.info(f"FinBERT[{self.backend}]: {len(ok_ids)} cached, {len(todo)} to score")

        new_rows: List[Dict] = []
        for start in range(0, len(todo), self.batch_size):
            chunk = todo.iloc[start:start + self.batch_size]
            texts = [build_text(t, s) for t, s in zip(chunk["title"], chunk.get("summary", [""] * len(chunk)))]
            try:
                probs_list = self._score_batch(texts)
            except Exception as e:
                logger.warning(f"FinBERT batch failed ({e}); marking {len(chunk)} articles UNAVAILABLE")
                probs_list = [None] * len(chunk)
            for aid, probs in zip(chunk["article_id"], probs_list):
                status = "OK" if probs is not None else ("FAILED" if self.backend == "hosted" else "UNAVAILABLE")
                new_rows.append(result_row(aid, probs, self.backend, status))
            if progress_every and (start // self.batch_size) % max(1, progress_every // self.batch_size) == 0:
                logger.info(f"FinBERT progress: {start + len(chunk)}/{len(todo)}")
            if len(new_rows) >= checkpoint_every:  # checkpoint so a crash loses at most one chunk
                cache = self._merge(cache, new_rows)
                self.save_cache(cache)
                new_rows = []

        if new_rows:
            cache = self._merge(cache, new_rows)
            self.save_cache(cache)
        return cache[cache["article_id"].isin(articles["article_id"])].reset_index(drop=True)

    @staticmethod
    def _merge(cache: pd.DataFrame, rows: List[Dict]) -> pd.DataFrame:
        new_df = pd.DataFrame(rows)
        return pd.concat([cache[~cache["article_id"].isin(new_df["article_id"])], new_df], ignore_index=True)
