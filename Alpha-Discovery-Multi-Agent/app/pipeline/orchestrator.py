"""Deterministic Financial Pipeline Orchestrator (v2).

Universe -> Market -> Market QA -> Technical -> SEC -> SEC QA -> PIT fundamentals -> Valuation
-> FNSPID + Finnhub unified news -> FinBERT -> PIT alignment -> News QA -> Daily news features
-> FRED macro -> SPY walk-forward regime -> Regime QA -> Cross-sectional features
-> Unified DATE+TICKER panel -> Parquet/DuckDB -> feature registry, QA, manifest, run log.

Every stage after ingestion is rebuilt from cached raw data, so a run is reproducible offline.
"""
import json
import logging
import uuid
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config.settings import (
    ALPHAVANTAGE_API_KEY,
    BENCHMARK_TICKER,
    DATASET_VERSION,
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    MANIFESTS_DIR,
    PIPELINE_VERSION,
    PROCESSED_NEWS_DIR,
    PROCESSED_REGIME_DIR,
    REGIME_HISTORY_START,
    REPORTS_DIR,
    UNIVERSE_FILE,
    UNIVERSE_VERSION,
)
from app.data.providers.macro_provider import FredMacroProvider
from app.data.providers.market_provider import YahooMarketDataProvider
from app.data.providers.sec_provider import EdgarSECDataProvider
from app.data.qa.market_qa import MarketQA
from app.data.qa.quality_reporter import QualityReporter
from app.data.qa.regime_qa import RegimeQA
from app.data.qa.sec_qa import SECQA
from app.data.storage.duckdb_manager import DuckDBManager
from app.data.storage.parquet_store import ParquetStore
from app.features.cross_sectional import CrossSectionalFeatureEngine
from app.features.fundamentals import FundamentalFeatureEngine
from app.features.macro_features import MacroFeatureEngine
from app.pipeline.news_pipeline import NEWS_DB_COLUMNS as _UNUSED, build_news_layer
from app.features.registry import registry_frame
from app.features.technical import TechnicalFeatureEngine
from app.features.valuation import ValuationFeatureEngine
from app.models.regime import MarketRegimeEngine
from app.pipeline.panel_builder import PanelBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PipelineOrchestrator")



