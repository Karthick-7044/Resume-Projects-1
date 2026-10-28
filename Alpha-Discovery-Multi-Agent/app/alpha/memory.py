"""Persistent research memory: every attempted hypothesis/formula with its full lineage.

Stored in DuckDB (table alpha_experiments) and as one JSON file per experiment. Memory prevents
re-testing the same formula, feeds lessons back to the Context Builder and preserves the complete
multiple-testing record needed to interpret final results honestly.
"""
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.config.settings import ALPHA_EXPERIMENTS_DIR, DATASET_VERSION
from app.data.storage.duckdb_manager import DuckDBManager

COLUMNS = ["experiment_id", "run_id", "config", "iteration", "parent_id", "hypothesis_id", "hypothesis_title",
           "rationale", "domains", "formula", "is_valid", "validation_errors", "verdict", "score",
           "train_rank_ic", "train_ic_tstat", "train_sharpe", "valid_rank_ic", "valid_sharpe",
           "annual_turnover", "dominant_domain", "critique", "revision_action", "source", "dataset_version",
           "created_at", "detail_json"]


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if k != "_series"}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) or np.isinf(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return o


class ResearchMemory:
    def __init__(self, duckdb_mgr: Optional[DuckDBManager] = None, persist: bool = True):
        self.db = duckdb_mgr or DuckDBManager()
        self.persist = persist
        self.records: List[Dict] = []
        if persist:
            with self.db.get_connection() as con:
                con.execute("""CREATE TABLE IF NOT EXISTS alpha_experiments (
                    experiment_id VARCHAR PRIMARY KEY, run_id VARCHAR, config VARCHAR, iteration BIGINT,
                    parent_id VARCHAR, hypothesis_id VARCHAR, hypothesis_title VARCHAR, rationale VARCHAR,
                    domains VARCHAR, formula VARCHAR, is_valid BOOLEAN, validation_errors VARCHAR,
                    verdict VARCHAR, score DOUBLE, train_rank_ic DOUBLE, train_ic_tstat DOUBLE,
                    train_sharpe DOUBLE, valid_rank_ic DOUBLE, valid_sharpe DOUBLE, annual_turnover DOUBLE,
                    dominant_domain VARCHAR, critique VARCHAR, revision_action VARCHAR, source VARCHAR,
                    dataset_version VARCHAR, created_at TIMESTAMP, detail_json VARCHAR)""")

    def clear_run(self, run_id: str):
        self.records = [r for r in self.records if r["run_id"] != run_id]
        if self.persist:
            try:
                self.db.execute("DELETE FROM alpha_experiments WHERE run_id = ?", [run_id])
            except Exception:  # noqa: BLE001 - a new run_id has nothing to delete; a busy database must not stop the run
                pass

    def record(self, run_id: str, config: str, iteration: int, hypothesis: Dict, formula: str,
               validation: Dict, metrics: Optional[Dict], attribution: Optional[Dict], critique: Optional[Dict],
               parent_id: Optional[str] = None, revision_action: Optional[str] = None, source: str = "offline") -> Dict:
        tr = (metrics or {}).get("train", {})
        va = (metrics or {}).get("valid", {})
        rec = {
            "experiment_id": f"exp_{uuid.uuid4().hex[:10]}", "run_id": run_id, "config": config,
            "iteration": iteration, "parent_id": parent_id, "hypothesis_id": hypothesis.get("id"),
            "hypothesis_title": hypothesis.get("title"), "rationale": hypothesis.get("rationale"),
            "domains": ",".join(validation.get("domains") or hypothesis.get("domains", [])), "formula": formula,
            "is_valid": bool(validation.get("valid")), "validation_errors": "; ".join(validation.get("errors", [])),
            "verdict": (critique or {}).get("verdict", "INVALID"), "score": (critique or {}).get("score"),
            "train_rank_ic": tr.get("rank_ic", {}).get("mean"), "train_ic_tstat": tr.get("rank_ic", {}).get("t_stat"),
            "train_sharpe": tr.get("sharpe"), "valid_rank_ic": va.get("rank_ic", {}).get("mean"),
            "valid_sharpe": va.get("sharpe"), "annual_turnover": tr.get("annual_turnover"),
            "dominant_domain": (attribution or {}).get("dominant_domain"),
            "critique": (critique or {}).get("summary", "; ".join(validation.get("errors", []))),
            "revision_action": revision_action, "source": source, "dataset_version": DATASET_VERSION,
            "created_at": datetime.utcnow(),
        }
        detail = _clean({"hypothesis": hypothesis, "validation": validation, "metrics": metrics,
                         "attribution": attribution, "critique": critique})
        rec = _clean(rec)
        rec["created_at"] = datetime.utcnow()
        rec["detail_json"] = json.dumps(detail)
        self.records.append(rec)
        if self.persist:
            try:      # the JSON lineage file below is the full record; the DuckDB copy is best-effort (file may be locked)
                self.db.upsert_dataframe("alpha_experiments", pd.DataFrame([rec])[COLUMNS], ["experiment_id"])
            except Exception as e:  # noqa: BLE001 - never lose a research run because the database is busy
                import logging
                logging.getLogger(__name__).warning(f"DuckDB busy, experiment kept in JSON only: {e}")
            (ALPHA_EXPERIMENTS_DIR / f"{rec['experiment_id']}.json").write_text(
                json.dumps({**{k: v for k, v in rec.items() if k not in ("detail_json", "created_at")},
                            "created_at": rec["created_at"].isoformat(), "detail": detail}, indent=2))
        return rec

    # ------------------------------------------------------------------ retrieval
    def for_run(self, run_id: str) -> List[Dict]:
        return [r for r in self.records if r["run_id"] == run_id]

    def formula_seen(self, run_id: str, formula: str) -> bool:
        norm = formula.replace(" ", "")
        return any(r["formula"].replace(" ", "") == norm for r in self.for_run(run_id))

    def summary(self, run_id: str, top: int = 5) -> Dict:
        """Compact memory view for the Context Builder (never contains test-period results)."""
        recs = self.for_run(run_id)
        acc = sorted([r for r in recs if r["verdict"] == "ACCEPT"], key=lambda r: -(r["score"] or -9))[:top]
        rej = [r for r in recs if r["verdict"] in ("REJECT", "INVALID")][-top:]
        dom_tested: Dict[str, int] = {}
        for r in recs:
            for d in (r["domains"] or "").split(","):
                if d:
                    dom_tested[d] = dom_tested.get(d, 0) + 1
        brief = lambda r: {"title": r["hypothesis_title"], "formula": r["formula"], "valid_rank_ic": r["valid_rank_ic"],
                           "verdict": r["verdict"], "critique": (r["critique"] or "")[:240]}
        return {"n_tested": len(recs), "n_accepted": len([r for r in recs if r["verdict"] == "ACCEPT"]),
                "accepted": [brief(r) for r in acc], "recent_failures": [brief(r) for r in rej],
                "failure_pool": [brief(r) for r in [x for x in recs if x["verdict"] in ("REJECT", "INVALID", "REVISE")][-40:]],
                "domains_tested": dom_tested,
                "tested_hypothesis_ids": sorted({r["hypothesis_id"] for r in recs if r["hypothesis_id"]})}
