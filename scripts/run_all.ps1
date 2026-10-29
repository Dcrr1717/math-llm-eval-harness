# Full evaluation sweep (Windows PowerShell). Mirrors scripts/run_all.sh.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Models   = if ($env:MODELS)    { $env:MODELS }    else { "opus,sonnet,haiku" }
$GsmLimit = if ($env:GSM_LIMIT) { $env:GSM_LIMIT } else { "200" }
$MathLimit= if ($env:MATH_LIMIT){ $env:MATH_LIMIT }else { "200" }
$MaxCost  = if ($env:MAXCOST)   { $env:MAXCOST }   else { "30" }

Write-Host "== own (custom set) =="
python -m src.cli run --dataset own                       --models $Models --max-cost $MaxCost
Write-Host "== gsm8k =="
python -m src.cli run --dataset gsm8k --limit $GsmLimit    --models $Models --max-cost $MaxCost
Write-Host "== math =="
python -m src.cli run --dataset math  --limit $MathLimit   --models $Models --max-cost $MaxCost

Write-Host "== report + dashboard =="
python -m src.cli report
python -m src.cli dashboard
Write-Host "Done. See results/summary.json and results/dashboard.html"
