"""DuckDB manager for storage and querying."""
import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.config.settings import DUCKDB_PATH, STORAGE_DIR

class DuckDBManager:
    """Manages the DuckDB analytical database for the quantitative platform."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DUCKDB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def get_connection(self, retries: int = 8):
        """Returns a connection to the database. DuckDB allows one writing process at a time, so when another process
        (e.g. the API answering a request) briefly holds the file, wait and retry instead of failing (~30 s total)."""
        import time
        for attempt in range(retries):
            try:
                return duckdb.connect(str(self.db_path))
            except duckdb.IOException:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5 * 2 ** min(attempt, 4))

    def init_schema(self):
        """Initializes all required analytical tables if they do not already exist."""
        with self.get_connection() as con:
            # 1. Universe Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS universe (
                ticker VARCHAR PRIMARY KEY,
                company_name VARCHAR,
                sector VARCHAR,
                industry VARCHAR,
                exchange VARCHAR,
                active BOOLEAN,
                universe_version VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. Market Daily Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS market_daily (
                date DATE,
                ticker VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                adj_close DOUBLE,
                volume BIGINT,
                source VARCHAR,
                downloaded_at TIMESTAMP,
                dataset_version VARCHAR,
                quality_status VARCHAR,
                PRIMARY KEY (date, ticker)
            );
            """)

            # 3. Technical Features Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS technical_features (
                date DATE,
                ticker VARCHAR,
                daily_return DOUBLE,
                momentum_5d DOUBLE,
                momentum_10d DOUBLE,
                momentum_20d DOUBLE,
                momentum_60d DOUBLE,
                rsi_14 DOUBLE,
                macd DOUBLE,
                macd_signal DOUBLE,
                macd_hist DOUBLE,
                volatility_20d DOUBLE,
                volatility_60d DOUBLE,
                sma_5 DOUBLE,
                sma_20 DOUBLE,
                sma_50 DOUBLE,
                sma_100 DOUBLE,
                sma_200 DOUBLE,
                close_to_sma20 DOUBLE,
                close_to_sma50 DOUBLE,
                close_to_sma200 DOUBLE,
                sma20_to_sma50 DOUBLE,
                sma50_to_sma200 DOUBLE,
                volume_growth_5d DOUBLE,
                volume_growth_20d DOUBLE,
                volume_ratio_20d DOUBLE,
                PRIMARY KEY (date, ticker)
            );
            """)

            # 4. SEC Facts Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS sec_facts (
                ticker VARCHAR,
                cik VARCHAR,
                tag VARCHAR,
                metric VARCHAR,
                value DOUBLE,
                unit VARCHAR,
                fiscal_period VARCHAR,
                fiscal_year BIGINT,
                form VARCHAR,
                period_end DATE,
                filed_date DATE,
                frame VARCHAR,
                mapping_status VARCHAR,
                source_url VARCHAR,
                retrieved_at TIMESTAMP
            );
            """)

            # 5. Fundamental Daily (Point-in-Time as-of market date)
            con.execute("""
            CREATE TABLE IF NOT EXISTS fundamental_daily (
                date DATE,
                ticker VARCHAR,
                revenue DOUBLE,
                net_income DOUBLE,
                operating_income DOUBLE,
                total_assets DOUBLE,
                total_liabilities DOUBLE,
                shareholders_equity DOUBLE,
                cash DOUBLE,
                debt DOUBLE,
                eps DOUBLE,
                shares DOUBLE,
                roe DOUBLE,
                revenue_growth DOUBLE,
                eps_growth DOUBLE,
                profit_margin DOUBLE,
                operating_margin DOUBLE,
                debt_to_equity DOUBLE,
                fundamental_asof_date DATE,
                fundamental_filing_date DATE,
                fundamental_period_end DATE,
                fundamental_form VARCHAR,
                quality_status VARCHAR,
                PRIMARY KEY (date, ticker)
            );
            """)

            # 6. Valuation Daily Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS valuation_daily (
                date DATE,
                ticker VARCHAR,
                close DOUBLE,
                pe_ratio DOUBLE,
                pb_ratio DOUBLE,
                ps_ratio DOUBLE,
                PRIMARY KEY (date, ticker)
            );
            """)

            # 7. News Raw Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS news_raw (
                article_id VARCHAR PRIMARY KEY,
                ticker VARCHAR,
                source VARCHAR,
                url VARCHAR,
                title VARCHAR,
                published_at TIMESTAMP,
                collected_at TIMESTAMP,
                language VARCHAR,
                tone DOUBLE,
                ticker_mapping VARCHAR
            );
            """)

            # 8. News Daily Aggregates Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS news_daily (
                date DATE,
                ticker VARCHAR,
                news_count BIGINT,
                positive_news_count BIGINT,
                negative_news_count BIGINT,
                neutral_news_count BIGINT,
                average_news_tone DOUBLE,
                news_volume_change DOUBLE,
                important_event_count BIGINT,
                source_count BIGINT,
                latest_news_timestamp_used TIMESTAMP,
                PRIMARY KEY (date, ticker)
            );
            """)

            # 9. Market Regime Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS market_regime (
                date DATE PRIMARY KEY,
                market_regime VARCHAR,
                hmm_state BIGINT,
                regime_method VARCHAR,
                regime_version VARCHAR,
                benchmark_return DOUBLE,
                benchmark_momentum_20d DOUBLE,
                benchmark_volatility_20d DOUBLE
            );
            """)

            # 10. Unified Daily Stock Panel Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS daily_stock_panel (
                date DATE,
                ticker VARCHAR,
                company_name VARCHAR,
                sector VARCHAR,
                industry VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                adj_close DOUBLE,
                volume BIGINT,
                daily_return DOUBLE,
                momentum_5d DOUBLE,
                momentum_10d DOUBLE,
                momentum_20d DOUBLE,
                momentum_60d DOUBLE,
                rsi_14 DOUBLE,
                macd DOUBLE,
                macd_signal DOUBLE,
                macd_hist DOUBLE,
                volatility_20d DOUBLE,
                volatility_60d DOUBLE,
                sma_5 DOUBLE,
                sma_20 DOUBLE,
                sma_50 DOUBLE,
                sma_100 DOUBLE,
                sma_200 DOUBLE,
                close_to_sma20 DOUBLE,
                close_to_sma50 DOUBLE,
                close_to_sma200 DOUBLE,
                sma20_to_sma50 DOUBLE,
                sma50_to_sma200 DOUBLE,
                volume_growth_5d DOUBLE,
                volume_growth_20d DOUBLE,
                volume_ratio_20d DOUBLE,
                revenue DOUBLE,
                revenue_growth DOUBLE,
                net_income DOUBLE,
                operating_income DOUBLE,
                operating_margin DOUBLE,
                profit_margin DOUBLE,
                assets DOUBLE,
                liabilities DOUBLE,
                equity DOUBLE,
                cash DOUBLE,
                debt DOUBLE,
                debt_to_equity DOUBLE,
                eps DOUBLE,
                eps_growth DOUBLE,
                roe DOUBLE,
                pe_ratio DOUBLE,
                pb_ratio DOUBLE,
                news_count BIGINT,
                positive_news_count BIGINT,
                negative_news_count BIGINT,
                neutral_news_count BIGINT,
                average_news_tone DOUBLE,
                news_volume_change DOUBLE,
                important_event_count BIGINT,
                source_count BIGINT,
                market_regime VARCHAR,
                hmm_state BIGINT,
                regime_method VARCHAR,
                regime_version VARCHAR,
                fundamental_asof_date DATE,
                fundamental_filing_date DATE,
                latest_news_timestamp_used TIMESTAMP,
                market_data_quality VARCHAR,
                fundamental_data_quality VARCHAR,
                news_data_quality VARCHAR,
                feature_coverage_ratio DOUBLE,
                dataset_version VARCHAR,
                pipeline_run_id VARCHAR,
                PRIMARY KEY (date, ticker)
            );
            """)

            # 11. Data Quality Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS data_quality (
                id VARCHAR PRIMARY KEY,
                run_id VARCHAR,
                entity_type VARCHAR,
                entity_name VARCHAR,
                metric VARCHAR,
                coverage_percentage DOUBLE,
                missing_count BIGINT,
                total_count BIGINT,
                min_date DATE,
                max_date DATE,
                overall_status VARCHAR,
                details VARCHAR,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 12. Feature Registry Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS feature_registry (
                feature_name VARCHAR PRIMARY KEY,
                category VARCHAR,
                description VARCHAR,
                formula VARCHAR,
                source VARCHAR,
                lookback BIGINT,
                availability_rule VARCHAR,
                point_in_time_safe BOOLEAN,
                null_policy VARCHAR,
                version VARCHAR
            );
            """)

            # 13. Pipeline Runs Table
            con.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id VARCHAR PRIMARY KEY,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                status VARCHAR,
                universe_version VARCHAR,
                dataset_version VARCHAR,
                start_date DATE,
                end_date DATE,
                ticker_count BIGINT,
                error_summary VARCHAR
            );
            """)

    def upsert_dataframe(self, table_name: str, df: pd.DataFrame, primary_keys: List[str]):
        """Upserts a pandas DataFrame into a DuckDB table."""
        if df.empty:
            return
        with self.get_connection() as con:
            # Register dataframe in connection
            con.register("tmp_df", df)
            # Create a staging table
            con.execute("CREATE TEMPORARY TABLE staging AS SELECT * FROM tmp_df")

            # Get target table columns
            tbl_info = con.execute(f"PRAGMA table_info('{table_name}')").df()
            target_cols = set(tbl_info["name"].tolist())
            valid_cols = [c for c in df.columns if c in target_cols]
            cols_str = ", ".join([f'"{c}"' for c in valid_cols])

            # If primary keys provided, delete existing matching rows before insert
            if primary_keys:
                pk_match = " AND ".join([f'staging."{k}" = {table_name}."{k}"' for k in primary_keys if k in valid_cols])
                if pk_match:
                    con.execute(f"DELETE FROM {table_name} WHERE EXISTS (SELECT 1 FROM staging WHERE {pk_match})")

            con.execute(f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM staging")
            con.execute("DROP TABLE staging")

    def replace_table(self, table_name: str, df: pd.DataFrame):
        """Atomically replaces a derived table with a DataFrame (schema follows the DataFrame).

        Derived tables are fully rebuilt on every pipeline run from cached raw data, so replacing
        them keeps the schema in step with the feature engines and avoids stale rows.
        """
        if df is None:
            return
        with self.get_connection() as con:
            con.register("replace_df", df)
            con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM replace_df')
            con.unregister("replace_df")

    def table_exists(self, table_name: str) -> bool:
        df = self.query("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_name = ?", [table_name])
        return bool(df["n"].iloc[0])

    def upsert_universe(self, df: pd.DataFrame):
        if not df.empty:
            cols = [c for c in ["ticker", "company_name", "sector", "industry", "exchange", "active", "universe_version"] if c in df.columns]
            self.upsert_dataframe("universe", df[cols], ["ticker"])

    def upsert_market_daily(self, df: pd.DataFrame):
        if not df.empty:
            cols = [c for c in ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "source", "downloaded_at", "dataset_version", "quality_status"] if c in df.columns]
            self.upsert_dataframe("market_daily", df[cols], ["date", "ticker"])

    def upsert_technical_features(self, df: pd.DataFrame):
        if not df.empty:
            self.upsert_dataframe("technical_features", df, ["date", "ticker"])

    def upsert_sec_facts(self, df: pd.DataFrame):
        if not df.empty:
            cols = [c for c in ["ticker", "cik", "tag", "metric", "value", "unit", "fiscal_period", "fiscal_year", "form", "period_end", "filed_date", "frame", "mapping_status", "source_url", "retrieved_at"] if c in df.columns]
            self.upsert_dataframe("sec_facts", df[cols], [])

    def upsert_fundamental_daily(self, df: pd.DataFrame):
        if not df.empty:
            self.upsert_dataframe("fundamental_daily", df, ["date", "ticker"])

    def upsert_valuation_daily(self, df: pd.DataFrame):
        if not df.empty:
            self.upsert_dataframe("valuation_daily", df, ["date", "ticker"])

    def upsert_news_raw(self, df: pd.DataFrame):
        if not df.empty:
            cols = [c for c in ["article_id", "ticker", "source", "url", "title", "published_at", "collected_at", "language", "tone", "ticker_mapping"] if c in df.columns]
            self.upsert_dataframe("news_raw", df[cols], ["article_id"])

    def upsert_news_daily(self, df: pd.DataFrame):
        if not df.empty:
            self.upsert_dataframe("news_daily", df, ["date", "ticker"])

    def upsert_market_regime(self, df: pd.DataFrame):
        if not df.empty:
            cols = [c for c in ["date", "market_regime", "hmm_state", "regime_method", "regime_version", "benchmark_return", "benchmark_momentum_20d", "benchmark_volatility_20d"] if c in df.columns]
            self.upsert_dataframe("market_regime", df[cols], ["date"])

    def upsert_data_quality(self, records: List[Dict[str, Any]]):
        if records:
            df = pd.DataFrame(records)
            self.upsert_dataframe("data_quality", df, ["id"])

    def query(self, sql: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
        """Executes a SQL query and returns a pandas DataFrame."""
        with self.get_connection() as con:
            if params:
                return con.execute(sql, params).df()
            return con.execute(sql).df()

    def execute(self, sql: str, params: Optional[List[Any]] = None):
        """Executes a SQL statement without returning a DataFrame."""
        with self.get_connection() as con:
            if params:
                con.execute(sql, params)
            else:
                con.execute(sql)

