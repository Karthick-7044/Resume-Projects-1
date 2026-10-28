"""SEC EDGAR Data Provider and standardized XBRL facts extraction.

Phase 2 corrections
- Every fact keeps its `start` date (duration facts) and accession number, so quarterly,
  year-to-date and annual values can be told apart downstream.
- Raw companyfacts JSON is retained (gzip) for provenance and offline rebuilds.
- Ticker -> CIK is resolved dynamically from SEC's company_tickers.json; the static map is
  only an offline fallback.
- Concepts are resolved through a primary/fallback hierarchy that includes bank-specific tags
  (e.g. JPM reports revenue net of interest expense and has no operating-income concept).
"""
import gzip
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from app.config.settings import (
    CONFIG_DIR,
    RAW_SEC_DIR,
    SEC_USER_AGENT,
    SEC_REQUEST_TIMEOUT,
    SEC_MAX_RETRIES,
)
from app.data.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)

# Offline fallback CIKs for the configured universe (used only if company_tickers.json is unavailable).
DEFAULT_CIK_MAP: Dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "JPM": "0000019617",
    "V": "0001403161",
    "XOM": "0000034088",
    "JNJ": "0000200406",
}

# Canonical metric -> ordered list of (taxonomy, concept). Earlier entries have priority; the
# fundamental engine resolves priority per reporting period, so a company that switched tags
# over time is still covered. "kind" tells the engine whether the metric is a flow (duration)
# or a balance (instant) item.
XBRL_METRIC_TAGS: Dict[str, Dict[str, Any]] = {
    "revenue": {"kind": "duration", "tags": [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
        ("us-gaap", "SalesRevenueGoodsNet"),            # pre-ASC-606 tag used by JNJ, KO and other goods sellers
        ("us-gaap", "SalesRevenueServicesNet"),
        ("us-gaap", "RevenuesNetOfInterestExpense"),          # banks (JPM)
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ]},
    "net_income": {"kind": "duration", "tags": [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
        ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic"),
    ]},
    "operating_income": {"kind": "duration", "tags": [
        ("us-gaap", "OperatingIncomeLoss"),
        # Banks do not report operating income; pre-tax income is used as a documented proxy.
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
    ]},
    "operating_cash_flow": {"kind": "duration", "tags": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ]},
    "eps_diluted": {"kind": "duration", "tags": [
        ("us-gaap", "EarningsPerShareDiluted"),
        ("us-gaap", "EarningsPerShareBasicAndDiluted"),
        ("us-gaap", "EarningsPerShareBasic"),
    ]},
    "total_assets": {"kind": "instant", "tags": [("us-gaap", "Assets")]},
    "total_liabilities": {"kind": "instant", "tags": [("us-gaap", "Liabilities")]},
    "liabilities_and_equity": {"kind": "instant", "tags": [("us-gaap", "LiabilitiesAndStockholdersEquity")]},
    "shareholders_equity": {"kind": "instant", "tags": [
        ("us-gaap", "StockholdersEquity"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ]},
    "cash": {"kind": "instant", "tags": [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ("us-gaap", "CashAndDueFromBanks"),                    # banks (JPM)
    ]},
    "debt": {"kind": "instant", "tags": [
        ("us-gaap", "LongTermDebt"),
        ("us-gaap", "LongTermDebtNoncurrent"),
        ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
    ]},
    "shares_outstanding": {"kind": "instant", "tags": [
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ]},
    # Fallback share count for multi-class issuers whose outstanding shares are only reported
    # dimensionally (e.g. META class A/B), which the companyfacts API omits.
    "weighted_diluted_shares": {"kind": "duration", "tags": [
        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
        ("us-gaap", "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"),
    ]},
}

ALLOWED_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}


class SECDataProvider(ABC):
    """Abstract base class for SEC EDGAR data providers."""

    @abstractmethod
    def fetch_company_facts(self, ticker: str, force_refresh: bool = False) -> pd.DataFrame:
        """Fetches raw structured facts for a given ticker."""


