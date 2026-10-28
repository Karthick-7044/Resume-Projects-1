# What we built and what we found — plain-English report

## 1. The idea in one paragraph
A team of AI "agents" searches for **alpha factors**: formulas that rank stocks by how well they are likely to do next.
- The **Research agent** proposes an idea, for example "stocks that went up for a year keep going up".
- The **Quant agent** turns the idea into a formula, for example `cs_rank(momentum_252_21d)`.
- A **validator** checks the formula is safe and never looks into the future.
- The **backtester** tests the formula on history.
- **Attribution** explains which data made it work.
- The **Critic agent** decides ACCEPT / REVISE / REJECT.
- **Memory** remembers every attempt.

Everything runs on a clean, point-in-time dataset: only information that was really available on each day is used.

## 2. The data we built
| What | Detail |
|---|---|
| Stocks | 36 large US companies at first, now **192** (11 sectors), picked by one rule: at least 20 news articles in every year 2013–2023 |
| Prices | Daily prices 2012–2025 (Yahoo Finance) |
| Company accounts | SEC EDGAR filings, using the numbers *as first reported* (no later corrections leak into the past) |
| News | **725,193** news headlines (FNSPID dataset), each scored positive/negative/neutral by **FinBERT** |
| Market mood | A hidden Markov model labels each day Bull / Bear / High-volatility, using only past data |
| Macro | Interest rates, VIX, yield curve (FRED) |
| Final table | **675,233 rows** (one row per stock per day) × 181 columns |

## 3. How each module works
- **Backtester.** Each rebalance day it buys the top-ranked stocks and sells the bottom-ranked ones (equal money long and short). It holds them, then charges **10 bps** (0.10%) every time it trades. It reports:
  - **rank IC:** how well the ranking predicted next-day returns;
  - **Sharpe ratio:** return per unit of risk;
  - drawdown, turnover, and results by year and by market regime.
- **Critic agent.** It never sees the test period. It checks seven things:
  1. too-good-to-be-true results (possible look-ahead);
  2. whether the sign matches the idea;
  3. stability over years (now: positive in at least 2/3 of years);
  4. dependence on one market regime;
  5. one stock producing most of the profit;
  6. sensitivity to trading costs;
  7. similarity to well-known factors.

  It now also needs a **deflated Sharpe ratio of at least 0.95**, which corrects for how many formulas were tried. Its thresholds: training IC ≥ 0.005; validation IC > 0 and validation Sharpe > 0; IC above 0.15 or Sharpe above 4 is flagged as suspicious; one stock above 50% of profit means FAIL.
- **Refinement loop (updated now).** When the Critic says REVISE or REJECT, its written reasons are saved in memory and sent back to the Quant agent. The Quant agent then makes an improved formula, for example by smoothing the signal or switching it on only in certain market regimes. This repeats **up to 2 times** per idea, and each attempt is linked to its parent in memory. Leakage failures are not "repaired", and flipping a formula's sign after seeing bad results is not allowed, because that would be cheating.
  - Before today, only REVISE verdicts got **1** refinement.
  - The results below were produced with that older version; rerunning discovery would show the effect of the new loop.
- **Attribution.** It removes one input at a time and measures how much the prediction quality drops. That tells you whether a formula really uses news, accounts, price or regime data, and how much it looks like known styles such as momentum, value or low volatility.

## 4. The six experiment setups (ablation)
| Setup | Data the agents may use | Critic |
|---|---|---|
| A | Price/technical only | yes |
| B | A + company accounts + valuation | yes |
| C | B + news sentiment | yes |
| D | C + market regime | yes |
| Full | everything + macro, Critic and memory | yes |
| Full-NoCritic | everything, but picks formulas by training score only | **no** |

## 5. How many formulas
| Source | Attempts | Invalid | Critic ACCEPT | REVISE | REJECT |
|---|---|---|---|---|---|
| Offline knowledge base, news window (6 setups) | 317 (73 distinct formulas) | 23 | 44 | 66 | 127 (+57 unreviewed in Full-NoCritic) |
| Offline knowledge base, recent window (6 setups) | 291 (64 distinct) | 29 | 52 | 13 | 140 (+57 unreviewed) |
| Gemini LLM agents (4 seeds) | 88 LLM formulas (+21 from the knowledge base in hybrid mode) | 13 | 2 | 6 | 67 |

