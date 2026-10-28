# Regime-Aware Multi-Agent LLM Framework for Explainable Alpha Factor Discovery

B.Tech final-year project, Easwari Engineering College, Chennai (October 2026).
Authors: Karthick A.R, Kavin Balaji. Guide: Santhi K, M.E.

A team of agents searches for **alpha factors** (formulas that rank stocks by expected future return) on a leakage-safe,
point-in-time panel of 192 US stocks, and a deterministic **Critic** judges every candidate.

## Pipeline

`Context Builder -> Research agent (LLM) -> Quant agent (LLM) -> Validator -> Backtester -> Attribution -> Critic -> Memory`

- **Data:** prices, SEC fundamentals (as first reported), valuation, FRED macro, walk-forward HMM market regimes, FinBERT-scored news.
- **LLM only where creativity is needed** (Research and Quant agents). Validation, backtesting, attribution and judging are plain code.
- **Backtest:** dollar-neutral rank weights, staggered monthly rebalancing, 10 bps costs, rank IC with HAC t-stats, Holm, White's reality check, deflated Sharpe, Fama-French five-factor + momentum regression.
- **Final test:** run once on a hidden window, 2025-01-01 to 2026-10-23 (454 trading days).

## Honest result

The Critic-accepted composite has rank IC +0.0068 (t 0.81), net long-short Sharpe 0.18 and FF5+Mom alpha +0.6% a year (t 0.15).
None of it is significant after multiple-testing correction (Holm p 0.62). The framework is an auditable research platform;
it is **not** a trading product and nothing here is investment advice.

## Run locally

```bash
# backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# frontend
npm install
npm run dev -- --port 3000
```

Open http://localhost:3000 and use **Guest Demo Mode** in the Workspace page. Copy `.env.example` to `.env` and fill in your own keys.

```bash
# 91 automated tests
python -m pytest -q
```

## Data

The large data files (price/news/feature panel, parquet, stored experiment lineage) are not stored in this repository.
`data/alpha/results` holds the result files used by the dashboard. See `docs/FRAMEWORK_GUIDE.md` and `NEWS_PIPELINE.md`.

## Structure

- `app/` Python backend: data engines, alpha agents (`app/alpha`), FastAPI routes
- `src/` React website (Home, Company, Services, Workspace, Contact)
- `tests/` pytest suite
- `scripts/` utilities (screenshots, discovery run scripts)
- `docs/` guides and results notes
- `supabase/schema.sql` database schema for sign-in
