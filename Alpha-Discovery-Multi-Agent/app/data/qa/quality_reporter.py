"""Data quality reporting across tickers and features."""
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import uuid

class QualityReporter:
    """Consolidates data quality and coverage reports for analytical storage and UI."""

    @staticmethod
    def build_ticker_qa_records(
        ticker: str,
        run_id: str,
        qa_summary: Dict[str, Any],
        entity_type: str = "market"
    ) -> List[Dict[str, Any]]:
        """Transforms a market QA summary into structured records for data_quality table."""
        total = qa_summary.get("total_rows", 0)
        passed = qa_summary.get("passed_count", 0)
        coverage_pct = (passed / total * 100.0) if total > 0 else 0.0

        record = {
            "id": f"{run_id}_{entity_type}_{ticker}",
            "run_id": run_id,
            "entity_type": entity_type,
            "entity_name": ticker,
            "metric": "ohlcv_integrity",
            "coverage_percentage": round(coverage_pct, 2),
            "missing_count": qa_summary.get("fail_count", 0),
            "total_count": total,
            "min_date": qa_summary.get("min_date"),
            "max_date": qa_summary.get("max_date"),
            "overall_status": qa_summary.get("overall_status", "UNKNOWN"),
            "details": "; ".join(qa_summary.get("reasons", [])),
            "recorded_at": datetime.utcnow()
        }
        return [record]

    @staticmethod
    def build_feature_coverage_report(
        df: pd.DataFrame,
        run_id: str,
        feature_cols: List[str],
        entity_name: str = "GLOBAL"
    ) -> List[Dict[str, Any]]:
        """Calculates feature-level coverage and missing counts across the dataset."""
        records = []
        total_rows = len(df)
        min_date = str(df["date"].min()) if "date" in df.columns and not df.empty else None
        max_date = str(df["date"].max()) if "date" in df.columns and not df.empty else None

        for col in feature_cols:
            if col not in df.columns:
                records.append({
                    "id": f"{run_id}_feature_{col}_{entity_name}",
                    "run_id": run_id,
                    "entity_type": "feature",
                    "entity_name": entity_name,
                    "metric": col,
                    "coverage_percentage": 0.0,
                    "missing_count": total_rows,
                    "total_count": total_rows,
                    "min_date": min_date,
                    "max_date": max_date,
                    "overall_status": "MISSING",
                    "details": "Column missing from dataset",
                    "recorded_at": datetime.utcnow()
                })
                continue

            missing = int(df[col].isnull().sum())
            available = total_rows - missing
            coverage_pct = (available / total_rows * 100.0) if total_rows > 0 else 0.0
            status = "PASS" if coverage_pct >= 90.0 else ("WARNING" if coverage_pct >= 50.0 else "FAIL")

            records.append({
                "id": f"{run_id}_feature_{col}_{entity_name}",
                "run_id": run_id,
                "entity_type": "feature",
                "entity_name": entity_name,
                "metric": col,
                "coverage_percentage": round(coverage_pct, 2),
                "missing_count": missing,
                "total_count": total_rows,
                "min_date": min_date,
                "max_date": max_date,
                "overall_status": status,
                "details": f"{available}/{total_rows} valid observations",
                "recorded_at": datetime.utcnow()
            })

        return records
