#!/usr/bin/env bash
# Runs FinBERT scoring repeatedly until the budget is used or everything is scored. A crash (segfault under low memory)
# only loses the current chunk because progress is saved every chunk; the loop gives up if a run makes no progress.
cd "$(dirname "$0")/.."
BUDGET_MIN=${1:-25}; END=$(( $(date +%s) + BUDGET_MIN*60 ))
count() { python -c "import pandas as pd; print(len(pd.read_parquet('data/processed/news/finbert_text_cache.parquet')))" 2>/dev/null; }
prev=$(count); stalls=0
while [ $(date +%s) -lt $END ]; do
  left=$(( (END - $(date +%s)) / 60 )); [ $left -lt 1 ] && break
  HF_HUB_OFFLINE=1 HF_HUB_DISABLE_SYMLINKS_WARNING=1 PYTHONIOENCODING=utf-8 \
  NEWS_SCORING_THREADS=${NEWS_SCORING_THREADS:-6} NEWS_SCORING_BATCH=${NEWS_SCORING_BATCH:-32} NEWS_SCORING_CHUNK=${NEWS_SCORING_CHUNK:-1024} \
    python -m app.nlp.news_scoring --max-minutes $left && break
  now=$(count); if [ "$now" = "$prev" ]; then stalls=$((stalls+1)); else stalls=0; fi; prev=$now
  echo "run crashed or ended early; cached=$now stalls=$stalls"; [ $stalls -ge 4 ] && { echo "no progress, giving up"; break; }
done
echo "FINAL cached=$(count)"
