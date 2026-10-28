"""Point-in-Time Fundamental Feature Engine (v2).

Why v2: the v1 engine pivoted SEC facts by (period_end, filed_date) without the fact's `start`
date, so 3-month, year-to-date and annual flows were mixed and comparative-period rows from later
filings overwrote current values. In the v1 panel ~70% of revenue/EPS/ROE values were NULL.

v2 rules
1. As first reported: for every concept and reporting period, only the EARLIEST filed value is
   used. Later restatements never leak back into history.
2. Tag priority per period: the highest-priority concept available for a period is used, so a
   company that switched XBRL tags over time is still covered (mapping_status records it).
3. Quarterisation: discrete quarterly flows come from 3-month facts or, for cash-flow items that
   are only reported year-to-date, from differences of consecutive YTD facts (Q4 = FY - 9M).
   A derived quarter is available only when ALL of its inputs have been filed.
4. TTM = sum of four consecutive quarters; available when the newest of the four was filed.
5. Availability lag: a filing is usable from the first business day AFTER filed_date.
6. Split consistency: SEC per-share values and share counts are as-reported, yfinance prices are
   split-adjusted to today's basis. Per-share values are divided, and share counts multiplied, by
   the cumulative split ratio after the value's reporting basis date.
7. Missing stays missing: no zero-filling; unavailable inputs produce NULL ratios.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from app.config.settings import SEC_AVAILABILITY_LAG_DAYS

# Fiscal quarters last 12-13 weeks, but 52/53-week filers (COST, PEP, ...) have a 16-week fourth quarter (112 days).
QUARTER_MIN_DAYS, QUARTER_MAX_DAYS = 77, 120
MONETARY_UNITS = {"USD"}
PER_SHARE_METRICS = {"eps_diluted"}
SHARE_COUNT_METRICS = {"shares_outstanding", "weighted_diluted_shares"}
FLOW_METRICS = ["revenue", "net_income", "operating_income", "operating_cash_flow", "eps_diluted"]
INSTANT_METRICS = ["total_assets", "total_liabilities", "liabilities_and_equity",
                   "shareholders_equity", "cash", "debt", "shares_outstanding"]

DAILY_FUNDAMENTAL_COLUMNS = [
    "revenue", "revenue_q", "net_income", "operating_income", "operating_cash_flow", "eps",
    "total_assets", "total_liabilities", "shareholders_equity", "cash", "debt", "shares",
    "roe", "revenue_growth", "eps_growth", "net_income_growth", "asset_growth", "profit_margin",
    "operating_margin", "debt_to_equity", "debt_to_assets", "cash_to_assets", "accruals_ratio",
    "fundamental_asof_date", "fundamental_filing_date", "fundamental_available_date",
    "fundamental_period_end", "fundamental_form", "fundamental_staleness_days",
    "fundamental_mapping", "quality_status",
]


def split_factor_after(dates: pd.Series, splits: Optional[pd.DataFrame]) -> np.ndarray:
    """Cumulative split ratio of all splits strictly after each date (1.0 when none)."""
    d = pd.to_datetime(pd.Series(dates)).values
    if splits is None or splits.empty:
        return np.ones(len(d))
    sd = pd.to_datetime(splits["date"]).values
    ratios = splits["ratio"].astype(float).values
    return np.array([np.prod(ratios[sd > x]) if not pd.isna(x) else np.nan for x in d])


class FundamentalFeatureEngine:
    """Builds point-in-time daily fundamentals from standardized SEC facts."""

    # ------------------------------------------------------------------ step 1: resolve facts
    @staticmethod
    def resolve_facts(facts_df: pd.DataFrame, splits: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """First-reported, priority-resolved, split-consistent facts (one row per metric & period)."""
        if facts_df.empty:
            return pd.DataFrame()
        df = facts_df.copy()
        if "quality_status" in df.columns:
            df = df[df["quality_status"] != "FAIL"]
        for c in ["start", "period_end", "filed_date"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c])
        if "start" not in df.columns:
            df["start"] = pd.NaT
        if "tag_priority" not in df.columns:
            df["tag_priority"] = 0
        if "mapping_status" not in df.columns:
            df["mapping_status"] = "PRIMARY"
        if "taxonomy" not in df.columns:
            df["taxonomy"] = "us-gaap"

        unit_ok = (
            (df["metric"].isin(PER_SHARE_METRICS) & df["unit"].astype(str).str.contains("/shares"))
            | (df["metric"].isin(SHARE_COUNT_METRICS) & (df["unit"] == "shares"))
            | (~df["metric"].isin(PER_SHARE_METRICS | SHARE_COUNT_METRICS) & df["unit"].isin(MONETARY_UNITS))
        ) if "unit" in df.columns else pd.Series(True, index=df.index)
        df = df[unit_ok]

        key = ["ticker", "metric", "tag", "start", "period_end"]
        df = df.sort_values("filed_date").drop_duplicates(subset=key, keep="first")  # as first reported
        # Earliest filing across tags wins (PIT); tag priority only breaks same-day ties.
        df = df.sort_values(["filed_date", "tag_priority"]).drop_duplicates(
            subset=["ticker", "metric", "start", "period_end"], keep="first")

        # Split basis: cover-page (dei) counts are as of period_end; statement values as of filing.
        basis_date = np.where(df["taxonomy"].eq("dei"), df["period_end"], df["filed_date"])
        factor = split_factor_after(pd.Series(basis_date), splits)
        df["split_factor"] = factor
        per_share = df["metric"].isin(PER_SHARE_METRICS).values
        shares = df["metric"].isin(SHARE_COUNT_METRICS).values
        df.loc[per_share, "value"] = df.loc[per_share, "value"].values / factor[per_share]
        df.loc[shares, "value"] = df.loc[shares, "value"].values * factor[shares]
        return df.sort_values(["ticker", "metric", "period_end"]).reset_index(drop=True)

    # ------------------------------------------------------------------ step 2: quarterise flows
    @staticmethod
    def quarterize(flow: pd.DataFrame) -> pd.DataFrame:
        """Discrete quarterly values from 3-month facts plus YTD differences.

        Args:
            flow: rows for ONE ticker and ONE duration metric with start, period_end, value, filed_date.
        Returns:
            DataFrame[period_end, q_start, value, filed_date, form, mapping_status, derived]
        """
        if flow.empty:
            return pd.DataFrame()
        f = flow.dropna(subset=["start"]).copy()
        f["days"] = (f["period_end"] - f["start"]).dt.days + 1
        quarters: Dict[pd.Timestamp, Dict] = {}

        for _, r in f[(f["days"] >= QUARTER_MIN_DAYS) & (f["days"] <= QUARTER_MAX_DAYS)].iterrows():
            quarters[r["period_end"]] = {"period_end": r["period_end"], "q_start": r["start"],
                                         "value": r["value"], "filed_date": r["filed_date"],
                                         "form": r.get("form"), "mapping_status": r.get("mapping_status"),
                                         "derived": False}

        # Year-to-date chains share a start date; consecutive members differ by one quarter.
        for _, grp in f[f["days"] >= QUARTER_MIN_DAYS].groupby("start"):
            grp = grp.sort_values("period_end")
            rows = grp.to_dict("records")
            for prev, cur in zip(rows, rows[1:]):
                q_days = (cur["period_end"] - prev["period_end"]).days
                if not QUARTER_MIN_DAYS <= q_days <= QUARTER_MAX_DAYS or cur["period_end"] in quarters:
                    continue
                quarters[cur["period_end"]] = {
                    "period_end": cur["period_end"], "q_start": prev["period_end"] + pd.Timedelta(days=1),
                    "value": cur["value"] - prev["value"],
                    "filed_date": max(prev["filed_date"], cur["filed_date"]),
                    "form": cur.get("form"), "mapping_status": cur.get("mapping_status"), "derived": True,
                }
        if not quarters:
            return pd.DataFrame()
        return pd.DataFrame(sorted(quarters.values(), key=lambda x: x["period_end"])).reset_index(drop=True)

    @staticmethod
    def ttm(quarters: pd.DataFrame) -> pd.DataFrame:
        """Trailing-twelve-month sums over four consecutive quarters (+ YoY growth of the TTM)."""
        if quarters.empty or len(quarters) < 4:
            return pd.DataFrame()
        q = quarters.sort_values("period_end").reset_index(drop=True)
        out = []
        for i in range(3, len(q)):
            window = q.iloc[i - 3:i + 1]
            span = (window["period_end"].iloc[-1] - window["period_end"].iloc[0]).days
            if not 250 <= span <= 300:  # a gap in the quarterly chain -> no TTM
                continue
            out.append({"period_end": q.loc[i, "period_end"], "value": window["value"].sum(),
                        "quarter_value": q.loc[i, "value"], "filed_date": window["filed_date"].max(),
                        "form": q.loc[i, "form"], "mapping_status": q.loc[i, "mapping_status"]})
        t = pd.DataFrame(out)
        if t.empty:
            return t
        # YoY growth: compare with the TTM whose period ended ~1 year earlier (both already filed).
        t = t.sort_values("period_end").reset_index(drop=True)
        prior = pd.merge_asof(
            t[["period_end"]].assign(target=t["period_end"] - pd.Timedelta(days=365)),
            t[["period_end", "value"]].rename(columns={"period_end": "prior_end", "value": "prior_value"}),
            left_on="target", right_on="prior_end", direction="nearest", tolerance=pd.Timedelta(days=20))
        valid = prior["prior_value"].notna() & (prior["prior_value"].abs() > 0)
        t["yoy_growth"] = np.where(valid, t["value"] / prior["prior_value"].where(valid) - 1.0, np.nan)
        # Sign changes (e.g. loss -> profit) make ratios meaningless
        t.loc[valid & (np.sign(t["value"]) != np.sign(prior["prior_value"])), "yoy_growth"] = np.nan
        return t

    # ------------------------------------------------------------------ step 3: PIT metric table
    @classmethod
    def build_pit_records(cls, resolved: pd.DataFrame,
                          lag_days: int = SEC_AVAILABILITY_LAG_DAYS) -> pd.DataFrame:
        """Long table: ticker, feature, period_end, available_date, value, form, filed_date, mapping."""
        if resolved.empty:
            return pd.DataFrame()
        recs: List[pd.DataFrame] = []
        for (ticker, metric), grp in resolved.groupby(["ticker", "metric"]):
            if metric in FLOW_METRICS:
                q = cls.quarterize(grp)
                t = cls.ttm(q)
                if t.empty:
                    continue
                name = "eps" if metric == "eps_diluted" else metric
                base = t[["period_end", "filed_date", "form", "mapping_status"]]
                recs.append(base.assign(ticker=ticker, feature=name, value=t["value"]))
                recs.append(base.assign(ticker=ticker, feature=f"{name}_growth", value=t["yoy_growth"]))
                if metric == "revenue":
                    recs.append(base.assign(ticker=ticker, feature="revenue_q", value=t["quarter_value"]))
            elif metric == "weighted_diluted_shares":
                # Share counts are averages, not additive: use the value of each period as-is.
                g = grp.sort_values(["period_end", "filed_date"]).drop_duplicates("period_end", keep="first")
                recs.append(g[["period_end", "filed_date", "form", "mapping_status"]].assign(
                    ticker=ticker, feature="weighted_diluted_shares", value=g["value"].values))
            else:
                g = grp.drop_duplicates("period_end", keep="first")
                recs.append(g[["period_end", "filed_date", "form", "mapping_status"]].assign(
                    ticker=ticker, feature=metric, value=g["value"].values))
        if not recs:
            return pd.DataFrame()
        out = pd.concat(recs, ignore_index=True)
        out["available_date"] = pd.to_datetime(out["filed_date"]) + BDay(lag_days)

        # Asset growth from the instant asset series
        ta = out[out["feature"] == "total_assets"].sort_values("period_end")
        growth = []
        for ticker, g in ta.groupby("ticker"):
            g = g.sort_values("period_end").reset_index(drop=True)
            prior = pd.merge_asof(g[["period_end"]].assign(target=g["period_end"] - pd.Timedelta(days=365)),
                                  g[["period_end", "value"]].rename(columns={"period_end": "pe", "value": "pv"}),
                                  left_on="target", right_on="pe", direction="nearest",
                                  tolerance=pd.Timedelta(days=20))
            gg = g.copy()
            gg["value"] = np.where(prior["pv"] > 0, g["value"] / prior["pv"] - 1.0, np.nan)
            gg["feature"] = "asset_growth"
            growth.append(gg)
        if growth:
            out = pd.concat([out] + growth, ignore_index=True)
        return out.sort_values(["ticker", "feature", "available_date"]).reset_index(drop=True)

    # ------------------------------------------------------------------ step 4: daily alignment
    @classmethod
    def align_to_daily_market(cls, market_dates_df: pd.DataFrame, pit_records: pd.DataFrame) -> pd.DataFrame:
        """As-of join: for each (date, ticker) the newest period whose available_date <= date."""
        if market_dates_df.empty:
            return pd.DataFrame()
        base = market_dates_df[["date", "ticker"]].copy()
        base["date"] = pd.to_datetime(base["date"])
        base = base.sort_values("date").reset_index(drop=True)
        if pit_records.empty:
            for c in DAILY_FUNDAMENTAL_COLUMNS:
                base[c] = np.nan
            base["quality_status"] = "NO_FILING_YET"
            base["date"] = base["date"].dt.date
            return base

        frames = []
        for ticker, m in base.groupby("ticker"):
            m = m.sort_values("date").reset_index(drop=True)
            recs = pit_records[pit_records["ticker"] == ticker]
            meta_parts = []
            for feature, g in recs.groupby("feature"):
                g = g.sort_values(["available_date", "period_end"])
                # Keep only records that advance the reporting period (older periods filed late are ignored)
                g = g[g["period_end"] >= g["period_end"].cummax()].drop_duplicates("available_date", keep="last")
                j = pd.merge_asof(m[["date"]], g[["available_date", "value", "period_end", "filed_date", "form",
                                                  "mapping_status"]],
                                  left_on="date", right_on="available_date", direction="backward")
                m[feature] = j["value"].values
                if feature == "revenue":
                    meta_parts = j
                if feature in ("operating_income", "shareholders_equity", "cash") and len(g):
                    m[f"_map_{feature}"] = j["mapping_status"].values
            if len(meta_parts):
                m["fundamental_period_end"] = meta_parts["period_end"].values
                m["fundamental_filing_date"] = meta_parts["filed_date"].values
                m["fundamental_available_date"] = meta_parts["available_date"].values
                m["fundamental_form"] = meta_parts["form"].values
            frames.append(m)

        df = pd.concat(frames, ignore_index=True)
        for c in ["revenue", "revenue_q", "net_income", "operating_income", "operating_cash_flow", "eps",
                  "total_assets", "total_liabilities", "liabilities_and_equity", "shareholders_equity",
                  "cash", "debt", "shares_outstanding", "weighted_diluted_shares", "revenue_growth",
                  "eps_growth", "net_income_growth", "asset_growth", "fundamental_period_end",
                  "fundamental_filing_date", "fundamental_available_date", "fundamental_form"]:
            if c not in df.columns:
                df[c] = np.nan

        # Fallbacks (documented, mapping recorded)
        df["total_liabilities"] = df["total_liabilities"].fillna(df["liabilities_and_equity"] - df["shareholders_equity"])
        df["shares"] = df["shares_outstanding"].fillna(df["weighted_diluted_shares"])

        eq = df["shareholders_equity"].where(df["shareholders_equity"] > 0)
        rev = df["revenue"].where(df["revenue"] > 0)
        ta = df["total_assets"].where(df["total_assets"] > 0)
        df["roe"] = df["net_income"] / eq
        df["profit_margin"] = df["net_income"] / rev
        df["operating_margin"] = df["operating_income"] / rev
        df["debt_to_equity"] = df["debt"] / eq
        df["debt_to_assets"] = df["debt"] / ta
        df["cash_to_assets"] = df["cash"] / ta
        df["accruals_ratio"] = (df["net_income"] - df["operating_cash_flow"]) / ta

        df["fundamental_asof_date"] = df["date"].dt.date
        df["fundamental_staleness_days"] = (df["date"] - pd.to_datetime(df["fundamental_available_date"])).dt.days
        map_cols = [c for c in df.columns if c.startswith("_map_")]
        df["fundamental_mapping"] = df[map_cols].apply(
            lambda r: ";".join(f"{c[5:]}:{v}" for c, v in r.items() if isinstance(v, str) and v != "PRIMARY"),
            axis=1) if map_cols else ""
        core = df[["revenue", "net_income", "shareholders_equity", "shares"]].notna()
        df["quality_status"] = np.select(
            [core.all(axis=1) & (df["fundamental_staleness_days"] <= 200), core.any(axis=1)],
            ["PASS", "PARTIAL"], default="NO_FILING_YET")
        df.loc[core.all(axis=1) & (df["fundamental_staleness_days"] > 200), "quality_status"] = "STALE"

        for c in ["fundamental_period_end", "fundamental_filing_date", "fundamental_available_date"]:
            df[c] = pd.to_datetime(df[c]).dt.date
        df["date"] = df["date"].dt.date
        keep = ["date", "ticker"] + [c for c in DAILY_FUNDAMENTAL_COLUMNS if c in df.columns]
        return df[keep].sort_values(["date", "ticker"]).reset_index(drop=True)

    # ------------------------------------------------------------------ convenience
    @classmethod
    def build_daily(cls, market_dates_df: pd.DataFrame, facts_df: pd.DataFrame,
                    splits_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Facts (all tickers) + splits (all tickers) -> daily PIT fundamentals."""
        if facts_df.empty:
            return cls.align_to_daily_market(market_dates_df, pd.DataFrame())
        resolved = []
        for ticker, g in facts_df.groupby("ticker"):
            sp = splits_df[splits_df["ticker"] == ticker] if splits_df is not None and not splits_df.empty else None
            resolved.append(cls.resolve_facts(g, sp))
        pit = cls.build_pit_records(pd.concat(resolved, ignore_index=True))
        return cls.align_to_daily_market(market_dates_df, pit)
