"""Market data provider abstraction and Yahoo Finance implementation."""
from abc import ABC, abstractmethod
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import time
import logging
import pandas as pd
import yfinance as yf

from app.config.settings import (
    RAW_MARKET_DIR,
    PROCESSED_MARKET_DIR,
    DEFAULT_START_DATE,
    DEFAULT_END_DATE,
    DATASET_VERSION
)
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

class MarketDataProvider(ABC):
    """Abstract base class for daily market data providers."""

    @abstractmethod
    def fetch_daily(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        force_refresh: bool = False,
        incremental: bool = True
    ) -> pd.DataFrame:
        """Fetches daily OHLCV for a single ticker."""
        pass

    @abstractmethod
    def fetch_universe(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        force_refresh: bool = False,
        incremental: bool = True
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str]]:
        """Fetches daily OHLCV for multiple tickers. Returns (data_dict, errors_dict)."""
        pass


class YahooMarketDataProvider(MarketDataProvider):
    """Market data provider fetching daily OHLCV from Yahoo Finance with local Parquet caching."""

    def __init__(
        self,
        raw_dir: Path = RAW_MARKET_DIR,
        dataset_version: str = DATASET_VERSION,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        timeout: int = 20
    ):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_version = dataset_version
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout

    def _get_raw_cache_path(self, ticker: str) -> Path:
        return self.raw_dir / f"{ticker.upper()}.parquet"

    def fetch_daily(
        self,
        ticker: str,
        start_date: str = DEFAULT_START_DATE,
        end_date: str = DEFAULT_END_DATE,
        force_refresh: bool = False,
        incremental: bool = True
    ) -> pd.DataFrame:
        """Fetches daily OHLCV for ticker with intelligent Parquet caching and backoff."""
        ticker = ticker.strip().upper()
        cache_file = self._get_raw_cache_path(ticker)

        cached_df = pd.DataFrame()
        if cache_file.exists() and not force_refresh:
            cached_df = ParquetStore.read(cache_file)
            if not cached_df.empty:
                cached_df["date"] = pd.to_datetime(cached_df["date"]).dt.date
                cached_min = cached_df["date"].min()
                cached_max = cached_df["date"].max()
                req_start = datetime.strptime(start_date, "%Y-%m-%d").date()
                req_end = datetime.strptime(end_date, "%Y-%m-%d").date()

                # If cache already completely covers the requested range
                if incremental and cached_min <= req_start and cached_max >= req_end:
                    filtered = cached_df[
                        (cached_df["date"] >= req_start) & (cached_df["date"] <= req_end)
                    ].copy()
                    return filtered.sort_values("date").reset_index(drop=True)

        # Download from Yahoo Finance with exponential backoff
        download_df = self._download_with_retry(ticker, start_date, end_date)

        if download_df.empty and not cached_df.empty:
            logger.warning(f"Failed to fetch new data for {ticker}, returning cached data.")
            return cached_df

        if download_df.empty:
            raise ValueError(f"No market data returned for ticker {ticker} from {start_date} to {end_date}")

        # Standardize columns
        download_df = self._standardize_data(download_df, ticker)

        # Merge with existing cache if incremental
        if not cached_df.empty and not force_refresh:
            combined = pd.concat([cached_df, download_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["date", "ticker"], keep="last")
            combined = combined.sort_values("date").reset_index(drop=True)
        else:
            combined = download_df.sort_values("date").reset_index(drop=True)

        # Save to raw Parquet cache
        ParquetStore.write(combined, cache_file)

        # Filter to requested range
        req_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        req_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        result = combined[
            (combined["date"] >= req_start) & (combined["date"] <= req_end)
        ].copy().sort_values("date").reset_index(drop=True)

        return result

    def _download_with_retry(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Executes yf.download with retry and exponential backoff."""
        attempt = 0
        last_error = None
        while attempt < self.max_retries:
            try:
                # Add 1 day to end_date for yfinance inclusive behavior
                end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                end_str = end_dt.strftime("%Y-%m-%d")

                df = yf.download(
                    tickers=ticker,
                    start=start_date,
                    end=end_str,
                    progress=False,
                    auto_adjust=False,
                    timeout=self.timeout
                )
                if not df.empty:
                    # If multi-index columns returned, flatten them
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [c[0] for c in df.columns]
                    return df
                else:
                    attempt += 1
                    time.sleep(self.backoff_factor ** attempt)
            except Exception as e:
                last_error = e
                attempt += 1
                logger.warning(f"Attempt {attempt}/{self.max_retries} failed for {ticker}: {e}")
                time.sleep(self.backoff_factor ** attempt)

        if last_error:
            raise RuntimeError(f"Exceeded max retries fetching market data for {ticker}: {last_error}")
        return pd.DataFrame()

    def _standardize_data(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Converts raw yfinance output to required standard schema."""
        res = df.reset_index().copy()

        # Identify date column
        date_col = None
        for col in ["Date", "Datetime", "date", "index"]:
            if col in res.columns:
                date_col = col
                break
        if date_col is None:
            raise ValueError(f"Could not locate Date column in yfinance output for {ticker}")

        res["date"] = pd.to_datetime(res[date_col]).dt.date
        res["ticker"] = ticker.upper()

        # Map OHLCV columns
        col_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume"
        }
        for orig, target in col_map.items():
            if orig in res.columns:
                res[target] = pd.to_numeric(res[orig], errors="coerce")
            elif target in res.columns:
                res[target] = pd.to_numeric(res[target], errors="coerce")
            else:
                if target == "adj_close" and "Close" in res.columns:
                    res["adj_close"] = res["open"]
                else:
                    res[target] = None

        res["source"] = "yfinance"
        res["downloaded_at"] = pd.Timestamp.utcnow()
        res["dataset_version"] = self.dataset_version

        cols = [
            "date", "ticker", "open", "high", "low", "close", "adj_close", "volume",
            "source", "downloaded_at", "dataset_version"
        ]
        return res[cols]

    def fetch_universe(
        self,
        tickers: List[str],
        start_date: str = DEFAULT_START_DATE,
        end_date: str = DEFAULT_END_DATE,
        force_refresh: bool = False,
        incremental: bool = True
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str]]:
        """Fetches data for entire universe with fault isolation."""
        data_dict: Dict[str, pd.DataFrame] = {}
        errors_dict: Dict[str, str] = {}

        for ticker in tickers:
            ticker = ticker.strip().upper()
            try:
                df = self.fetch_daily(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    force_refresh=force_refresh,
                    incremental=incremental
                )
                data_dict[ticker] = df
                logger.info(f"Successfully fetched {len(df)} market records for {ticker}")
            except Exception as e:
                errors_dict[ticker] = str(e)
                logger.error(f"Failed to fetch market data for {ticker}: {e}")

        return data_dict, errors_dict

    def fetch_splits(self, ticker: str, force_refresh: bool = False) -> pd.DataFrame:
        """Stock split history (date, ratio) used to put SEC share counts on yfinance's price basis.

        yfinance OHLC prices are retroactively split-adjusted to today's share basis, whereas SEC
        share counts and EPS are as-reported. The ratio lets the valuation engine convert between them.
        """
        ticker = ticker.strip().upper()
        cache_file = self.raw_dir / "splits" / f"{ticker}.parquet"
        if cache_file.exists() and not force_refresh:
            return ParquetStore.read(cache_file)
        try:
            s = yf.Ticker(ticker).splits
        except Exception as e:  # network/scraper failure: callers treat missing splits as none
            logger.warning(f"Could not fetch split history for {ticker}: {e}")
            return pd.DataFrame(columns=["date", "ticker", "ratio"])
        df = pd.DataFrame({
            "date": pd.to_datetime(s.index).tz_localize(None).date if len(s) else [],
            "ticker": ticker,
            "ratio": s.values.astype(float) if len(s) else [],
        })
        if df.empty:
            df = pd.DataFrame({"date": pd.Series([], dtype="object"), "ticker": pd.Series([], dtype="object"),
                               "ratio": pd.Series([], dtype="float64")})
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_file)
            return df
        ParquetStore.write(df, cache_file)
        return df
