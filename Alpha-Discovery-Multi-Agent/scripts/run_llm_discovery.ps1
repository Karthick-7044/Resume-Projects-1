# Large-scale LLM discovery + honest evaluation (run AFTER setting the GROQ_API_KEY environment variable yourself).
#   powershell -File scripts\run_llm_discovery.ps1 [-Seeds 11,12,13,14,15,16,17,18] [-Budget 60]
# Discovery uses ONLY the FNSPID train (2013-2019) and validation (2020-2021) windows; 2022-2025 is never shown to the
# agents, so it is the out-of-sample span on which the LLM library and the knowledge-base library are compared.
param([int[]]$Seeds = @(19, 20, 21, 22, 23, 24, 25, 26), [int]$Budget = 60, [switch]$SkipEval)
if (-not $env:GROQ_API_KEY) { Write-Error "GROQ_API_KEY is not set in this environment"; exit 1 }
$env:ALPHA_LLM_PROVIDER = "groq,gemini"   # Groq first, Gemini as fallback
$env:ALPHA_LLM_MODE = "llm"               # LLM-only hypotheses
$env:ALPHA_LLM_STRICT = "1"               # never substitute knowledge-base ideas when the LLM is unavailable
if (-not $env:GROQ_MODEL) { $env:GROQ_MODEL = "openai/gpt-oss-20b,qwen/qwen3.8-27b,openai/gpt-oss-120b" }   # each model has its own daily quota
$py = ".\.venv\Scripts\python.exe"
$log = "data\alpha\results\llm_discovery.log"
function Step($name, [string[]]$a) {
    "== $name  $(Get-Date -Format s)" | Add-Content $log
    & $py @a 2>&1 | Where-Object { "$_" -notmatch "Warning|warn|NativeCommand|CategoryInfo|FullyQualified|At line|~~~|^\s*\+" } |
        Select-Object -Last 15 | Out-String | Add-Content $log
}
foreach ($s in $Seeds) {
    $out = "data\alpha\results\ablation_results_fnspid_llm_groq_seed$s.json"
    if (Test-Path $out) { "skip seed $s (done)" | Add-Content $log; continue }   # resumable
    Step "discovery seed $s" @("-m", "app.alpha.run_discovery", "--window", "fnspid", "--configs", "Full", "--budget", "$Budget", "--seed", "$s", "--tag", "_groq_seed$s")
}
if ($SkipEval) { "DISCOVERY DONE (evaluation skipped) $(Get-Date -Format s)" | Add-Content $log; exit 0 }
foreach ($lib in @("llm", "offline")) {
    Step "walk-forward $lib 2022-2025" @("-m", "app.alpha.walkforward", "--library", $lib, "--first", "2022", "--last", "2025", "--rebalance", "21", "--tag", "_${lib}_2022_2025")
    Step "cost-aware $lib" @("-m", "app.alpha.cost_aware", "--tag", "_${lib}_2022_2025")
    Step "FF5+Mom $lib" @("-m", "app.alpha.ff_attribution", "--tag", "_${lib}_2022_2025", "--extra", "cost_aware_daily_${lib}_2022_2025.parquet")
    Step "library tests $lib" @("-m", "app.alpha.library_tests", "--library", $lib, "--tag", "_${lib}")
}
"ALLDONE $(Get-Date -Format s)" | Add-Content $log
