# v4 LLM discovery: agents see ONLY train 2020-2023 and validation 2024; 2025-01-01 onward (post knowledge cutoff of the
# gpt-oss models) is the untouched test. Novelty gate (|corr| <= 0.5 with known factors), cost-aware Critic (validation
# Sharpe after 10 bps > 0), monthly rebalancing, strict LLM-only (no knowledge-base fallback). Resumable per seed.
#   powershell -File scripts\run_llm_v4.ps1 -Seeds "41,42,43,44,45,46,47,48" -Budget 60
param([string]$Seeds = "41,42,43,44,45,46,47,48", [int]$Budget = 60)
if (-not $env:GROQ_API_KEY) { Write-Error "GROQ_API_KEY is not set"; exit 1 }
$env:ALPHA_LLM_PROVIDER = "groq,cerebras,gemini"   # providers without a key are skipped automatically
$env:ALPHA_LLM_MODE = "llm"
$env:ALPHA_LLM_STRICT = "1"
$env:ALPHA_NOVELTY_GATE = "1"
$env:ALPHA_REBALANCE_DAYS = "21"
if (-not $env:GROQ_MODEL) { $env:GROQ_MODEL = "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b" }
$py = ".\.venv\Scripts\python.exe"
$log = "data\alpha\results\llm_v4.log"
foreach ($s in ($Seeds -split ",")) {
    $s = $s.Trim()
    $out = "data\alpha\results\ablation_results_recent_llm_v4_seed$s.json"
    if (Test-Path $out) { "skip seed $s (done)" | Add-Content $log; continue }
    "== v4 discovery seed $s  $(Get-Date -Format s)" | Add-Content $log
    & $py -m app.alpha.run_discovery --window recent --configs Full --budget $Budget --seed $s --tag "_v4_seed$s" 2>&1 |
        Where-Object { "$_" -notmatch "Warning|warn|NativeCommand|CategoryInfo|FullyQualified|At line|~~~|^\s*\+" } |
        Select-Object -Last 8 | Out-String | Add-Content $log
}
"V4 DISCOVERY DONE $(Get-Date -Format s)" | Add-Content $log
