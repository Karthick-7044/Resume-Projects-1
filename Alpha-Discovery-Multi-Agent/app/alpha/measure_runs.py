"""Efficiency of the v4 and v5 LLM discovery runs: time per formula, LLM calls and tokens per formula.

    python -m app.alpha.measure_runs

Round boundaries come from data/alpha/results/llm_v{4,5}.log ("== vN discovery seed S  <timestamp>"); LLM calls and token
usage come from data/alpha/llm/calls.jsonl (usage is logged by the provider client; cached calls have no usage).
"""
import json
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.config.settings import ALPHA_LLM_DIR, ALPHA_RESULTS_DIR

LOCAL_OFFSET = timedelta(hours=5, minutes=30)     # the run logs use local time (IST), calls.jsonl uses UTC


def rounds(version: str) -> list:
    log = (ALPHA_RESULTS_DIR / f"llm_{version}.log").read_text(encoding="utf-8", errors="ignore").splitlines()
    starts = [(int(m.group(1)), datetime.fromisoformat(m.group(2)))
              for l in log if (m := re.match(rf"== {version} discovery seed (\d+)\s+(\S+)", l))]
    out = []
    for i, (seed, t0) in enumerate(starts):
        p = ALPHA_RESULTS_DIR / f"ablation_results_recent_llm_{version}_seed{seed}.json"
        if not p.exists():
            continue
        res = json.loads(p.read_text())
        t1 = datetime.fromtimestamp(p.stat().st_mtime)     # results file is written when the round ends (local time)
        cfg = res["configs"]["Full"]
        out.append({"seed": seed, "start": t0, "end": t1, "n_tested": cfg["n_tested"], "verdicts": cfg["verdicts"]})
    return out


def run() -> dict:
    calls = pd.DataFrame([json.loads(l) for l in (ALPHA_LLM_DIR / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()])
    calls["t"] = pd.to_datetime(calls["ts"], utc=True).dt.tz_localize(None) + LOCAL_OFFSET
    calls["tokens"] = calls.get("usage", pd.Series(dtype=object)).map(lambda u: u.get("total_tokens") if isinstance(u, dict) else None)
    out = {}
    for v in ("v4", "v5"):
        rs = [r for r in rounds(v) if r["end"] is not None and r["n_tested"] > 0]
        if not rs:
            continue
        rows = []
        for r in rs:
            c = calls[(calls["t"] >= r["start"]) & (calls["t"] <= r["end"]) & (~calls["cached"].astype(bool))]
            mins = (r["end"] - r["start"]).total_seconds() / 60
            rows.append({"seed": r["seed"], "minutes": mins, "formulas": r["n_tested"], "accepted": r["verdicts"].get("ACCEPT", 0),
                         "llm_calls": len(c), "tokens": float(c["tokens"].dropna().sum()) if c["tokens"].notna().any() else None,
                         "tokens_logged_calls": int(c["tokens"].notna().sum()),
                         "prompt_chars": float(c["prompt_chars"].dropna().mean()) if "prompt_chars" in c and c["prompt_chars"].notna().any() else None})
        df = pd.DataFrame(rows)
        f = df["formulas"].sum()
        tok = df.dropna(subset=["tokens"])
        out[v] = {"rounds": rows, "formulas": int(f), "accepted": int(df["accepted"].sum()),
                  "minutes_per_round": float(df["minutes"].mean()), "seconds_per_formula": float(df["minutes"].sum() * 60 / f),
                  "llm_calls_per_formula": float(df["llm_calls"].sum() / f),
                  "tokens_per_formula": float(tok["tokens"].sum() / tok["formulas"].sum()) if len(tok) and tok["tokens"].sum() > 0 else None,
                  "mean_prompt_chars": float(df["prompt_chars"].dropna().mean()) if df["prompt_chars"].notna().any() else None}
    (ALPHA_RESULTS_DIR / "run_efficiency.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    for v, s in run().items():
        print(v, {k: (round(x, 1) if isinstance(x, float) else x) for k, x in s.items() if k != "rounds"})
