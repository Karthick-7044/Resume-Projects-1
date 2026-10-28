"""FRED macroeconomic data provider (public CSV endpoint, no API key required)."""
import io
import logging
import time
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests

from app.config.settings import MACRO_SERIES, RAW_MACRO_DIR
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredMacroProvider:
    """Downloads daily FRED series and caches the raw observations as Parquet."""

    def __init__(self, raw_dir: Path = RAW_MACRO_DIR, series: Optional[Dict[str, str]] = None):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.series = series or MACRO_SERIES

    def fetch_series(self, series_id: str, start_date: str, force_refresh: bool = False) -> pd.DataFrame:
        cache = self.raw_dir / f"{series_id}.parquet"
        if cache.exists() and not force_refresh:
            return ParquetStore.read(cache)
        last_error = None
        for attempt in range(1, 4):
            try:
                resp = requests.get(FRED_CSV_URL, params={"id": series_id}, timeout=30,
                                    headers={"User-Agent": "Mozilla/5.0 (compatible; research)", "Accept": "text/csv"})
                resp.raise_for_status()
                raw = pd.read_csv(io.StringIO(resp.text))
                date_col = raw.columns[0]
                df = pd.DataFrame({
                    "date": pd.to_datetime(raw[date_col]).dt.date,
                    "series_id": series_id,
                    "value": pd.to_numeric(raw[series_id], errors="coerce"),  # FRED marks gaps with '.'
                })
                df = df[pd.to_datetime(df["date"]) >= pd.Timestamp(start_date) - pd.Timedelta(days=120)]
                df["retrieved_at"] = pd.Timestamp.utcnow().tz_localize(None)
                ParquetStore.write(df, cache)
                return df
            except (requests.RequestException, KeyError, ValueError) as e:
                last_error = e
                time.sleep(2.0 * attempt)
        logger.warning(f"FRED download failed for {series_id}: {last_error}")
        return pd.DataFrame(columns=["date", "series_id", "value"])

    def fetch_all(self, start_date: str, force_refresh: bool = False) -> pd.DataFrame:
        frames = [self.fetch_series(sid, start_date, force_refresh) for sid in self.series]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
