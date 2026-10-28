"""Market Regime Quality Assurance and validation checks."""
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np


class RegimeQA:
    """Validates market regime predictions and benchmark series integrity."""

    @staticmethod
    def validate_regimes(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Runs quality checks on market regime DataFrame.

        Returns:
            (annotated_df, summary_report)
        """
        if df.empty:
            return df, {
                "total_rows": 0,
                "overall_status": "FAIL",
                "reasons": ["Empty regime dataset"],
                "passed_count": 0,
                "warning_count": 0,
                "fail_count": 0
            }

        res = df.copy()
        res["quality_status"] = "PASS"
        res["quality_reason"] = ""

        reasons = []

        # 1. Check date continuity / monotonic ordering
        res["date"] = pd.to_datetime(res["date"]).dt.date
        if not res["date"].is_monotonic_increasing:
            reasons.append("Regime dates not sorted monotonically")
            res = res.sort_values("date").reset_index(drop=True)

        # 2. Check for empty regime labels
        empty_labels = res["market_regime"].isnull() | (res["market_regime"] == "")
        empty_count = int(empty_labels.sum())
        if empty_count > 0:
            reasons.append(f"Found {empty_count} rows with missing regime labels")
            res.loc[empty_labels, "quality_status"] = "FAIL"
            res.loc[empty_labels, "quality_reason"] = res.loc[empty_labels, "quality_reason"] + "; Missing regime label"

        # 3. Check volatility non-negativity
        neg_vol = (res["benchmark_volatility_20d"].notnull()) & (res["benchmark_volatility_20d"] < 0)
        neg_vol_count = int(neg_vol.sum())
        if neg_vol_count > 0:
            reasons.append(f"Found {neg_vol_count} rows with negative volatility")
            res.loc[neg_vol, "quality_status"] = "FAIL"
            res.loc[neg_vol, "quality_reason"] = res.loc[neg_vol, "quality_reason"] + "; Negative volatility"

        res["quality_reason"] = res["quality_reason"].str.lstrip("; ")

        passed_count = int((res["quality_status"] == "PASS").sum())
        warning_count = int((res["quality_status"] == "WARNING").sum())
        fail_count = int((res["quality_status"] == "FAIL").sum())

        overall_status = "PASS" if fail_count == 0 else "FAIL"

        summary = {
            "total_rows": len(res),
            "overall_status": overall_status,
            "reasons": reasons if reasons else ["All regime validations passed"],
            "passed_count": passed_count,
            "warning_count": warning_count,
            "fail_count": fail_count,
            "min_date": str(res["date"].min()),
            "max_date": str(res["date"].max())
        }

        return res, summary
