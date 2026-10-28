"""Parquet storage utilities for raw, processed, and unified panels."""
from pathlib import Path
from typing import Optional, List
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

class ParquetStore:
    """Handles saving and loading Parquet data across pipeline stages."""

    @staticmethod
    def write(df: pd.DataFrame, path: Path, partition_cols: Optional[List[str]] = None):
        """Writes a DataFrame to a Parquet file or partitioned directory."""
        if df.empty:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df)
        if partition_cols:
            pq.write_to_dataset(
                table,
                root_path=str(path),
                partition_cols=partition_cols,
                use_dictionary=True,
                compression="SNAPPY"
            )
        else:
            pq.write_table(table, str(path), compression="SNAPPY")

    @staticmethod
    def read(path: Path) -> pd.DataFrame:
        """Reads a Parquet file or directory into a pandas DataFrame."""
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)
