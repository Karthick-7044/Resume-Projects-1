# News pipeline (FNSPID + Finnhub, FinBERT, point-in-time safe)

Provider-agnostic: every provider writes one unified schema; **one** alignment path, **one** FinBERT scoring path and
**one** feature path serve all of them. No synthetic data exists anywhere in the pipeline
(`_generate_historical_sample_news()` was deleted; the legacy RSS provider is live-headline only).

```
FNSPID extract ─┐
                ├─> unified articles ─> FinBERT (cached) ─> PIT alignment ─> News QA ─> daily features ─> master panel
Finnhub API ────┘      (article_hash)    app/nlp             app/features      app/data/qa   app/features        DuckDB/Parquet
```

## 1. Sources and licenses

| Source | Used for | Terms |
|---|---|---|
| **FNSPID** (Hugging Face `Zihan1004/FNSPID`; Dong, Fan & Peng, arXiv:2402.06698) | historical news, up to 2023-12-31 | **CC BY-NC-4.0**: non-commercial research use, attribution required. Commercial use needs the authors' permission. |
| **Finnhub company-news** | 2024-01-01 -> today, daily updates | Finnhub free-tier terms; key from `FINNHUB_API_KEY`. History depth is verified by `scripts/probe_news_sources.py`. |
| ProsusAI/finbert | sentiment | Hugging Face model card terms |

FNSPID's two news CSVs are 5.7 GB and 23.2 GB. They are **never stored**: `app/data/providers/fnspid_provider.py`
streams them with HTTP range requests and keeps only rows for the configured tickers inside the window.
Layout found by inspection:

* `All_external.csv`: 11 columns, real timestamps (mostly Benzinga headlines, titles only), **not sorted** by ticker, contains
  non-English text and rows with no ticker -> full stream-filter.
* `nasdaq_exteral_data.csv`: 12 columns (leading float index). First ~75% is **sorted by ticker** (block search by binary
  search over byte offsets); the tail is a different unsorted section -> full stream-filter. Timestamps are date-only.
* Rows are split on a strict row-start pattern and parsed individually, so one malformed quote cannot swallow neighbours.
  Extraction is resumable and idempotent (`data/raw/news_fnspid/progress.json`).

## 2. Unified schema

`article_hash` (sha1 of `ticker + title + published_at`), `ticker`, `published_at` (UTC), `fetched_at` (UTC; FNSPID =
dataset load time with `provider_fetch_kind="static"`, Finnhub = actual fetch time, `"api"`), `title`, `summary`,
`source` (publisher), `url`, `provider` (`fnspid` | `finnhub`), plus `source_domain`, `time_precision`
(`EXACT`/`LOW`), `topics`, `title_mentions_company`, `relevance_weight`, `article_type`. FNSPID files:
`data/raw/news/{TICKER}_news.parquet`; Finnhub (append-only): `data/raw/news_finnhub/{TICKER}_news.parquet`, raw JSON
in `data/raw/news_finnhub_raw/{TICKER}/`.

Ticker aliases (config `ticker_aliases`): FNSPID tags pre-2022 Facebook as `FB` and Alphabet's other share class as
`GOOG`. They are mapped to `META` / `GOOGL` (same issuer); the original symbol stays in `orig_symbol`. Disable by editing
`data/config/news.yaml`.

## 3. Point-in-time alignment (`app/features/news_pit.py`)

`published_at` is converted to America/New_York; the trading calendar is derived from the SPY price index in the repo.

| Case | effective_date |
|---|---|
| trading day, before 16:00 ET | same day |
| trading day, at/after 16:00 ET | next trading day |
| weekend or holiday | next trading day |
| low-precision stamp (`minute == second == 0`: date-only or hour-only) | first trading day **strictly after** the stamp's date |

The last row is deliberately conservative: it can delay an article, never advance it. Tests (`tests/test_news_pit.py`):
Friday 16:01 ET -> Monday, 15:59 ET -> same day, holiday -> next session, DST, date-only, never earlier than the publication
session. News QA also verifies `effective_date >= published date` and one effective date per article.

