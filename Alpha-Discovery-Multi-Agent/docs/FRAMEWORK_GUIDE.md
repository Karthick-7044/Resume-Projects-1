# Framework guide: how everything works and where every file is

The project folder is called **P** below:
`C:\Users\hp\Downloads\final-year project (2)\final-year project`

Everything is explained in simple words. Each section says **what** a part does, **how** it does it, and **where** its files are.

---

## Part A. The big picture (one minute)

1. **We collect data** about 192 large US companies, one row per company per day, 2012–2025:
   - prices;
   - company accounts from SEC filings;
   - news headlines scored by FinBERT;
   - market mood (bull, bear or volatile);
   - interest rates.
2. **We describe that data to an AI "Research agent"**, without company names or dates. It proposes an idea, for example "profitable companies do better when the market is calm".
3. **A "Quant agent" turns the idea into a formula**, for example `cs_rank(roe) * (1 - regime_high_vol)`.
4. **Code checks the formula** (Validator). It then **tests it on history** (Backtester), **explains it** (Attribution) and **judges it** (Critic).
5. **Failed formulas are sent back to be fixed**, up to 2 times. **Everything is remembered** (Memory).
6. **At the end we test honestly**: years the agents never saw, correction for trying many formulas, trading costs, and comparison with known factors.

---

## Part B. The data and how it is joined

### B1. Prices and technical features
- **What:** daily open, high, low, close and volume, 2012–2025, from Yahoo Finance.
- **How:** downloaded once and cached. Quality checks look for missing days, negative prices and strange jumps. From prices we compute momentum (5, 20, 60 days and 12-month-minus-1-month), volatility, RSI, MACD and moving averages. All windows look **backwards only**.
- **Files:**
  - `P\app\data\providers\market_provider.py` (download)
  - `P\app\data\qa\market_qa.py` (checks)
  - `P\app\features\technical.py` (features)
  - `P\data\raw\market\*.parquet` (cached prices)

### B2. Company accounts (SEC EDGAR)
- **What:** revenue, net income, EPS, cash flow, debt, equity and more, from official SEC XBRL filings.
- **How:** for every number we keep the value **as first reported**, so later corrections cannot leak into the past. Quarterly values are built from year-to-date reports. A filing is usable only **from the next business day** after its filing date. Ratios include ROE, margins, growth, debt ratios and accruals. Valuation ratios (P/E, P/B, earnings yield and others) use a split-consistent share count.
- **Files:**
  - `P\app\data\providers\sec_provider.py` (download)
  - `P\app\features\fundamentals.py`
  - `P\app\features\valuation.py`
  - `P\data\raw\sec\*.json.gz` (raw filings)

### B3. Market regime and macro
- **What:** each day is labelled Bull / Low-vol, Bear / High-vol or Sideways. We also use the 10-year and 2-year Treasury yields, the yield curve, the VIX and the Fed funds rate.
- **How:** a hidden Markov model is re-fitted every 21 days using **only past data**, so the label on day t never uses information after t. Macro values are used **one day late**, to respect publication timing.
- **Files:**
  - `P\app\models\regime.py`
  - `P\app\data\providers\macro_provider.py`
  - `P\app\features\macro_features.py`

### B4. The news layer and FinBERT (in detail)
1. **Where the news comes from**
   - **2013–2023: FNSPID**, a public research dataset of about 15.7 million finance news records. Its files are huge (29 GB), so we never download them whole. We stream them in pieces over the internet and keep only rows for our 192 companies. **725,193 headlines** were kept.
   - **2024–2025: Google News RSS (new).** FNSPID stops at the end of 2023, and the free Finnhub tier only gives recent months. So we built a **free harvester**: for each company and each 2-week window it asks Google News for headlines. It is a *sample* of at most about 100 headlines per 2 weeks per company, and it is labelled as a separate source so it is never confused with FNSPID.
   - **Finnhub:** recent data only (since about October 2025), kept for daily updates.