class PipelineOrchestrator:
    """Orchestrates extraction, QA, feature generation, storage and reporting."""

    def __init__(self, start_date: str = DEFAULT_START_DATE, end_date: str = DEFAULT_END_DATE,
                 duckdb_mgr: Optional[DuckDBManager] = None):
        self.start_date = start_date
        self.end_date = end_date
        self.duckdb_mgr = duckdb_mgr or DuckDBManager()
        self.market_provider = YahooMarketDataProvider()
        self.sec_provider = EdgarSECDataProvider()
        self.macro_provider = FredMacroProvider()
        self.regime_engine = MarketRegimeEngine(label_start="2013-01-01")
        self.panel_builder = PanelBuilder(duckdb_mgr=self.duckdb_mgr)

    def load_universe(self) -> List[Dict[str, Any]]:
        lines = [l for l in UNIVERSE_FILE.read_text().splitlines() if not l.strip().startswith("#")]
        return pd.read_csv(StringIO("\n".join(lines))).to_dict(orient="records")

    # ------------------------------------------------------------------ news stage
    def build_news(self, tickers: List[str], market_dates: pd.DataFrame, qa_records: List[Dict], run_id: str):
        """Shared news layer (FNSPID historical + Finnhub recent): see app/pipeline/news_pipeline.py."""
        res = build_news_layer(tickers, market_dates)
        for prov, summary in res["stats"]["qa"].items():
            qa_records.extend(QualityReporter.build_ticker_qa_records(f"NEWS_{prov}".upper(), run_id, summary, "news"))
        cov_rows = [{"ticker": t, "provider": p, "windows": len(iv)} for p, d in res["coverage"].items() for t, iv in d.items()]
        return res["articles"], res["daily"], pd.DataFrame(cov_rows)

    # ------------------------------------------------------------------ main
    def run(self, force_refresh: bool = False, update_news_archive: bool = True,
            score_finbert: bool = True) -> Dict[str, Any]:
        started = datetime.utcnow()
        run_id = f"run_{started.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info(f"=== Pipeline {PIPELINE_VERSION} run {run_id} ({self.start_date} -> {self.end_date}) ===")

        universe = self.load_universe()
        universe_df = pd.DataFrame(universe)
        tickers = [r["ticker"].upper() for r in universe]
        self.duckdb_mgr.replace_table("universe", universe_df)
        qa: List[Dict] = []

        # 1. Market + technical
        logger.info("--- Market ingestion, QA, technical features ---")
        market_frames = []
        for t in tickers:
            raw = self.market_provider.fetch_daily(t, self.start_date, self.end_date, force_refresh=force_refresh)
            val, q = MarketQA.validate_series(raw)
            market_frames.append(val)
            qa.extend(QualityReporter.build_ticker_qa_records(t, run_id, q, "market"))
        market = pd.concat(market_frames, ignore_index=True)
        market["date"] = pd.to_datetime(market["date"]).dt.date
        technical = TechnicalFeatureEngine.calculate_universe(market)
        dates = market[["date", "ticker"]]

        # 2. SEC fundamentals + valuation
        logger.info("--- SEC fundamentals (PIT v2) and valuation ---")
        facts_frames, split_frames = [], []
        for t in tickers:
            f = self.sec_provider.fetch_company_facts(t, force_refresh=force_refresh)
            if f.empty:
                continue
            fv, q = SECQA.validate_facts(f)
            facts_frames.append(fv)
            qa.extend(QualityReporter.build_ticker_qa_records(t, run_id, q, "sec"))
            split_frames.append(self.market_provider.fetch_splits(t))
        facts = pd.concat(facts_frames, ignore_index=True)
        splits = pd.concat(split_frames, ignore_index=True)
        fundamentals = FundamentalFeatureEngine.build_daily(dates, facts, splits)
        valuation = ValuationFeatureEngine.calculate_valuation_daily(market, fundamentals)

        # 3. News
        logger.info("--- News: FNSPID + Finnhub unified layer, FinBERT cache, PIT alignment, QA, daily features ---")
        news_articles, news_daily, news_cov = self.build_news(tickers, dates, qa, run_id)

        # 4. Macro
        logger.info("--- FRED macro factors ---")
        macro_raw = self.macro_provider.fetch_all(self.start_date, force_refresh=force_refresh)
        macro = MacroFeatureEngine.build_daily(macro_raw, market["date"].unique())

        # 5. Regime
        logger.info("--- SPY walk-forward HMM regime ---")
        spy = self.market_provider.fetch_daily(BENCHMARK_TICKER, REGIME_HISTORY_START, self.end_date,
                                               force_refresh=force_refresh)
        regime_full = self.regime_engine.detect_regimes(spy, force_refresh=True)
        regime = regime_full[pd.to_datetime(regime_full["date"]) >= pd.Timestamp(self.start_date)].reset_index(drop=True)
        regime_val, q = RegimeQA.validate_regimes(regime)
        qa.extend(QualityReporter.build_ticker_qa_records(BENCHMARK_TICKER, run_id, q, "regime"))
        regime_report = MarketRegimeEngine.validation_report(regime_full, "2020-01-01")
        (PROCESSED_REGIME_DIR / "regime_validation.json").write_text(json.dumps(regime_report, indent=2, default=str))

        # 6. Unified panel (+ cross-sectional features) and labels
        logger.info("--- Unified DATE+TICKER panel ---")
        panel = self.panel_builder.build_panel(
            market_df=market, technical_df=technical, fundamentals_df=fundamentals, valuation_df=valuation,
            news_df=news_daily, regime_df=regime, macro_df=macro, universe_df=universe_df,
            cross_sectional_fn=CrossSectionalFeatureEngine.build, pipeline_run_id=run_id)
        labels = CrossSectionalFeatureEngine.forward_returns(market)

        # 7. Persist domain tables
        db = self.duckdb_mgr
        db.replace_table("market_daily", market)
        db.replace_table("technical_features", technical)
        db.replace_table("sec_facts", facts.drop(columns=["retrieved_at"], errors="ignore"))
        db.replace_table("fundamental_daily", fundamentals)
        db.replace_table("valuation_daily", valuation)
        if not news_articles.empty:
            from app.pipeline.news_pipeline import NEWS_DB_COLUMNS
            na = news_articles.copy()
            for c in NEWS_DB_COLUMNS:                    # stable schema regardless of provider
                if c not in na.columns:
                    na[c] = None
            news_proc = na[NEWS_DB_COLUMNS]
            db.replace_table("news_processed", news_proc)
            db.replace_table("news_raw", news_proc[["article_hash", "article_id", "ticker", "provider", "title", "summary",
                                                    "publisher", "url", "published_at", "fetched_at"]])
            ParquetStore.write(news_proc, PROCESSED_NEWS_DIR / "news_processed.parquet")
        db.replace_table("news_daily", news_daily)
        if not news_cov.empty:
            db.replace_table("news_coverage", news_cov)
        db.replace_table("macro_daily", macro)
        db.replace_table("market_regime", regime_val)
        db.replace_table("forward_returns", labels)
        db.replace_table("feature_registry", registry_frame())

        coverage_cols = ["close", "daily_return", "rsi_14", "momentum_252_21d", "revenue", "net_income", "eps",
                         "roe", "pe_ratio", "earnings_yield", "news_count", "avg_finbert_sentiment",
                         "market_regime", "vix", "treasury_10y"]
        research = panel[pd.to_datetime(panel["date"]) >= pd.Timestamp("2020-01-01")]
        qa.extend(QualityReporter.build_feature_coverage_report(research, run_id, coverage_cols))
        db.replace_table("data_quality", pd.DataFrame(qa))

        finished = datetime.utcnow()
        manifest = {
            "run_id": run_id,
            "pipeline_version": PIPELINE_VERSION,
            "dataset_version": DATASET_VERSION,
            "universe_version": UNIVERSE_VERSION,
            "executed_at": finished.isoformat(),
            "duration_seconds": round((finished - started).total_seconds(), 1),
            "date_range": {"start_date": self.start_date, "end_date": self.end_date},
            "tickers_processed": tickers,
            "master_panel_rows": int(len(panel)),
            "master_panel_columns": int(panel.shape[1]),
            "news_articles": int(len(news_articles)),
            "news_coverage": news_cov.to_dict("records") if not news_cov.empty else [],
            "regime_validation": {k: v for k, v in regime_report.items() if k != "state_stats"},
            "status": "SUCCESS",
        }
        (MANIFESTS_DIR / f"{run_id}.json").write_text(json.dumps(manifest, indent=2, default=str))
        (REPORTS_DIR / "latest_run.json").write_text(json.dumps(manifest, indent=2, default=str))
        db.replace_table("pipeline_runs", pd.DataFrame([{
            "run_id": run_id, "started_at": started, "finished_at": finished, "status": "SUCCESS",
            "universe_version": UNIVERSE_VERSION, "dataset_version": DATASET_VERSION,
            "start_date": self.start_date, "end_date": self.end_date, "ticker_count": len(tickers),
            "error_summary": None}]))
        logger.info(f"=== Run {run_id} complete: {len(panel)} rows x {panel.shape[1]} columns ===")
        return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run the deterministic data pipeline")
    ap.add_argument("--no-news-update", action="store_true", help="(kept for compatibility) news is updated with app.pipeline.news_update")
    ap.add_argument("--no-finbert", action="store_true", help="use cached FinBERT scores only")
    ap.add_argument("--force-refresh", action="store_true")
    args = ap.parse_args()
    res = PipelineOrchestrator().run(force_refresh=args.force_refresh,
                                     update_news_archive=not args.no_news_update,
                                     score_finbert=not args.no_finbert)
    print(json.dumps({k: res[k] for k in ["run_id", "master_panel_rows", "master_panel_columns", "news_articles"]}, indent=2))
