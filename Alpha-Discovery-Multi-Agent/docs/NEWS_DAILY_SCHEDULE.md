# Daily news update: scheduling

The daily job fetches the last 3 days of Finnhub company news for every universe ticker, de-duplicates by
`article_hash` and **appends only new rows** (old rows are never edited or deleted). Run it after the US market
close (16:00 ET = 20:00 UTC in summer, 21:00 UTC in winter), then re-score and rebuild.

```
python -m app.pipeline.news_update --mode daily       # needs a working FINNHUB_API_KEY
python -m app.nlp.news_scoring                         # scores only the new headlines (cached)
python -m app.pipeline.orchestrator --no-news-update   # rebuilds panel + weekly snapshot
```

The key is read from the `FINNHUB_API_KEY` environment variable (or a local `.env`, which is git-ignored). It is
never stored in code. If the key is missing or rejected the job exits with code 2 and writes nothing.

## Windows Task Scheduler (this machine)

```
schtasks /Create /SC DAILY /ST 22:30 /TN "NewsDaily" /TR "cmd /c cd /d C:\karthick\final-year project && python -m app.pipeline.news_update --mode daily && python -m app.nlp.news_scoring"
```
22:30 local (IST) is after the close in both US DST regimes only when the PC is on; adjust to your time zone.

## cron (Linux/macOS server, UTC)

```
# 21:30 UTC, Monday-Friday: after the 16:00 ET close in both EST and EDT
30 21 * * 1-5  cd /path/to/project && python -m app.pipeline.news_update --mode daily && python -m app.nlp.news_scoring
```

## GitHub Actions

Template: `ops/news_daily.github-workflow.yml` (copy to `.github/workflows/news_daily.yml` in a git repository and add
`FINNHUB_API_KEY` as a repository secret).

## Checks the job performs

- logs article count per ticker per run to `data/raw/news_finnhub/daily_log.csv`;
- warns when a ticker that normally has articles returns zero;
- every raw JSON response is saved under `data/raw/news_finnhub_raw/{TICKER}/daily_*.json`.