2. **Cleaning:** we drop empty titles, non-English rows and exact duplicates. We tag the article type (earnings, analyst rating, M&A, product) using keyword rules. Relevance is 1.0 if the title names the company, otherwise 0.3.
3. **FinBERT (what it does):** FinBERT is a language model trained on finance text. For each headline it outputs three probabilities: positive, negative and neutral. Our sentiment score is **P(positive) − P(negative)**, a number between −1 and +1. Each unique headline is scored once and cached. We checked FinBERT on the Financial PhraseBank: 97.2% accuracy on sentences that all annotators agreed on.
4. **Point-in-time rule:** a headline published after 16:00 New York time, on a weekend or with no exact time, counts **from the next trading day**. News can therefore be delayed, but never used early.
5. **Daily news features** per company and day:
   - news count;
   - average and time-decayed sentiment (half-life 3 days);
   - sentiment surprise and news-volume surprise (compared with the previous 20 days);
   - sentiment momentum;
   - sentiment dispersion;
   - sentiment of earnings news and of analyst news.
6. **Coverage (why some cells are empty):** a company-year counts as covered only if it has at least 20 FNSPID articles. Outside coverage, every news value is **empty (NULL) on purpose**, never zero, because "no data" is not "no news". The website now shows **"no coverage"** instead of a blank.
7. **Why the website showed empty news values (fixed):**
   - **Missing years:** 2024–2025 had no news source. Now fixed by adding Google News; this goes live when the panel is rebuilt.
   - **Wrong column:** the panel page displayed `avg_av_sentiment`, an old Alpha Vantage column that is always empty, instead of the FinBERT sentiment. It now shows FinBERT sentiment, decayed sentiment and the news source.