## 4. FinBERT scoring (`app/nlp/news_scoring.py`)

ProsusAI/finbert, tensor-only weight loading (the checkpoint ships only `pytorch_model.bin`, which recent `transformers`
refuse on torch < 2.6), CPU batch inference (length-sorted batches), seed 42. Text = title (+ summary truncated to
`scoring.summary_chars`; default 0 = **title only**, because title+summary is ~2.5x slower on CPU and FNSPID summaries are
extractive text). Identical texts are scored once. `sentiment = p_pos - p_neg`. Caches (`data/processed/news/`):
`finbert_text_cache.parquet` (text hash -> probabilities), `articles_scored.parquet` (keyed by `article_hash`), and
`finbert_meta.json` (model, **revision hash**, torch/transformers versions, seed, max length). Provider-supplied sentiment is
never used.

## 5. Relevance and article type (`app/features/news_enrich.py`)

* `relevance_weight` = 1.0 if the company name/alias or ticker appears in the title, else 0.3 (config `relevance`).
* `article_type` by config keyword lists, first match in config order: `earnings`, `analyst_rating`, `m_and_a`,
  `product_partnership`, else `other`. **Keyword-based; expect misclassifications.**

## 6. Daily features (`app/features/news_features.py`)

Per (ticker, effective_date), relevance-weighted (`w`), computed **separately inside each provider period**:

| Feature | Definition |
|---|---|
| `news_count` / `news_count_weighted` | article count / sum of weights (0 on a covered day with no article) |
| `sent_mean` | `sum(w s)/sum(w)` |
| `sent_decay` | decayed `sum(w s)/sum(w)`, half-life 3 trading days; NaN if decayed weight mass < 0.25 |
| `sent_surprise` | `(sent_mean_t - mean_20)/std_20` over the 20 days **strictly before t** |
| `news_vol_surprise` | same z-score for `news_count_weighted` |
| `sent_dispersion` | weighted std of article sentiment that day; NaN if < 3 articles |
| `sent_momentum` | `sent_decay_t - sent_decay_{t-5}` |
| `source_count` | distinct source domains |
| `sent_earnings`, `sent_analyst_rating` | weighted mean sentiment of that article type |
| `*_pstd` | expanding within-provider-period z-score (baseline = earlier days of the same ticker and provider only); raw feature kept |

Gating (all in `data/config/news.yaml`): >= 3 articles for dispersion; >= 10 trailing days **with news** for any z-score;
>= 0.25 decayed weight mass for `sent_decay`; >= 60 prior observations for `*_pstd`. **NaN means "not enough information", never 0.**
Compatibility columns from earlier versions (`news_count`, `avg_finbert_sentiment`, `positive_news_count`, ...) remain.
`news_provider` / `news_status` (`NEWS`, `NO_ARTICLES`, `NO_COVERAGE`) / `news_quality` columns are added.

Coverage: a **FNSPID** ticker-year counts as covered only with >= 20 articles (`coverage.min_articles_per_ticker_year`);
other years are `NO_COVERAGE` and every feature is NaN. **Finnhub** is covered only for windows whose raw response was saved.

## 7. Quality assurance (`app/data/qa/news_qa.py`)

Rejects: empty titles, future timestamps, `published_at` after `fetched_at`, sentiment outside [-1, 1] or probabilities outside
[0, 1], `effective_date` earlier than the published date, an article mapped to two effective dates, duplicate `article_hash`.
Reports the NaN rate per feature per ticker per provider (`reports/news_nan_rates.csv`). **Leakage test**
(`NewsQA.leakage_check`, `tests/test_news_features.py`): features on date t are identical when every article with
`effective_date > t` is deleted; a deliberately leaky builder is detected.

## 8. Operation

