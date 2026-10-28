"""FinBERT validation on the Financial PhraseBank (Malo et al., 2014).

    python -m app.nlp.phrasebank_eval

Downloads the public FinancialPhraseBank-v1.0 archive once (data/raw/phrasebank), scores every sentence with the SAME
local FinBERT pipeline used for news scoring, and reports accuracy, macro-F1 and per-class F1 for each annotator-
agreement subset. Caveat (reported with the numbers): ProsusAI/finbert was fine-tuned on a split of this corpus, so the
scores are an implementation sanity check (correct weights, labels and tokenisation), not an independent
out-of-sample estimate of FinBERT accuracy on news headlines.
"""
import io
import json
import logging
import zipfile

import numpy as np
import pandas as pd
import requests
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from app.config.settings import ALPHA_RESULTS_DIR, RAW_DATA_DIR
from app.nlp.finbert import FinBERTScorer, parse_finbert_output

logger = logging.getLogger("PhraseBank")
PB_DIR = RAW_DATA_DIR / "phrasebank"
PB_URL = "https://huggingface.co/datasets/takala/financial_phrasebank/resolve/main/data/FinancialPhraseBank-v1.0.zip"
SUBSETS = ["AllAgree", "75Agree", "66Agree", "50Agree"]
LABELS = ["positive", "negative", "neutral"]


def load_subsets() -> dict:
    PB_DIR.mkdir(parents=True, exist_ok=True)
    p = PB_DIR / "FinancialPhraseBank-v1.0.zip"
    if not p.exists():
        r = requests.get(PB_URL, timeout=120)
        r.raise_for_status()
        p.write_bytes(r.content)
    out = {}
    with zipfile.ZipFile(p) as z:
        for s in SUBSETS:
            name = next(n for n in z.namelist() if n.endswith(f"Sentences_{s}.txt"))
            rows = []
            for ln in z.read(name).decode("latin-1").splitlines():
                if "@" in ln:
                    text, lab = ln.rsplit("@", 1)
                    rows.append((text.strip(), lab.strip().lower()))
            out[s] = pd.DataFrame(rows, columns=["text", "label"])
    return out


def run() -> dict:
    subsets = load_subsets()
    pipe = FinBERTScorer(backend="local")._local_pipeline()
    allsent = subsets["50Agree"]              # superset of every other subset
    uniq = allsent["text"].drop_duplicates().tolist()
    logger.info(f"scoring {len(uniq)} sentences with local FinBERT")
    preds = {}
    for i in range(0, len(uniq), 64):
        batch = uniq[i:i + 64]
        for t, r in zip(batch, pipe(batch, batch_size=32)):
            p = parse_finbert_output(r)
            preds[t] = max(p, key=p.get) if p else None
    res = {"source": PB_URL, "caveat": "ProsusAI/finbert was fine-tuned on Financial PhraseBank; sanity check, not independent",
           "subsets": {}}
    for s, df in subsets.items():
        y, yhat = df["label"].values, df["text"].map(preds).values
        ok = pd.notna(yhat)
        res["subsets"][s] = {
            "n": int(len(df)), "accuracy": float(accuracy_score(y[ok], yhat[ok])),
            "macro_f1": float(f1_score(y[ok], yhat[ok], average="macro", labels=LABELS)),
            "weighted_f1": float(f1_score(y[ok], yhat[ok], average="weighted", labels=LABELS)),
            "per_class": {k: {m: float(v[m]) for m in ("precision", "recall", "f1-score")}
                          for k, v in classification_report(y[ok], yhat[ok], labels=LABELS, output_dict=True).items() if k in LABELS},
            "confusion_rows_true_cols_pred": {"labels": LABELS, "matrix": confusion_matrix(y[ok], yhat[ok], labels=LABELS).tolist()},
            "majority_class_accuracy": float(pd.Series(y).value_counts(normalize=True).iloc[0]),
        }
    (ALPHA_RESULTS_DIR / "finbert_phrasebank_eval.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    r = run()
    for s, v in r["subsets"].items():
        print(f"{s:9s} n={v['n']:5d} accuracy={v['accuracy']:.3f} macroF1={v['macro_f1']:.3f} (majority {v['majority_class_accuracy']:.3f})")