class EdgarSECDataProvider(SECDataProvider):
    """Fetches XBRL company facts from SEC EDGAR with raw JSON retention and Parquet caching."""

    FACTS_SCHEMA_VERSION = "v2"

    def __init__(
        self,
        raw_dir: Path = RAW_SEC_DIR,
        user_agent: str = SEC_USER_AGENT,
        timeout: int = SEC_REQUEST_TIMEOUT,
        max_retries: int = SEC_MAX_RETRIES
    ):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.cik_cache: Dict[str, str] = dict(DEFAULT_CIK_MAP)
        self.cik_source: Dict[str, str] = {t: "STATIC_FALLBACK" for t in DEFAULT_CIK_MAP}
        self._load_cik_mapping()

    def _ingest_ticker_map(self, data: Dict[str, Any]):
        for item in data.values():
            sym = str(item.get("ticker", "")).upper()
            cik = str(item.get("cik_str", "")).zfill(10)
            if sym and cik.strip("0"):
                self.cik_cache[sym] = cik
                self.cik_source[sym] = "SEC_COMPANY_TICKERS"

    def _load_cik_mapping(self):
        """Loads SEC's ticker->CIK master list (cached locally), falling back to the static map."""
        cik_file = self.raw_dir / "company_tickers.json"
        if cik_file.exists():
            try:
                self._ingest_ticker_map(json.loads(cik_file.read_text()))
                return
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not load local CIK mapping: {e}")
        try:
            resp = requests.get("https://www.sec.gov/files/company_tickers.json",
                                headers={"User-Agent": self.user_agent}, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                cik_file.write_text(json.dumps(data))
                self._ingest_ticker_map(data)
        except requests.RequestException as e:
            logger.info(f"Using static CIK fallback ({e})")

    def get_cik(self, ticker: str) -> Optional[str]:
        """Returns the 10-digit zero-padded CIK of the ticker's CURRENT registrant."""
        return self.cik_cache.get(ticker.upper())

    def get_cik_lineage(self, ticker: str) -> List[str]:
        """All registrant CIKs for a ticker: current registrant plus predecessors from cik_history.csv."""
        ticker = ticker.upper()
        ciks: List[str] = []
        history_file = CONFIG_DIR / "cik_history.csv"
        if history_file.exists():
            hist = pd.read_csv(history_file, comment="#", dtype=str)
            ciks.extend(c.zfill(10) for c in hist.loc[hist["ticker"].str.upper() == ticker, "cik"])
        current = self.get_cik(ticker)
        if current and current not in ciks:
            ciks.append(current)
        return ciks

    def _raw_json_path(self, ticker: str, cik: str) -> Path:
        return self.raw_dir / f"{ticker}_CIK{cik}_companyfacts.json.gz"

    def _download_facts_json(self, ticker: str, cik: str) -> Optional[Dict[str, Any]]:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(0.15)  # SEC fair-access guideline: <= 10 requests/second
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    logger.warning(f"SEC rate limit hit (429) for {ticker}. Backing off...")
                    time.sleep(2.0 * attempt)
                else:
                    logger.warning(f"SEC API returned status {resp.status_code} for {ticker}")
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"SEC API request error (attempt {attempt}/{self.max_retries}): {e}")
                time.sleep(1.0 * attempt)
        return None

    def fetch_company_facts(self, ticker: str, force_refresh: bool = False, reparse: bool = False) -> pd.DataFrame:
        """Returns standardized facts for a ticker, downloading companyfacts JSON when needed.
        reparse=True rebuilds the parsed table from the saved raw JSON (no network), e.g. after a tag-map change."""
        ticker = ticker.strip().upper()
        cache_path = self.raw_dir / f"{ticker}_facts.parquet"

        if cache_path.exists() and not force_refresh and not reparse:
            cached_df = ParquetStore.read(cache_path)
            if not cached_df.empty and "start" in cached_df.columns:
                return cached_df

        ciks = self.get_cik_lineage(ticker)
        if not ciks:
            logger.error(f"No CIK found for ticker {ticker}")
            return pd.DataFrame()

        frames = []
        for cik in ciks:
            raw_path = self._raw_json_path(ticker, cik)
            if raw_path.exists() and not force_refresh:
                facts_json = json.loads(gzip.decompress(raw_path.read_bytes()))
            else:
                facts_json = self._download_facts_json(ticker, cik)
                if facts_json:
                    raw_path.write_bytes(gzip.compress(json.dumps(facts_json).encode("utf-8")))
            if not facts_json:
                logger.error(f"Failed to fetch SEC facts for {ticker} (CIK {cik})")
                continue
            parsed = self.parse_sec_facts_json(ticker, cik, facts_json)
            if not parsed.empty:
                parsed["entity_name"] = facts_json.get("entityName", "")
                frames.append(parsed)

        if not frames:
            return pd.DataFrame()
        facts_df = pd.concat(frames, ignore_index=True)
        ParquetStore.write(facts_df, cache_path)
        return facts_df

    @staticmethod
    def parse_sec_facts_json(ticker: str, cik: str, data: Dict[str, Any]) -> pd.DataFrame:
        """Extracts every mapped concept (all periods, all filings) from a companyfacts payload."""
        facts = data.get("facts", {})
        retrieved_at = datetime.utcnow()
        source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        records: List[Dict[str, Any]] = []

        for metric, spec in XBRL_METRIC_TAGS.items():
            for priority, (taxonomy, tag) in enumerate(spec["tags"]):
                tag_data = facts.get(taxonomy, {}).get(tag)
                if not tag_data:
                    continue
                for unit_key, items in tag_data.get("units", {}).items():
                    for item in items:
                        form = str(item.get("form", "")).upper()
                        if form not in ALLOWED_FORMS:
                            continue
                        val, end, filed = item.get("val"), item.get("end"), item.get("filed")
                        if val is None or not end or not filed:
                            continue
                        start = item.get("start")
                        fy = item.get("fy")
                        records.append({
                            "ticker": ticker,
                            "cik": cik,
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "metric": metric,
                            "metric_kind": spec["kind"],
                            "tag_priority": priority,
                            "mapping_status": "PRIMARY" if priority == 0 else "FALLBACK",
                            "value": float(val),
                            "unit": unit_key,
                            "start": pd.to_datetime(start).date() if start else None,
                            "period_end": pd.to_datetime(end).date(),
                            "filed_date": pd.to_datetime(filed).date(),
                            "accn": item.get("accn"),
                            "fiscal_period": item.get("fp", ""),
                            "fiscal_year": int(fy) if fy is not None and str(fy).isdigit() else None,
                            "form": form,
                            "frame": item.get("frame", ""),
                            "source_url": source_url,
                            "retrieved_at": retrieved_at,
                        })

        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # Exact duplicates (same concept, period, filing) are dropped; comparative-period rows from
        # later filings are kept here and resolved "as first reported" by the fundamental engine.
        df = df.drop_duplicates(subset=["tag", "unit", "start", "period_end", "accn", "value"]).reset_index(drop=True)
        return df.sort_values(["metric", "period_end", "filed_date"]).reset_index(drop=True)