```
python -m app.pipeline.fetch_fnspid            # extract FNSPID rows (resumable)
python -m app.pipeline.build_fnspid_news       # filters, aliases, unified files, coverage table
python scripts/probe_news_sources.py AAPL      # Finnhub history-depth verdict (needs a working key)
python -m app.pipeline.news_update --mode backfill|daily
python -m app.nlp.news_scoring [--max-minutes 25]   # resumable FinBERT scoring
python -m app.pipeline.orchestrator            # rebuild the panel (also writes the weekly snapshot)
python scripts/splice_diagnostics.py
python -m app.alpha.run_discovery --window fnspid|recent   # evaluate each window separately
```
Weekly dated snapshots of the news table go to `data/snapshots/news_snapshot_<Monday>.parquet`. Daily scheduling:
`docs/NEWS_DAILY_SCHEDULE.md`. Evaluation windows are **never pooled** by default (`ALPHA_WINDOWS` in `settings.py`).

## 9. Results of the run (36-stock universe, 2012-2025)

| Item | Value |
|---|---|
| Universe | 36 US large caps in 9 sectors: the original 10 plus 26 added by the rule "at least 20 FNSPID articles in every year 2013-2023" (68 candidates screened, 28 passed) |
| Unified articles | 240,154 (238,077 FNSPID + 2,077 Finnhub recent rows), 100% FinBERT-scored, revision `4556d130...` recorded in `data/processed/news/finbert_meta.json` |
| Timestamp precision | FNSPID: **99.9% date-only**, so those articles take effect the next trading day; Finnhub: exact (4% low-precision) |
| Coverage | median 507 articles per ticker-year; 58 of 396 ticker-years below 20 articles are `NO_COVERAGE` (features NaN, never 0) |
| News QA | 0 failures, 0 duplicates, 0 point-in-time violations |
| Panel | 126,625 rows x 181 columns, DATE+TICKER unique; news features available for 2013-2023 only |
| Cross-section | on 2013-2023, a median of 24 stocks per day have `sent_mean` and 29 have `sent_decay`; about 100% of days have the 5+ stocks needed to rank (the 10-stock panel had 24-32%) |
| Feature NaN rate (covered days) | `sent_decay` 7%, `sent_momentum` 8%, `news_vol_surprise` 17%, `sent_mean` 27%, `sent_surprise` 31%, `sent_dispersion` 62%, `sent_earnings` 81%, `sent_analyst_rating` 88% (sparse by construction) |

Finnhub free-tier probe (`scripts/probe_news_sources.py`, key valid): **2024 and mid-2025 return no articles**; data starts about
October 2025 (about 12 months of history) and each call is capped near 250 newest articles, so windows are split at 200+.
The backfill is therefore stopped by design; the daily update works and is append-only.
`scripts/splice_diagnostics.py` reports "cannot be assessed" because there is no news after 2023-12-31.

## 10. Known limitations

1. **Source shift and gap.** FNSPID ends 2023-12-31 and Finnhub's free tier cannot backfill 2024 - Sep 2025, so news features are NaN
   from 2024-01-01; the news ablation is evaluated only inside 2013-2023.
2. **Mostly date-only timestamps.** 99.9% of FNSPID articles carry only a date, so news acts with a one-trading-day delay; intraday
   news effects cannot be studied.
3. **Source mix.** FNSPID combines Benzinga headlines (2009-2020) and Nasdaq/Zacks articles (2022-2023); source composition changes
   over time and varies by stock. Provider-period standardisation (`*_pstd`) addresses only the provider boundary, not changes inside FNSPID.
4. **Keyword tagging.** `article_type` and `topics` are keyword rules and will misclassify; relevance uses a title match (company name or ticker).
5. **Title-only scoring.** FinBERT scores headlines (title + summary was 2.5x slower on CPU); FinBERT has not been re-validated on this dataset.
6. **Alias mapping.** `FB`->`META` and `GOOG`->`GOOGL` are treated as the same issuer (configurable).
7. **Universe.** Present-day large-cap survivors (survivorship bias); 36 stocks is still a small cross-section.
8. **Sparse features.** `sent_dispersion`, `sent_earnings` and `sent_analyst_rating` are NaN on most days; they are usable only combined with denser features.
9. **LLM look-ahead.** An LLM proposing hypotheses may know market history. Mitigations: anonymised prompts, literature-grounding and
   no-identity output rules, offline knowledge-base baseline, and (still to do) a post-cutoff test window.
