"""SEC Facts Quality Assurance and validation checks."""
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np


class SECQA:
    """Validates raw and structured SEC facts."""

    @staticmethod
    def validate_facts(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Runs quality checks on extracted SEC facts DataFrame.

        Returns:
            (annotated_df, summary_report)
        """
        if df.empty:
            return df, {
                "total_rows": 0,
                "overall_status": "FAIL",
                "reasons": ["Empty SEC facts dataset"],
                "passed_count": 0,
                "warning_count": 0,
                "fail_count": 0
            }

        res = df.copy()
        res["quality_status"] = "PASS"
        res["quality_reason"] = ""

        reasons = []

        # 1. Filing date chronologically after or on period end date
        res["period_end"] = pd.to_datetime(res["period_end"]).dt.date
        res["filed_date"] = pd.to_datetime(res["filed_date"]).dt.date

        invalid_dates = res["filed_date"] < res["period_end"]
        inv_date_count = int(invalid_dates.sum())
        if inv_date_count > 0:
            reasons.append(f"Found {inv_date_count} rows where filing date precedes period end date")
            res.loc[invalid_dates, "quality_status"] = "FAIL"
            res.loc[invalid_dates, "quality_reason"] = res.loc[invalid_dates, "quality_reason"] + "; Filing date before period end"

        # 2. Non-negative checks for assets and revenue
        negative_assets = (res["metric"] == "total_assets") & (res["value"] < 0)
        neg_assets_count = int(negative_assets.sum())
        if neg_assets_count > 0:
            reasons.append(f"Found {neg_assets_count} rows with negative total assets")
            res.loc[negative_assets, "quality_status"] = "FAIL"
            res.loc[negative_assets, "quality_reason"] = res.loc[negative_assets, "quality_reason"] + "; Negative assets"

        # 3. Non-negative shares check
        neg_shares = (res["metric"] == "shares") & (res["value"] <= 0)
        neg_shares_count = int(neg_shares.sum())
        if neg_shares_count > 0:
            reasons.append(f"Found {neg_shares_count} rows with non-positive shares count")
            res.loc[neg_shares, "quality_status"] = "WARNING"
            res.loc[neg_shares, "quality_reason"] = res.loc[neg_shares, "quality_reason"] + "; Non-positive shares"

        # Clean quality reason string
        res["quality_reason"] = res["quality_reason"].str.lstrip("; ")

        # Calculate counts
        passed_count = int((res["quality_status"] == "PASS").sum())
        warning_count = int((res["quality_status"] == "WARNING").sum())
        fail_count = int((res["quality_status"] == "FAIL").sum())

        overall_status = "PASS"
        if fail_count > 0:
            overall_status = "FAIL" if fail_count > (len(res) * 0.1) else "WARNING"
        elif warning_count > 0:
            overall_status = "WARNING"

        summary = {
            "total_rows": len(res),
            "overall_status": overall_status,
            "reasons": reasons if reasons else ["All SEC fact validations passed"],
            "passed_count": passed_count,
            "warning_count": warning_count,
            "fail_count": fail_count,
            "min_period_end": str(res["period_end"].min()),
            "max_period_end": str(res["period_end"].max()),
            "min_filed_date": str(res["filed_date"].min()),
            "max_filed_date": str(res["filed_date"].max())
        }

        return res, summary
