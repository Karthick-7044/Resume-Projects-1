# Robustness study (v3): what is and is not significant

All numbers are out-of-sample walk-forward results (selection uses only earlier years). Costs are 10 bps one-way.
Portfolios use staggered tranches, which average every rebalance day.
Corrections:
- **Holm** across the pre-specified rules or variants in each family.
- **White's reality check** across the 70-formula library.
- **Random null:** 200 random 3-formula selections per test year.
- **DSR:** deflated Sharpe ratio.

The years 2016–2023 are out of sample for *selection* but not for *library generation*. 2024–2025, and especially 2025, were never used.
Raw files are in `data/alpha/results/`. The 36-stock results have no tag; the 192-stock results are tagged `_u192`.

## Ranking signal (rank IC)

| Rule | Universe | Period | Rank IC | Monthly t | Holm p | Random-null p | Verdict |
|---|---|---|---|---|---|---|---|
| Composite (all stable formulas) | 36 | 2016–23 | 0.0243 | 4.77 | <0.001 | <0.005 | **Significant** |
| Composite | 192 | 2016–23 | 0.0123 | 3.63 | 0.001 | 0.01 | **Significant** |
| Composite | 192 | 2024–25 hold-out | 0.0271 | 4.00 | <0.001 | <0.005 | **Significant** |
| Composite | 36 | 2024–25 hold-out | 0.0281 | 2.26 | 0.047 | 0.015 | Significant (marginal) |
| Naive top-3 | 36 | 2016–23 | 0.0164 | 2.71 | 0.020 | 0.05 | Significant vs 0; borderline vs random |
| Naive top-3 | 192 | 2016–23 | 0.0134 | 3.44 | 0.002 | 0.01 | **Significant** |
| Naive top-3 | 192 | 2024–25 hold-out | 0.0196 | 2.45 | 0.043 | 0.02 | Significant (marginal) |
| Literature composite (no selection) | 192 | 2016–23 | 0.0114 | 2.86 | 0.004 | 0.02 | **Significant** |
| Strict Critic (DSR ≥ 0.95) | both | 2016–23 | — | — | — | — | Accepts **no** formula in any year (max DSR 0.21–0.49) |
| Any single formula | 192 | 2025 hold-out | — | — | 0 of 70 pass Holm | RC p = 0.084 | Not significant |

## Net of costs and factor models

| Test | Best result | Corrected | Verdict |
|---|---|---|---|
| 28 cost-aware variants, 36 stocks, 2016–23 | Composite long-only top quintile vs EW, net SR 0.35 | Holm p = 1.0, DSR 0.23 | Not significant |
| 28 variants, 192 stocks, 2016–23 | Naive long-only top quintile vs EW, net SR 0.43 | Holm p = 1.0, DSR 0.26 | Not significant |
| 28 variants, 192 stocks, 2024–25 | Composite L/S 63-day, net SR 0.31 | Holm p = 1.0 | Not significant |
| FF5 + Mom alpha (all pre-specified series) | Largest positive t ≈ 2.4 (not a pre-specified trial) | Holm across ~70 regressions: not significant | Not significant; signal loads on momentum (β ≈ 0.2–0.47) |
| Accrual factor `-cs_rank(accruals_ratio)`, 192 stocks | 2013–23: net SR 0.87 (t = 2.88), FF5+Mom alpha 3.0%/yr (t = 3.15); holds on the 156 unseen stocks | Library Holm p = 0.0497 | **Borderline; fails 2024–25 hold-out** (net SR −0.51) |
| SEC 8-K post-earnings drift (1 pre-specified test) | 192 stocks, 2024–25: IC 0.010 (t = 2.52), net SR 1.07 | FF alpha t = 1.27 | Not significant net |
| Gemini agents, 4 seeds | Best test IC 0.007 (t = 0.76) | — | Not significant |

## Other checks

- **FinBERT on Financial PhraseBank:** 97.2% accuracy, macro-F1 0.963 on AllAgree; 89.0% and 0.883 on 50Agree. FinBERT was fine-tuned on this corpus, so this is a sanity check only.
- **Rebalance-phase luck:** the previously reported 5-day gross Sharpe of 0.51 was the best of 5 phases (range −0.14 to 0.51). All portfolio numbers now average across phases.
- **Universe:** 156 of 242 S&P 500 candidates pass the unchanged rule (≥20 FNSPID articles in every year 2013–23), giving 192 stocks in 11 sectors. EA, HOLX, BK and EQR passed the news rule but were dropped because they have no price history (taken private or delisted).

## Bottom line

The agent loop finds real, multiple-testing-robust cross-sectional *ranking* information. It replicates on a 5× larger universe and on the untouched 2024–25 hold-out. But it is mostly momentum and short-term reversal, and **no pre-specified portfolio earns a significant net-of-cost return or factor-model alpha**. The accrual factor is the only net-of-cost lead, and it did not replicate out of time.
