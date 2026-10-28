# Runs the full v3 robustness suite on the CURRENT master panel and tags every output (e.g. -Tag _u192).
#   powershell -File scripts\run_robustness.ps1 -Tag _u192 [-Panel path]
param([string]$Tag = "_u192", [string]$Panel = "")
$py = ".\.venv\Scripts\python.exe"
$log = "data\alpha\results\robustness$Tag.log"
$pp = @(); if ($Panel) { $pp = @("--panel", $Panel) }
function Step($name, [string[]]$a) {
    "== $name" | Add-Content $log
    & $py @a 2>&1 | Where-Object { "$_" -notmatch "Warning|warn|INFO|NativeCommand|CategoryInfo|FullyQualified|At line|~~~|^\s*\+" } | Out-String | Add-Content $log
}
Step "walkforward reb5" (@("-m", "app.alpha.walkforward", "--rebalance", "5", "--tag", $Tag) + $pp)
Step "walkforward reb21" (@("-m", "app.alpha.walkforward", "--rebalance", "21", "--tag", "${Tag}_reb21") + $pp)
Step "walkforward holdout" (@("-m", "app.alpha.walkforward", "--first", "2024", "--last", "2025", "--tag", "${Tag}_holdout") + $pp)
Step "cost_aware" (@("-m", "app.alpha.cost_aware", "--tag", $Tag) + $pp)
Step "cost_aware holdout" (@("-m", "app.alpha.cost_aware", "--tag", "${Tag}_holdout") + $pp)
Step "ff" @("-m", "app.alpha.ff_attribution", "--tag", $Tag, "--extra", "cost_aware_daily$Tag.parquet")
Step "ff holdout" @("-m", "app.alpha.ff_attribution", "--tag", "${Tag}_holdout", "--extra", "cost_aware_daily${Tag}_holdout.parquet")
Step "library_tests" (@("-m", "app.alpha.library_tests", "--tag", $Tag) + $pp)
Step "8-K PEAD" (@("-m", "app.alpha.eightk_pead", "--tag", $Tag) + $pp)
Step "phase" (@("-m", "app.alpha.phase_sensitivity", "--tag", $Tag) + $pp)
"ALLDONE" | Add-Content $log
