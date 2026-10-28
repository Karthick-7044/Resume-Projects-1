"""Global configuration settings for the deterministic financial pipeline (Phase 1 + Phase 2)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load API keys (ALPHAVANTAGE_API_KEY, HF_TOKEN, ANTHROPIC_API_KEY, ...) from the project .env file.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:  # python-dotenv is optional; plain environment variables still work
    pass

# Data Paths
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = DATA_DIR / "config"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
UNIFIED_DATA_DIR = DATA_DIR / "unified"
REPORTS_DIR = DATA_DIR / "reports"
MANIFESTS_DIR = DATA_DIR / "manifests"
STORAGE_DIR = BASE_DIR / "storage"

# Sub-directories
RAW_MARKET_DIR = RAW_DATA_DIR / "market"
RAW_SEC_DIR = RAW_DATA_DIR / "sec"
RAW_NEWS_DIR = RAW_DATA_DIR / "news"
RAW_REGIME_DIR = RAW_DATA_DIR / "regime"
RAW_MACRO_DIR = RAW_DATA_DIR / "macro"
RAW_NEWS_AV_DIR = RAW_NEWS_DIR / "alphavantage"
RAW_NEWS_GN_DIR = RAW_NEWS_DIR / "gnews"

PROCESSED_MARKET_DIR = PROCESSED_DATA_DIR / "market"
PROCESSED_TECHNICAL_DIR = PROCESSED_DATA_DIR / "technical"
PROCESSED_FUNDAMENTALS_DIR = PROCESSED_DATA_DIR / "fundamentals"
PROCESSED_VALUATION_DIR = PROCESSED_DATA_DIR / "valuation"
PROCESSED_NEWS_DIR = PROCESSED_DATA_DIR / "news"
PROCESSED_REGIME_DIR = PROCESSED_DATA_DIR / "regime"
PROCESSED_MACRO_DIR = PROCESSED_DATA_DIR / "macro"
PROCESSED_CROSS_SECTIONAL_DIR = PROCESSED_DATA_DIR / "cross_sectional"

UNIFIED_PANEL_DIR = UNIFIED_DATA_DIR / "daily_stock_panel"

# DuckDB database file
DUCKDB_PATH = STORAGE_DIR / "quant.duckdb"

# Universe & Aliases files
UNIVERSE_FILE = CONFIG_DIR / "universe.csv"
COMPANY_ALIASES_FILE = CONFIG_DIR / "company_aliases.csv"

# Pipeline Defaults
DEFAULT_START_DATE = "2012-01-01"   # covers the FNSPID news window (2013+) with a warm-up year for 200/252-day windows
REGIME_HISTORY_START = "2010-01-01"  # long SPY history for the walk-forward HMM
DEFAULT_END_DATE = os.getenv("PIPELINE_END_DATE", "2026-10-23")   # last full trading day before the v4 rebuild
# Alpha Vantage NEWS_SENTIMENT archive coverage begins in early 2022.
DEFAULT_NEWS_START_DATE = "2022-03-01"

DATASET_VERSION = "v2.0.0"
UNIVERSE_VERSION = "v1.0.0"
REGIME_VERSION = "v2.0.0-walkforward"
PIPELINE_VERSION = "v2.0.0"

# Primary historical news source. "gnews" = in-house harvester over Google News RSS date windows
# (no API key, no quota). "alphavantage" is kept only as an independent reference source used to
# measure the harvester's completeness.
NEWS_PRIMARY_SOURCE = os.getenv("NEWS_PRIMARY_SOURCE", "gnews")
GNEWS_MIN_SECONDS_BETWEEN_CALLS = 1.2
GNEWS_WINDOW_DAYS = 7
GNEWS_TRUNCATION_ITEMS = 90   # a response this large is assumed capped (~100) and the window is split

# Alpha Vantage news provider (free tier: 25 requests/day). The provider is resumable:
# every fetched window is cached, so re-running the pipeline on later days extends coverage.
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_API_KEY")
ALPHAVANTAGE_DAILY_REQUEST_BUDGET = int(os.getenv("ALPHAVANTAGE_DAILY_REQUEST_BUDGET", "25"))
ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS = 1.5

# News point-in-time decision cutoff: articles published after 15:30 US/Eastern on day t
# are only usable from the next trading day onward.
NEWS_DECISION_CUTOFF = "15:30"
MARKET_TIMEZONE = "America/New_York"

# FinBERT (ProsusAI/finbert). "hosted" uses the Hugging Face Inference API (requires HF_TOKEN);
# "local" runs the model through transformers; "auto" prefers hosted when a token exists.
FINBERT_MODEL = "ProsusAI/finbert"
FINBERT_BACKEND = os.getenv("FINBERT_BACKEND", "auto")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")

# SEC filings are treated as usable from the first trading day AFTER filed_date,
# because EDGAR filing time-of-day is not guaranteed to precede the market close.
SEC_AVAILABILITY_LAG_DAYS = 1

# FRED macro series (public CSV endpoint, no key required); values are lagged one
# business day before use to respect publication timing.
MACRO_SERIES = {
    "DGS10": "treasury_10y",
    "DGS2": "treasury_2y",
    "T10Y2Y": "yield_curve_10y2y",
    "VIXCLS": "vix",
    "DFF": "fed_funds_rate",
}

# Phase 2 alpha-discovery configuration
ALPHA_DIR = DATA_DIR / "alpha"
ALPHA_EXPERIMENTS_DIR = ALPHA_DIR / "experiments"
ALPHA_RESULTS_DIR = ALPHA_DIR / "results"
ALPHA_TRAIN_START = "2020-01-01"
ALPHA_TRAIN_END = "2023-12-31"
ALPHA_VALID_START = "2024-01-01"
ALPHA_VALID_END = "2024-12-31"
ALPHA_TEST_START = "2025-01-01"    # untouched hold-out, evaluated once per selected factor
ALPHA_TEST_END = DEFAULT_END_DATE   # post-cutoff test: 2025-01-01 to the latest data
ALPHA_TRANSACTION_COST_BPS = 10.0  # one-way cost per unit of turnover
# Evaluation windows are kept SEPARATE by news provider period (never pooled into one headline metric):
#   "fnspid" -> FNSPID news window (<= 2023-12-31); "recent" -> Finnhub/recent window (>= 2024-01-01 is its test span)
ALPHA_WINDOWS = {
    "fnspid": {"train": ("2013-01-01", "2019-12-31"), "valid": ("2020-01-01", "2021-12-31"), "test": ("2022-01-01", "2023-12-31")},
    "recent": {"train": (ALPHA_TRAIN_START, ALPHA_TRAIN_END), "valid": (ALPHA_VALID_START, ALPHA_VALID_END),
               "test": (ALPHA_TEST_START, ALPHA_TEST_END)},
}
ALPHA_REBALANCE_DAYS = int(os.getenv("ALPHA_REBALANCE_DAYS", "5"))   # v4 discovery runs use 21 (monthly)
ALPHA_RESEARCH_BATCH = int(os.getenv("ALPHA_RESEARCH_BATCH", "4"))   # hypotheses per Research-agent call (v5: 5)
ALPHA_ATTRIBUTION = os.getenv("ALPHA_ATTRIBUTION", "loo")   # "fast" = v5 month-end regression attribution
ALPHA_NOVELTY_GATE = os.getenv("ALPHA_NOVELTY_GATE", "0") == "1"     # v4: reject formulas too similar to known factors
# --- LLM agents (Research Agent hypotheses, Quant Agent formulas). Keys come from the environment / .env only.
ALPHA_LLM_PROVIDER = os.getenv("ALPHA_LLM_PROVIDER", os.getenv("ALPHA_LLM_BACKEND", "auto"))  # auto | anthropic | gemini | groq | offline | "groq,gemini"
ALPHA_LLM_BRIEFING = os.getenv("ALPHA_LLM_BRIEFING", "full")   # "compact" = v5 two-step briefing (menu -> chosen features)
GROQ_MODEL_SMALL = os.getenv("GROQ_MODEL_SMALL", "")           # v5: model(s) for formula repairs/revisions (e.g. gpt-oss-20b)
ALPHA_LLM_STRICT = os.getenv("ALPHA_LLM_STRICT", "0") == "1"   # llm mode: never fall back to the knowledge base
ALPHA_LLM_MODE = os.getenv("ALPHA_LLM_MODE", "hybrid")   # llm = LLM only | hybrid = LLM + knowledge base | offline
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")   # set to any current Gemini model id
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Withhold tickers and calendar dates from LLM prompts (reduces recall of the LLM's own memory of market history)
ALPHA_LLM_ANONYMIZE = os.getenv("ALPHA_LLM_ANONYMIZE", "1") != "0"
ALPHA_LLM_DIR = ALPHA_DIR / "llm"                         # prompt/response cache + call log (reproducibility)
LLM_BACKEND = ALPHA_LLM_PROVIDER

# SEC EDGAR Requirements: User-Agent must be declared
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "AlphaDiscoveryResearch quant-research@alphadiscovery.org")
SEC_REQUEST_TIMEOUT = 15
SEC_MAX_RETRIES = 3

# Benchmark ticker for market regime HMM
BENCHMARK_TICKER = "SPY"

# Ensure essential directories exist
for p in [
    RAW_MARKET_DIR, RAW_SEC_DIR, RAW_NEWS_DIR, RAW_REGIME_DIR, RAW_MACRO_DIR, RAW_NEWS_AV_DIR, RAW_NEWS_GN_DIR,
    PROCESSED_MACRO_DIR, PROCESSED_CROSS_SECTIONAL_DIR,
    PROCESSED_MARKET_DIR, PROCESSED_TECHNICAL_DIR, PROCESSED_FUNDAMENTALS_DIR,
    PROCESSED_VALUATION_DIR, PROCESSED_NEWS_DIR, PROCESSED_REGIME_DIR,
    UNIFIED_PANEL_DIR, REPORTS_DIR, MANIFESTS_DIR, STORAGE_DIR,
    ALPHA_EXPERIMENTS_DIR, ALPHA_RESULTS_DIR, ALPHA_LLM_DIR
]:
    p.mkdir(parents=True, exist_ok=True)
