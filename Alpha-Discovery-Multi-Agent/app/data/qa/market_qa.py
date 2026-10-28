"""Market data quality checks and validation rules."""
from typing import Tuple, Dict, Any, List
import pandas as pd
import numpy as np

class MarketQA:
    """Deterministic validation of daily market data (OHLCV)."""

    @staticmethod
    def validate_series(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Runs validation checks on a market dataframe for a ticker.

        Returns:
            (annotated_df, summary_report)
        """
        if df.empty:
            return df, {
                "total_rows": 0,
                "overall_status": "FAIL",
                "reasons": ["Empty dataset"],
                "passed_count": 0,
                "warning_count": 0,
                "fail_count": 0
            }

        res = df.copy()
        res["quality_status"] = "PASS"
        res["quality_reason"] = ""

        reasons = []

        # 1. Date ordering
        is_sorted = res["date"].is_monotonic_increasing
        if not is_sorted:
            reasons.append("Dates not monotonically increasing")
            # Sort explicitly without dropping
            res = res.sort_values("date").reset_index(drop=True)

        # 2. Duplicate (date, ticker)
        dups = res.duplicated(subset=["date", "ticker"], keep=False)
        dup_count = int(dups.sum())
        if dup_count > 0:
            reasons.append(f"Found {dup_count} duplicate (date, ticker) rows")
            res.loc[dups, "quality_status"] = "FAIL"
            res.loc[dups, "quality_reason"] = res.loc[dups, "quality_reason"] + "; Duplicate (date, ticker)"

        # 3. Missing OHLC
        ohlc_cols = ["open", "high", "low", "close"]
        missing_ohlc = res[ohlc_cols].isnull().any(axis=1)
        missing_count = int(missing_ohlc.sum())
        if missing_count > 0:
            reasons.append(f"Found {missing_count} rows with missing OHLC values")
            res.loc[missing_ohlc, "quality_status"] = "FAIL"
            res.loc[missing_ohlc, "quality_reason"] = res.loc[missing_ohlc, "quality_reason"] + "; Missing OHLC"

        # 4. Non-positive prices (<= 0)
        non_positive = (res[ohlc_cols] <= 0).any(axis=1)
        non_pos_count = int(non_positive.sum())
        if non_pos_count > 0:
            reasons.append(f"Found {non_pos_count} rows with non-positive prices (<= 0)")
            res.loc[non_positive, "quality_status"] = "FAIL"
            res.loc[non_positive, "quality_reason"] = res.loc[non_positive, "quality_reason"] + "; Non-positive price"

        # 5. Negative volume (< 0)
        neg_volume = res["volume"] < 0
        neg_vol_count = int(neg_volume.sum())
        if neg_vol_count > 0:
            reasons.append(f"Found {neg_vol_count} rows with negative volume")
            res.loc[neg_volume, "quality_status"] = "FAIL"
            res.loc[neg_volume, "quality_reason"] = res.loc[neg_volume, "quality_reason"] + "; Negative volume"

        # 6. High < Low violation
        high_lt_low = res["high"] < res["low"]
        high_low_count = int(high_lt_low.sum())
        if high_low_count > 0:
            reasons.append(f"Found {high_low_count} rows where high < low")
            res.loc[high_lt_low, "quality_status"] = "FAIL"
            res.loc[high_lt_low, "quality_reason"] = res.loc[high_lt_low, "quality_reason"] + "; High < Low"

        # 7. Close outside [Low, High] or Open outside [Low, High] (WARNING)
        outside_range = (
            (res["open"] < res["low"]) | (res["open"] > res["high"]) |
            (res["close"] < res["low"]) | (res["close"] > res["high"])
        ) & (res["quality_status"] != "FAIL")
        outside_count = int(outside_range.sum())
        if outside_count > 0:
            reasons.append(f"Found {outside_count} rows where Open/Close lies outside [Low, High]")
            res.loc[outside_range, "quality_status"] = "WARNING"
            res.loc[outside_range, "quality_reason"] = res.loc[outside_range, "quality_reason"] + "; Open/Close outside [Low, High]"

        # Zero volume on a trading day (WARNING)
        zero_vol = (res["volume"] == 0) & (res["quality_status"] == "PASS")
        zero_vol_count = int(zero_vol.sum())
        if zero_vol_count > 0:
            res.loc[zero_vol, "quality_status"] = "WARNING"
            res.loc[zero_vol, "quality_reason"] = res.loc[zero_vol, "quality_reason"] + "; Zero volume"

        # Clean quality_reason string
        res["quality_reason"] = res["quality_reason"].str.lstrip("; ")

        # Overall dataset classification
        fail_count = int((res["quality_status"] == "FAIL").sum())
        warning_count = int((res["quality_status"] == "WARNING").sum())
        pass_count = int((res["quality_status"] == "PASS").sum())

        if fail_count > 0:
            overall_status = "FAIL"
        elif warning_count > 0:
            overall_status = "WARNING"
        else:
            overall_status = "PASS"

        summary = {
            "total_rows": len(res),
            "overall_status": overall_status,
            "passed_count": pass_count,
            "warning_count": warning_count,
            "fail_count": fail_count,
            "reasons": reasons,
            "min_date": str(res["date"].min()) if not res.empty else None,
            "max_date": str(res["date"].max()) if not res.empty else None
        }

        return res, summary