- **Formula library used for all the significance tests:** 70 distinct valid formulas.
- **All 70 come from the offline knowledge base; 0 come from the LLM.** So the significant composite below is 100% knowledge-base formulas.

## 6. What is statistically significant (after correcting for testing many formulas)
| Signal | Stocks | Period | Prediction quality (rank IC) | t | Corrected p |
|---|---|---|---|---|---|
| Composite (average of all stable formulas) | 36 | 2016–23 | 0.0243 | 4.77 | <0.001 |
| Composite | 192 | 2016–23 | 0.0123 | 3.63 | 0.001 |
| **Composite** | **192** | **2024–25 (never used before)** | **0.0271** | **4.00** | **<0.001** |
| Top-3 formulas | 192 | 2016–23 | 0.0134 | 3.44 | 0.002 |
| Five textbook factors | 192 | 2016–23 | 0.0114 | 2.86 | 0.004 |

The composite also beat **200 out of 200** random picks of formulas from the same library.

## 7. What is NOT significant
- **Strict Critic:** no single formula passes it in any year.
- **Trading profit after costs:** none of 28 portfolio designs is significant, whether lower trading, smoothing, long-only or sector-neutral.
- **Fama-French 5 + momentum:** nothing beats it; most of the signal is plain momentum and short-term reversal.
- **SEC 8-K earnings drift:** not significant after costs.
- **Gemini agents:** best test IC 0.007; they did not beat the knowledge base.
- **Accrual factor:** strong in 2013–23, but failed 2024–25. Treat it as a lead only.

## 8. Other checks
- **FinBERT accuracy:** 97.2% on the Financial PhraseBank. FinBERT was trained on part of this dataset, so this is only a sanity check.
- **Bugs we found and fixed:**
  - A one-day date shift in the factor regression.
  - "Lucky rebalance day": the earlier Sharpe of 0.51 was the best of 5 possible days. All results now average over all 5.
  - The dashboard showed a hardcoded "10 stocks".
  - The equity chart had been overwritten.

## 9. Bottom line
The system **does find real, robust predictive signals** that survive strict statistical correction, including on fresh 2024–25 data. But they are **small and mostly known effects (momentum and reversal)**, and trading costs eat them in big US stocks. That is an honest, publishable result.

## 10. How to see it
1. Open http://localhost:3000. The API runs on port 8000.
2. Click **Guest Demo Mode**.
3. Scroll to the workspace.
4. Open the **Alpha Discovery Lab** tab to see:
   - the ablation table and equity curves;
   - Research memory, with the Critic verdict for every formula (hover a row to read why);
   - the Attribution panel.
5. The **News Intelligence (FinBERT)** tab shows the news coverage.

**Files:**
- Screenshots: `docs/screenshots/demo_*.png`.
- Paper: `docs/paper/..._v3.docx`.
- Full numbers: `docs/RESULTS_v3.md`.

## 11. Added on 24 Oct 2026
- **Groq LLM provider** (model llama-3.3-70b-versatile).
  - The key is read only from the `GROQ_API_KEY` environment variable.
  - Calls are paced to 30 per minute, cached and logged, and quota errors are reported clearly.
  - Setting `ALPHA_LLM_PROVIDER=groq,gemini` uses Groq first and falls back to Gemini.
- **Two-domain rule:** each new hypothesis must combine at least two data domains (for example price + fundamentals, or news + regime). Single-domain ideas are rejected automatically.
- **Refinement loop:** the Critic's reasons go back to the Quant agent for up to 2 refinements, on REVISE and on REJECT (see section 3).
- **One-command large LLM run:** `scripts\run_llm_discovery.ps1` runs 8 seeds × 60 formulas (about 480 formulas). It then evaluates the LLM library and the knowledge-base library separately on 2022–2025, years the agents never see, with Holm correction, the random-selection null, costs and Fama-French 5 + momentum.
- **Tests:** 80, all passing.
