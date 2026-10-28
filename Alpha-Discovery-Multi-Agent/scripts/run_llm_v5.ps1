# v5 = v4 + two-step briefing (menu -> chosen features + relevant failures), 5 ideas per Research call, small model for
# repairs, attribution only for formulas passing the cheap checks.
# v4 LLM discovery: agents see ONLY train 2020-2023 and validation 2024; 2025-01-01 onward (post knowledge cutoff of the
# gpt-oss models) is the untouched test. Novelty gate (|corr| <= 0.5 with known factors), cost-aware Critic (validation
# Sharpe after 10 bps > 0), monthly rebalancing, strict LLM-only (no knowledge-base fallback). Resumable per seed.
#   powershell -File scripts\run_llm_v5.ps1 -Seeds "41,42,43,44,45,46,47,48" -Budget 60
param([string]$Seeds = "51,52,53,54,55,56,57,58", [int]$Budget = 60)
if (-not $env:GROQ_API_KEY) { Write-Error "GROQ_API_KEY is not set"; exit 1 }
$env:ALPHA_LLM_PROVIDER = "groq,cerebras,gemini"   # providers without a key are skipped automatically
$env:ALPHA_LLM_MODE = "llm"
$env:ALPHA_LLM_STRICT = "1"
$env:ALPHA_NOVELTY_GATE = "1"
$env:ALPHA_REBALANCE_DAYS = "21"
$env:ALPHA_LLM_BRIEFING = "compact"
$env:ALPHA_RESEARCH_BATCH = "5"
$env:ALPHA_ATTRIBUTION = "gated"
if (-not $env:GROQ_MODEL_SMALL) { $env:GROQ_MODEL_SMALL = "openai/gpt-oss-20b" }
if (-not $env:GROQ_MODEL) { $env:GROQ_MODEL = "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b" }
$py = ".\.venv\Scripts\python.exe"
$log = "data\alpha\results\llm_v5.log"
foreach ($s in ($Seeds -split ",")) {
    $s = $s.Trim()
    $out = "data\alpha\results\ablation_results_recent_llm_v5_seed$s.json"
    if (Test-Path $out) { "skip seed $s (done)" | Add-Content $log; continue }
    "== v5 discovery seed $s  $(Get-Date -Format s)" | Add-Content $log
    & $py -m app.alpha.run_discovery --window recent --configs Full --budget $Budget --seed $s --tag "_v5_seed$s" 2>&1 |
        Where-Object { "$_" -notmatch "Warning|warn|NativeCommand|CategoryInfo|FullyQualified|At line|~~~|^\s*\+" } |
        Select-Object -Last 8 | Out-String | Add-Content $log
}
"V5 DISCOVERY DONE $(Get-Date -Format s)" | Add-Content $log
