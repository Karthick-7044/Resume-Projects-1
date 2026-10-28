"""FastAPI routes for Quant Research Workspace and analytics API."""
from datetime import date
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from app.data.storage.duckdb_manager import DuckDBManager
import json
from app.config.settings import DUCKDB_PATH, PROCESSED_REGIME_DIR, ALPHA_RESULTS_DIR, ALPHA_EXPERIMENTS_DIR

router = APIRouter(prefix="/api")
duckdb_mgr = DuckDBManager(DUCKDB_PATH)


def clean_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Converts a DataFrame into JSON-compliant records replacing NaNs with None and formatting dates."""
    if df.empty:
        return []
    cleaned = df.copy()
    for col in cleaned.select_dtypes(include=["datetime64[ns]", "object"]).columns:
        cleaned[col] = cleaned[col].astype(str)
    # Convert dates to string
    if "date" in cleaned.columns:
        cleaned["date"] = cleaned["date"].astype(str)
    # Replace NaN, inf, -inf with None for valid JSON serialization
    cleaned = cleaned.replace([np.nan, np.inf, -np.inf], None)
    # Ensure any remaining float NaN is None
    records = cleaned.to_dict(orient="records")
    for r in records:
        for k, v in list(r.items()):
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                r[k] = None
    return records


@router.get("/universe")
def get_universe():
    """Returns the configured universe of tracked assets."""
    try:
        df = duckdb_mgr.query("SELECT * FROM universe ORDER BY ticker")
        return clean_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/panel")
def get_panel_data(
    ticker: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0, ge=0)
):
    """Returns paginated daily stock panel rows from DuckDB master panel table."""
    try:
        where_clauses = []
        params: List[Any] = []

        if ticker:
            where_clauses.append("ticker = ?")
            params.append(ticker.upper())
        if start_date:
            where_clauses.append("date >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("date <= ?")
            params.append(end_date)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Get total count
        count_sql = f"SELECT COUNT(*) as total FROM daily_stock_panel {where_sql}"
        cnt_df = duckdb_mgr.query(count_sql, params)
        total_count = int(cnt_df["total"].iloc[0]) if not cnt_df.empty else 0

        # Query paginated rows
        data_sql = f"SELECT * FROM daily_stock_panel {where_sql} ORDER BY date DESC, ticker ASC LIMIT ? OFFSET ?"
        data_params = params + [limit, offset]
        df = duckdb_mgr.query(data_sql, data_params)

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "ticker": ticker.upper() if ticker else None,
            "columns": list(df.columns) if not df.empty else [],
            "rows": clean_records(df)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fundamentals/quality")
def get_fundamentals_quality(limit: int = Query(500, le=5000)):
    """Returns data quality records for fundamentals."""
    try:
        df = duckdb_mgr.query("SELECT * FROM data_quality WHERE entity_type IN ('sec', 'fundamentals', 'feature') ORDER BY recorded_at DESC LIMIT ?", [limit])
        return {"rows": clean_records(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/{ticker}")
def get_market_data(
    ticker: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000, le=5000)
):
    """Returns historical daily OHLCV and technical features for a ticker."""
    ticker = ticker.upper()
    try:
        query = """
        SELECT m.date, m.ticker, m.open, m.high, m.low, m.close, m.adj_close, m.volume,
               t.daily_return, t.rsi_14, t.macd, t.macd_signal, t.macd_hist,
               t.volatility_20d, t.sma_20, t.sma_50, t.sma_200
        FROM market_daily m
        LEFT JOIN technical_features t ON m.date = t.date AND m.ticker = t.ticker
        WHERE m.ticker = ?
        """
        params = [ticker]
        if start_date:
            query += " AND m.date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND m.date <= ?"
            params.append(end_date)
        query += " ORDER BY m.date ASC LIMIT ?"
        params.append(limit)

        df = duckdb_mgr.query(query, params)
        return clean_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fundamentals/{ticker}")
def get_fundamentals_data(
    ticker: str,
    limit: int = Query(500, le=2000)
):
    """Returns Point-in-Time fundamental metrics and valuation ratios."""
    ticker = ticker.upper()
    try:
        query = """
        SELECT f.date, f.ticker, f.revenue, f.net_income, f.operating_income,
               f.roe, f.profit_margin, f.revenue_growth, f.eps_growth,
               f.fundamental_filing_date, f.fundamental_period_end, f.fundamental_form,
               v.pe_ratio, v.pb_ratio, v.ps_ratio
        FROM fundamental_daily f
        LEFT JOIN valuation_daily v ON f.date = v.date AND f.ticker = v.ticker
        WHERE f.ticker = ?
        ORDER BY f.date ASC LIMIT ?
        """
        df = duckdb_mgr.query(query, [ticker, limit])
        return clean_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/coverage")
def get_news_coverage():
    """Coverage per ticker and provider period. NO_COVERAGE days are NaN features, never 'zero news'."""
    try:
        cov = duckdb_mgr.query("""
            SELECT ticker, news_provider AS provider, MIN(date) AS coverage_start, MAX(date) AS coverage_end,
                   COUNT(*) AS covered_days
            FROM news_daily WHERE news_status <> 'NO_COVERAGE' GROUP BY ticker, news_provider ORDER BY ticker, provider""")
        status = duckdb_mgr.query("""
            SELECT ticker, news_status, COUNT(*) AS days FROM news_daily
            GROUP BY ticker, news_status ORDER BY ticker, news_status""")
        return {"coverage": clean_records(cov), "status_days": clean_records(status)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/quality")
def get_news_quality():
    """News QA summary: quality status, duplicates, PIT safety and FinBERT scoring status."""
    try:
        df = duckdb_mgr.query("""
            SELECT ticker, provider, COUNT(*) AS articles, COUNT(DISTINCT event_id) AS unique_events,
                   SUM(CASE WHEN quality_status = 'PASS' THEN 1 ELSE 0 END) AS passed,
                   SUM(CASE WHEN NOT pit_safe THEN 1 ELSE 0 END) AS pit_unsafe,
                   SUM(CASE WHEN is_duplicate THEN 1 ELSE 0 END) AS duplicates,
                   SUM(CASE WHEN finbert_status = 'OK' THEN 1 ELSE 0 END) AS finbert_scored,
                   AVG(av_ticker_sentiment) AS avg_av_sentiment, AVG(finbert_score) AS avg_finbert_sentiment,
                   MIN(published_at) AS first_article, MAX(published_at) AS last_article
            FROM news_processed GROUP BY ticker, provider ORDER BY ticker, provider""")
        return {"rows": clean_records(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news")
def get_news_articles(
    ticker: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Latest validated articles with provider and FinBERT sentiment (publisher/source retained), optionally within
    [start_date, end_date]."""
    try:
        conds, params = [], []
        if ticker:
            conds.append("ticker = ?"); params.append(ticker.upper())
        if start_date:
            conds.append("published_at >= CAST(? AS TIMESTAMPTZ)"); params.append(start_date)
        if end_date:
            conds.append("published_at < CAST(? AS TIMESTAMPTZ) + INTERVAL 1 DAY"); params.append(end_date)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        df = duckdb_mgr.query(f"""
            SELECT article_id, ticker, provider, title, publisher, url, published_at, effective_date, time_precision, topics, relevance_score, av_relevance_score,
                   av_ticker_sentiment, av_ticker_sentiment_label, finbert_label, finbert_score, finbert_status,
                   quality_status
            FROM news_processed {where} ORDER BY published_at DESC LIMIT ? OFFSET ?""", params + [limit, offset])
        return {"rows": clean_records(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/{ticker}")
def get_news_data(
    ticker: str,
    limit: int = Query(500, le=2000),
    covered_only: bool = True,
):
    """Daily point-in-time news features for a ticker (most recent `limit` trading days; by default only days
    inside provider coverage, so the tab shows real data rather than the NO_COVERAGE gap after 2023)."""
    ticker = ticker.upper()
    try:
        query = """
        SELECT * FROM (
            SELECT date, ticker, news_provider, news_status, news_quality, news_count, news_count_weighted, sent_mean,
                   sent_decay, sent_surprise, news_vol_surprise, sent_dispersion, sent_momentum, sent_earnings,
                   sent_analyst_rating, sent_mean_pstd, sent_decay_pstd, unique_event_count, positive_news_count,
                   negative_news_count, neutral_news_count, avg_av_sentiment, avg_finbert_sentiment,
                   sentiment_5d, sentiment_20d, av_sentiment_20d, news_volume_5d, news_volume_20d,
                   news_volume_zscore_20d, earnings_count, merger_count, technology_count, macro_count,
                   financial_market_count, source_count, latest_news_timestamp, news_cutoff_timestamp
            FROM news_daily WHERE ticker = ?{cov} ORDER BY date DESC LIMIT ?
        ) ORDER BY date ASC
        """.replace("{cov}", " AND news_status <> 'NO_COVERAGE'" if covered_only else "")
        df = duckdb_mgr.query(query, [ticker, limit])
        return clean_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro")
def get_macro(limit: int = Query(2000, le=5000)):
    """FRED macro factors aligned point-in-time to trading dates."""
    try:
        return clean_records(duckdb_mgr.query("SELECT * FROM macro_daily ORDER BY date ASC LIMIT ?", [limit]))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime/validation")
def get_regime_validation():
    """Walk-forward HMM validation report: state statistics, durations, agreement with baselines."""
    path = PROCESSED_REGIME_DIR / "regime_validation.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run the pipeline first")
    return json.loads(path.read_text())


@router.get("/features/registry")
def get_feature_registry():
    """Feature registry: definition, domain, availability rule and PIT status of every feature."""
    try:
        return clean_records(duckdb_mgr.query("SELECT * FROM feature_registry ORDER BY category, feature_name"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alpha/ablation")
def get_alpha_ablation(file: Optional[str] = Query(None)):
    """Ablation results for one run. Default: the most recently written results file (any window/mode)."""
    files = sorted(ALPHA_RESULTS_DIR.glob("ablation_results*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if file:
        files = [f for f in files if f.name == file]
    else:        # default: the newest file that holds the full set of configurations
        full = [f for f in files if len(json.loads(f.read_text()).get("configs", {})) >= 4]
        files = full or files
    if not files:
        raise HTTPException(status_code=404, detail="Run python -m app.alpha.run_discovery first")
    out = json.loads(files[0].read_text())
    out["file"] = files[0].name
    out["available_files"] = [f.name for f in sorted(ALPHA_RESULTS_DIR.glob("ablation_results*.json"))]
    return out


@router.get("/alpha/experiments")
def get_alpha_experiments(config: Optional[str] = Query(None), limit: int = Query(300, le=2000)):
    """Research memory: every tested hypothesis/formula with verdict and critique (latest run per config)."""
    try:
        where, params = "", []
        if config:
            where, params = "AND config = ?", [config]
        df = duckdb_mgr.query(f"""
            SELECT experiment_id, run_id, config, iteration, parent_id, hypothesis_id, hypothesis_title, rationale,
                   domains, formula, is_valid, verdict, score, train_rank_ic, train_sharpe, valid_rank_ic,
                   valid_sharpe, annual_turnover, dominant_domain, critique, revision_action, source, created_at
            FROM alpha_experiments
            WHERE run_id IN (SELECT MAX(run_id) FROM alpha_experiments GROUP BY config) {where}
            ORDER BY config, iteration LIMIT ?""", params + [limit])
        return {"rows": clean_records(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alpha/attribution")
def get_alpha_attribution(ids: str = Query(..., description="comma-separated experiment ids")):
    """Leave-one-feature-out attribution (training period) per experiment: rank-IC contribution of each feature leaf,
    domain shares and style exposures, read from the experiment lineage files written by the discovery loop."""
    out = []
    for eid in [i.strip() for i in ids.split(",") if i.strip()][:200]:
        if not eid.replace("_", "").isalnum():          # ids are exp_<hex>; never a path
            continue
        p = ALPHA_EXPERIMENTS_DIR / f"{eid}.json"
        if not p.exists():
            continue
        e = json.loads(p.read_text())
        att = (e.get("detail") or {}).get("attribution")
        if not att:
            continue
        out.append({"experiment_id": eid, "formula": e.get("formula"), "hypothesis_title": e.get("hypothesis_title"),
                    "verdict": e.get("verdict"), "train_rank_ic": e.get("train_rank_ic"), "valid_rank_ic": e.get("valid_rank_ic"),
                    **att})
    def finite(o):
        if isinstance(o, dict):
            return {k: finite(v) for k, v in o.items()}
        if isinstance(o, list):
            return [finite(v) for v in o]
        return None if isinstance(o, float) and not np.isfinite(o) else o
    return {"rows": finite(out)}


def _finite(o):
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_finite(v) for v in o]
    return None if isinstance(o, float) and not np.isfinite(o) else o


@router.get("/alpha/agent_loop")
def get_agent_loop(file: Optional[str] = Query(None), config: Optional[str] = Query(None)):
    """Every step of the agent loop for one run: Research-agent hypothesis, Quant-agent formula, validator result,
    backtest metrics, attribution, Critic verdict with each check, and refinement links (parent -> child)."""
    files = sorted(ALPHA_RESULTS_DIR.glob("ablation_results*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if file:
        files = [f for f in files if f.name == file]
    if not files:
        raise HTTPException(status_code=404, detail="no results file")
    res = json.loads(files[0].read_text())
    cfg_name = config if config in res["configs"] else next(iter(res["configs"]))
    rows = []
    for e in res["configs"][cfg_name]["experiments"]:
        p = ALPHA_EXPERIMENTS_DIR / f"{e['experiment_id']}.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        det = d.get("detail") or {}
        hyp, val, crit = det.get("hypothesis") or {}, det.get("validation") or {}, det.get("critique") or {}
        met, att = det.get("metrics") or {}, det.get("attribution") or {}
        brief = {k: {"rank_ic": (met.get(k) or {}).get("rank_ic", {}).get("mean"), "rank_ic_t": (met.get(k) or {}).get("rank_ic", {}).get("t_stat"),
                     "sharpe": (met.get(k) or {}).get("sharpe"), "annual_turnover": (met.get(k) or {}).get("annual_turnover")}
                 for k in ("train", "valid") if met.get(k)}
        rows.append({"experiment_id": e["experiment_id"], "iteration": e.get("iteration"), "parent_id": d.get("parent_id"),
                     "revision_action": d.get("revision_action"), "source": d.get("source") or "knowledge_base",
                     "hypothesis": {"id": hyp.get("id") or d.get("hypothesis_id"), "title": hyp.get("title") or e.get("hypothesis_title"),
                                    "rationale": hyp.get("rationale") or d.get("rationale"), "literature_basis": hyp.get("literature_basis"),
                                    "domains": hyp.get("domains") or e.get("domains"), "expected_sign": hyp.get("expected_sign"),
                                    "key_features": hyp.get("key_features")},
                     "formula": e["formula"], "validation": {"valid": val.get("valid", e["verdict"] != "INVALID"), "errors": val.get("errors", []),
                                                             "nodes": val.get("nodes"), "originality": val.get("originality")},
                     "metrics": brief, "attribution": {"domain_share": att.get("domain_share"), "dominant_domain": att.get("dominant_domain")},
                     "critic": {"verdict": e["verdict"], "summary": crit.get("summary") or e.get("critique"),
                                "checks": crit.get("checks", []), "actions": crit.get("actions", []), "score": crit.get("score")}})
    return _finite({"file": files[0].name, "config": cfg_name, "configs": list(res["configs"]), "window": res.get("window"),
                    "periods": res.get("periods"), "rows": rows,
                    "available_files": [f.name for f in sorted(ALPHA_RESULTS_DIR.glob("ablation_results*.json"))]})


@router.get("/alpha/briefing")
def get_research_briefing():
    """The exact anonymised briefing the Research agent received in the most recent LLM call, and its answer."""
    from app.config.settings import ALPHA_LLM_DIR
    log = ALPHA_LLM_DIR / "calls.jsonl"
    if not log.exists():
        raise HTTPException(status_code=404, detail="no LLM calls logged yet")
    keys = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"research"' in l]
    for k in reversed(keys):
        p = ALPHA_LLM_DIR / "cache" / f"{k['key']}.json"
        if p.exists():
            c = json.loads(p.read_text(encoding="utf-8"))
            return {"ts": k["ts"], "provider": c.get("provider"), "model": c.get("model"), "system": c.get("system"),
                    "user": c.get("user"), "response": c.get("response"), "n_research_calls": len(keys)}
    raise HTTPException(status_code=404, detail="no cached research call")


@router.get("/alpha/summary")
def get_alpha_summary():
    """Headline statistics of the robustness study (walk-forward, Holm, random null, cost-aware, FF5+Mom, FinBERT)."""
    from app.config.settings import BASE_DIR
    p = BASE_DIR / "docs" / "paper" / "figures" / "paper_stats_v3.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="run docs/paper/collect_stats_v3.py first")
    return _finite(json.loads(p.read_text()))


@router.get("/alpha/factor_report")
def get_factor_report():
    """Plain-language report card per Critic-accepted LLM factor (built by python -m app.alpha.factor_report)."""
    p = ALPHA_RESULTS_DIR / "factor_report.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="run python -m app.alpha.factor_report first")
    return _finite(json.loads(p.read_text()))


@router.get("/alpha/post_cutoff")
def get_post_cutoff():
    """Final post-knowledge-cutoff test, LLM signals vs built-in library (built by python -m app.alpha.post_cutoff_eval)."""
    p = ALPHA_RESULTS_DIR / "post_cutoff_eval.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="run python -m app.alpha.post_cutoff_eval first")
    return _finite(json.loads(p.read_text()))


DOWNLOADS = {
    "paper_v3.docx": "docs/paper/Regime_Aware_Multi_Agent_Alpha_Discovery_IEEE_Paper_v3.docx",
    "results_v3.md": "docs/RESULTS_v3.md",
    "project_report_simple.md": "docs/PROJECT_REPORT_SIMPLE.md",
    "framework_guide.md": "docs/FRAMEWORK_GUIDE.md",
}


@router.get("/files")
def list_files():
    from app.config.settings import BASE_DIR
    return [{"name": k, "path": v, "exists": (BASE_DIR / v).exists()} for k, v in DOWNLOADS.items()]


@router.get("/files/{name}")
def get_file(name: str):
    from fastapi.responses import FileResponse
    from app.config.settings import BASE_DIR
    if name not in DOWNLOADS or not (BASE_DIR / DOWNLOADS[name]).exists():
        raise HTTPException(status_code=404, detail="unknown file")
    return FileResponse(BASE_DIR / DOWNLOADS[name], filename=name)


@router.get("/alpha/equity")
def get_alpha_equity():
    """Validation + test equity curves of the combined factor of each configuration."""
    try:
        return clean_records(duckdb_mgr.query(
            "SELECT date, config, net_return, equity FROM alpha_equity_curves ORDER BY config, date"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime")
def get_market_regimes(
    limit: int = Query(1000, le=5000)
):
    """Returns market regime classification timeline."""
    try:
        query = """
        SELECT date, market_regime, hmm_state, regime_method, regime_probability, regime_rule_based,
               benchmark_return, benchmark_momentum_20d, benchmark_volatility_20d
        FROM market_regime
        WHERE date >= DATE '2020-01-01'
        ORDER BY date ASC LIMIT ?
        """
        df = duckdb_mgr.query(query, [limit])
        return clean_records(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/status")
def get_pipeline_status():
    """Returns latest data quality summaries, table counts, and pipeline health."""
    try:
        table_counts = {}
        tables = [
            "universe", "market_daily", "technical_features", "sec_facts",
            "fundamental_daily", "valuation_daily", "news_raw", "news_processed", "news_daily",
            "macro_daily", "forward_returns", "feature_registry", "alpha_experiments",
            "market_regime", "daily_stock_panel", "data_quality"
        ]
        for tbl in tables:
            try:
                cnt_df = duckdb_mgr.query(f"SELECT COUNT(*) as count FROM {tbl}")
                table_counts[tbl] = int(cnt_df["count"].iloc[0]) if not cnt_df.empty else 0
            except Exception:
                table_counts[tbl] = 0

        # Latest data quality records
        dq_df = duckdb_mgr.query("SELECT * FROM data_quality ORDER BY recorded_at DESC LIMIT 50")

        return {
            "status": "HEALTHY",
            "table_counts": table_counts,
            "data_quality_summary": clean_records(dq_df)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