- **Files:**
  - `P\app\data\providers\fnspid_provider.py` (FNSPID streaming)
  - `P\app\pipeline\fetch_fnspid.py` and `P\app\pipeline\fetch_fnspid_extra.py`
  - `P\app\pipeline\build_fnspid_news.py`
  - `P\app\data\providers\gnews_provider.py` (Google News harvester)
  - `P\app\pipeline\harvest_news_recent.py` and `P\app\pipeline\build_gnews_recent.py` (2024–25)
  - `P\app\nlp\finbert.py` and `P\app\nlp\news_scoring.py` (FinBERT)
  - `P\app\features\news_pit.py` (timing rule)
  - `P\app\features\news_features.py` (daily features)
  - `P\app\pipeline\news_pipeline.py` (puts it all together)
  - `P\data\config\news.yaml` (all thresholds)
  - Data: `P\data\raw\news\*_news.parquet` (FNSPID), `P\data\raw\news\gnews_recent\` (Google News), `P\data\processed\news\finbert_text_cache.parquet` (FinBERT scores)

### B5. Joining everything into one table
- **How:** all of the above are joined on **date + company**. The result is 675,233 rows × 181 columns for 192 stocks. Labels (future returns) are kept in a separate table, so formulas can never read them.
- **Files:**
  - `P\app\pipeline\orchestrator.py` (runs the whole data pipeline)
  - `P\app\pipeline\panel_builder.py`
  - `P\app\features\registry.py` (list of the 112 features each agent may use, with the source and timing of each)
  - Output: `P\data\unified\daily_stock_panel\master_panel.parquet`, also stored in `P\storage\quant.duckdb`

---

## Part C. How the mixed data reaches the Research agent (and whether it is correct)

The Research agent does **not** receive raw numbers. Raw data would be far too big, and with names and dates the model could "remember" what happened, which is cheating. Instead it receives a **briefing**. The exact briefing is visible on the website under **Agent Loop → "What the Research agent receives"**. It contains:

1. **The research question:** "find factors whose higher values predict higher next-period returns".
2. **The universe:** "192 large-cap US stocks (names withheld)".
3. **The sample size:** "about 7 years of training and 2 years of validation (dates withheld). A later period exists but is hidden."
4. **The allowed data domains:** technical, fundamental, valuation, cross-sectional, news, regime and macro.
5. **The market mood mix in training**, for example Bull 78%, Bear 17%, Sideways 5%.
6. **A feature catalogue:** every feature, grouped by domain, with its meaning and **real coverage**, for example `accruals_ratio: Accruals (earnings quality) (coverage 98%)`. Sparse features are flagged.
7. **Memory:** how many formulas were tested and accepted, which domains are under-tested, accepted factors so far, and **recent failures with the Critic's reasons**.
8. **Rules:**
   - each idea must name a published mechanism;
   - each idea must **combine at least two data domains**;
   - no company names, no years after 2019 and no specific events (checked in code, and broken ideas are rejected).

**Is it correct?** Yes. The live example from the Groq run contains all seven domains with correct coverage numbers, and the model's answers combine domains as required (fundamental + regime, technical + macro, valuation + news).

**Files:**
- `P\app\alpha\agents.py` (ContextBuilder builds the briefing; ResearchAgent and QuantAgent)
- `P\app\alpha\prompts.py` (the exact wording)
- `P\app\alpha\llm.py` (Groq / Gemini / Claude clients, cache, rules)
- `P\data\config\research_priors.md` (editable notes for the agent)
- `P\data\alpha\llm\cache\` and `P\data\alpha\llm\calls.jsonl` (every prompt and answer is saved)

---

## Part D. Every role in the agent loop

| Role | What it does | How | File |
|---|---|---|---|
| Research agent | Proposes ideas (hypotheses) | LLM reads the briefing above and returns title, mechanism, literature, domains and expected sign | `P\app\alpha\agents.py`, `prompts.py`, `llm.py` |
| Quant agent | Writes formulas | LLM turns each idea into up to 3 formulas in a safe factor language; it repairs a rejected formula using the validator's error message | `P\app\alpha\agents.py`, `llm.py`, `dsl.py` |
| Factor language | Safe formulas | Operators such as cs_rank, ts_mean and if_else. Every time-series operator looks backwards. Parsed node by node, never run with `eval` | `P\app\alpha\dsl.py` |
| Validator | Blocks bad formulas | Checks syntax, known features only, windows 1–252, no negative lags, no labels, enough coverage, originality versus earlier formulas | `P\app\alpha\validator.py`, `similarity.py` |
| Backtester | Tests on history | See Part E | `P\app\alpha\backtester.py` |
| Attribution | Explains the formula | Replaces one feature at a time with its daily average and measures the drop in IC, so you can see which data really matters. Also measures similarity to known styles (momentum, value, low volatility, size, quality) | `P\app\alpha\attribution.py` |
| Critic agent | Judges | See Part F | `P\app\alpha\critic.py` |
| Memory | Remembers | Stores every attempt with its idea, formula, validation, metrics, attribution, Critic reasons, verdict, parent and source. Feeds a summary into the next briefing | `P\app\alpha\memory.py`, `P\data\alpha\experiments\*.json`, DuckDB table `alpha_experiments` |
| Loop controller | Order of steps | LangGraph state machine: context → research → quant → validate → backtest → attribution → critic → memory → (refine or next idea) | `P\app\alpha\graph.py` |

**Why LangGraph and not plain LangChain?** Our process is a loop. When the Critic says "fix it", we go back to the Quant agent, then test again. LangGraph is built for loops and branches. LangChain chains run in a straight line. LangGraph comes from the same team.

**Refinement (what you proposed):** when the Critic says REVISE or REJECT:
- its written reasons are stored in memory and sent to the Quant agent, which writes an improved formula;
- this happens **up to 2 times per idea**, and each attempt is saved and linked to its parent;
- leakage failures are not "repaired", and flipping a formula's sign after seeing bad results is not allowed (that would be cheating).

Code: `refinable()` and `refinement_actions()` in `P\app\alpha\graph.py`. Tests: `P\tests\test_critic_refinement.py`.

---

## Part E. How backtesting works (step by step)

Take a formula, for example `cs_rank(momentum_252_21d)` (stocks that rose most over the past year, skipping the last month).

1. **Score:** on each trading day the formula gives every stock a number, using only data known at that day's close.
2. **Rank:** convert the scores to ranks from 0 to 1 across the 192 stocks. At least 5 stocks with a value are needed that day.
3. **Weights (dollar-neutral):** weight = (rank − average rank) ÷ (sum of absolute differences). Stocks above average are bought, stocks below average are sold short, and both sides are equal in money. Total gross exposure is 1.
4. **Timing:** the weights decided at day t's close earn the return from close t to close t+1.
5. **Rebalance:** every 5 trading days (21 and 63 were also tested). Weights are held in between. In the final tests every possible rebalance day is averaged ("staggered"), so no lucky day is picked.
6. **Costs:** 10 bps (0.10%) per unit of weight traded. We also report 0, 5, 20 and 50 bps.
7. **Measurements:**
   - **Rank IC:** the daily correlation between today's ranks and tomorrow's returns. The main "does it predict?" number. We report its mean, its t-statistic and its value per year.
   - **Sharpe ratio:** yearly return ÷ yearly volatility, after costs.
   - Max drawdown, turnover, hit rate, results per market regime, and how much of the profit comes from one stock.
8. **Data splits:** agents see only **training (2013–2019)** and **validation (2020–2021)**. The test years are hidden and used once. The final honest tests use:
   - **walk-forward:** for each year 2016–2023, choose formulas using only earlier years, then test on that year;
   - the **untouched 2024–2025 hold-out**.

**Does it follow quant research standards?** Yes:
- point-in-time data and no look-ahead (with automated leakage tests);
- transaction costs;
- out-of-sample and walk-forward testing;
- multiple-testing correction (Holm, White's reality check, deflated Sharpe ratio);
- a random-selection baseline;
- Fama-French 5 + momentum factor regressions;
- reported failures.

This is above what is usual for a student project and close to academic practice.

**Files:**
- `P\app\alpha\backtester.py`
- `P\app\alpha\walkforward.py`
- `P\app\alpha\cost_aware.py`
- `P\app\alpha\library_tests.py`
- `P\app\alpha\ff_attribution.py`
- `P\app\alpha\stats.py` (deflated Sharpe)
- `P\app\alpha\phase_sensitivity.py`

---

## Part F. The Critic's rules and thresholds (exact)

| # | Check | PASS / WARN / FAIL rule |
|---|---|---|
| 1 | Leakage | FAIL if training IC above 0.15 or Sharpe above 4 (too good to be true); WARN if the validator warned |
| 2 | Plausibility | FAIL if training IC ≤ 0 (contradicts the idea); WARN if below 0.005 |
| 3 | Stability | FAIL if the IC changes sign in validation; WARN if validation IC is below 30% of training IC or the sign is consistent in under 60% of years |
| 3b | Year consistency | FAIL if IC is positive in fewer than **2/3 of years** |
| 3c | Deflated Sharpe | FAIL if the DSR (corrected for the number of formulas tried) is below **0.95** (when computed) |
| 4 | Regime dependence | WARN if IC is positive in some market regimes and negative in others; suggests a regime gate |
| 5 | Concentration | WARN if one stock makes over 35% of the profit; FAIL above 50% |
| 6 | Trading costs | WARN if the Sharpe turns negative at 20 bps or turnover is above 60× a year |
| 7 | Novelty | WARN if the rank correlation with a known style is above 0.85 |
| – | Complexity | WARN above 20 nodes; the score is penalised above 8 nodes |

**Verdict:**
- ACCEPT if training IC ≥ 0.005, validation IC > 0, validation Sharpe > 0 and at most 2 warnings.
- REVISE if a fixable problem has a suggested action.
- Otherwise REJECT.

**Selection:** uses validation data only, never the test years.

---

## Part G. Results in one table

| Result | Number | Verdict |
|---|---|---|
| Composite of all stable formulas, 192 stocks, 2024–25 (never seen) | rank IC 0.0271, t = 4.0, corrected p < 0.001 | **Significant** |
| Composite, 192 stocks, 2016–23 | IC 0.0123, corrected p = 0.001 | **Significant** |
| Any portfolio after 10 bps costs (28 designs) | best net Sharpe about 0.4, corrected p = 1.0 | Not significant |
| Fama-French 5 + momentum alpha | mostly momentum | Not significant |
| Strict Critic (DSR ≥ 0.95) | no formula passes | Not significant |
| **LLM novel factors (3 Critic-accepted), post-cutoff test 2025-01-01 → 2026-10-23** | IC 0.0068 (t 0.81), residual IC 0.0072 (t 1.95), long-short net Sharpe 0.18, long-only net 0.43, FF5+Mom alpha 0.6% (t 0.15); best Holm p 0.10 | Not significant (best of the three signals) |
| All 329 valid LLM formulas, same window | IC 0.0031, net Sharpe 0.00 | Not significant |
| Built-in library (70 formulas), same window | IC 0.0091, net Sharpe −0.17, alpha −3.1% | Not significant |

**Post-cutoff design (v4/v5):** agents see training 2020–2023 and validation 2024 only; novelty gate |corr| ≤ 0.5 against 77 known factors; validation Sharpe after 10 bps > 0; monthly staggered rebalancing. v5 adds the compact two-step briefing (prompts 17.7k → 6.5k characters), batches of 5, a small repair model, gated attribution and a stop after 3 dry batches. Code: `P\app\alpha\post_cutoff_eval.py`, `factor_report.py`, `measure_runs.py`, `novelty.py`; results: `P\data\alpha\results\post_cutoff_eval.json`, `factor_report.json`, `run_efficiency.json`; paper: `P\docs\paper\Regime_Aware_Multi_Agent_Alpha_Discovery_IEEE_Paper_v4.docx`; project report (college format, no results): `P\docs\report\Project_Report.docx`.

---

## Part H. The website (how to use it)

1. Start it with the two servers in `P\.claude\launch.json` (API on port 8000, web on port 3000), then open http://localhost:3000.
2. Click **Guest Demo Mode** and scroll to the workspace.
3. Use the menu:
   1. **Overview:** what the system does, the agent-loop diagram and the key results.
   2. **Data:** pipeline status, the daily stock panel (now with FinBERT sentiment and "no coverage" labels), charts, regimes and SEC fundamentals.
   3. **News & FinBERT:** coverage per company.
   4. **Agent Loop:**
      - the exact Research-agent briefing;
      - every idea with its domains and source (LLM or knowledge base);
      - the Quant agent's formulas;
      - the validator result, backtest numbers and attribution;
      - the Critic verdict with every check;
      - refinements linked to their parent.
   5. **Backtest Results:** how backtesting works, significance tables, the ablation, equity curves, research memory and the attribution panel.
   6. **Paper & Downloads.**

**Files:**
- `P\src\components\WorkspaceSection.jsx` (menu)
- `OverviewPanel.jsx`, `AgentLoopPanel.jsx`, `SignificancePanel.jsx`, `DownloadsPanel.jsx`, `AlphaDiscoveryLab.jsx`, `DailyStockPanel.jsx`, `NewsIntelligence.jsx` (all in `P\src\components\`)
- API: `P\app\api\routes.py` (endpoints `/api/alpha/agent_loop`, `/api/alpha/briefing`, `/api/alpha/summary`, `/api/alpha/attribution`, `/api/files`)

---

## Part I. Full file map

### Code: data
| File | Role |
|---|---|
| `P\app\config\settings.py` | All paths, dates, model names; keys read from environment variables |
| `P\app\data\providers\market_provider.py` | Yahoo prices |
| `P\app\data\providers\sec_provider.py` | SEC XBRL company facts |
| `P\app\data\providers\sec_8k_provider.py` | SEC 8-K filing events |
| `P\app\data\providers\macro_provider.py` | FRED macro series |
| `P\app\data\providers\fnspid_provider.py` | FNSPID streaming extractor |
| `P\app\data\providers\gnews_provider.py` | Google News RSS harvester |
| `P\app\data\providers\finnhub_news_provider.py` | Finnhub recent news |
| `P\app\data\qa\*.py` | Data quality checks (market, SEC, news, regime) |
| `P\app\features\*.py` | Technical, fundamental, valuation, macro, news, cross-sectional features; feature registry |
| `P\app\models\regime.py` | Walk-forward HMM regimes |
| `P\app\nlp\finbert.py`, `news_scoring.py`, `phrasebank_eval.py` | FinBERT loading, scoring cache, validation |
| `P\app\pipeline\orchestrator.py` | Runs the full data pipeline and writes the panel |
| `P\app\pipeline\screen_universe.py` | Universe rule (≥20 articles every year) |
| `P\app\pipeline\harvest_news_recent.py`, `build_gnews_recent.py` | 2024–25 news |

### Code: agents and evaluation
| File | Role |
|---|---|
| `P\app\alpha\graph.py` | LangGraph loop, refinement rules |
| `P\app\alpha\agents.py` | Context builder, Research agent, Quant agent |
| `P\app\alpha\prompts.py` | Prompt text |
| `P\app\alpha\llm.py` | LLM providers (Groq, Gemini, Claude), cache, safety rules |
| `P\app\alpha\dsl.py` | Factor language |
| `P\app\alpha\validator.py`, `similarity.py` | Formula checks, originality |
| `P\app\alpha\backtester.py` | Backtest engine |
| `P\app\alpha\attribution.py` | Attribution |
| `P\app\alpha\critic.py` | Critic rules |
| `P\app\alpha\memory.py` | Research memory |
| `P\app\alpha\hypotheses.py` | Offline knowledge base of 21 documented ideas |
| `P\app\alpha\run_discovery.py` | Runs the six ablation configurations |
| `P\app\alpha\walkforward.py` | Walk-forward selection, composite, random baseline, Holm |
| `P\app\alpha\cost_aware.py` | 7 portfolio constructions after costs |
| `P\app\alpha\library_tests.py` | Per-formula Holm and White's reality check |
| `P\app\alpha\ff_attribution.py` | Fama-French 5 + momentum regressions |
| `P\app\alpha\eightk_pead.py` | 8-K earnings-drift test |
| `P\app\alpha\stats.py` | Deflated Sharpe ratio |
| `P\app\alpha\tracing.py` | LangSmith / Langfuse hooks (need a key) |
| `P\app\api\routes.py`, `P\app\main.py` | Web API |

### Scripts
| File | Role |
|---|---|
| `P\scripts\run_robustness.ps1` | Runs the full evaluation suite |
| `P\scripts\run_llm_discovery.ps1` | Large Groq run plus evaluation |
| `P\scripts\capture_demo.py` | Website screenshots |
| `P\scripts\keep_awake_until.py` | Keeps the PC awake during long runs |

### Tests
`P\tests\*.py`: 81 tests (data QA, timing and leakage, news, factor language, validator, deflated Sharpe, Critic gate, refinement loop, LLM providers, statistics helpers).

### Data
| Path | Content |
|---|---|
| `P\data\config\universe.csv` | The 192 stocks (`universe_v2_36.csv` = the old 36) |
| `P\data\config\news.yaml` | News settings and thresholds |
| `P\data\unified\daily_stock_panel\master_panel.parquet` | The joined daily table |
| `P\data\raw\news\` | FNSPID per-company files; `gnews_recent\` = 2024–25 Google News |
| `P\data\processed\news\finbert_text_cache.parquet` | FinBERT scores |
| `P\data\processed\sec\eightk_events.parquet` | 8-K events |
| `P\data\alpha\experiments\*.json` | Every formula attempt (memory) |
| `P\data\alpha\results\*.json` | All results (ablations, walk-forward, cost-aware, FF, library tests) |
| `P\data\alpha\llm\` | Every LLM prompt and answer |
| `P\storage\quant.duckdb` | Database used by the website |
| `P\data\_backup_u36\` | Backup of the 36-stock panel |

### Documents
| Path | Content |
|---|---|
| `P\docs\paper\Regime_Aware_Multi_Agent_Alpha_Discovery_IEEE_Paper_v3.docx` | Journal paper |
| `P\docs\paper\build_paper_v2.cjs`, `collect_stats_v3.py` | Paper builder and statistics collector |
| `P\docs\RESULTS_v3.md` | Results table |
| `P\docs\PROJECT_REPORT_SIMPLE.md` | Plain-English report |
| `P\docs\FRAMEWORK_GUIDE.md` | This guide |
| `P\docs\screenshots\demo_*.png` | Website screenshots |
| `C:\Users\hp\Downloads\Alpha_Discovery_Deliverables_v3\` | Copies of the paper, reports and screenshots |
