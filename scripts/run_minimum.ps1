<#
  Runs the minimum experiment for the paper (~1.5-2 h) end to end.
  Run from the rmc-spark folder in a VS Code PowerShell terminal, with Docker Desktop running:

      powershell -ExecutionPolicy Bypass -File scripts\run_minimum.ps1
      powershell -ExecutionPolicy Bypass -File scripts\run_minimum.ps1 -CaseStudies   # + Section XVIII (~15 min, needs internet once)
      powershell -ExecutionPolicy Bypass -File scripts\run_minimum.ps1 -SkipData      # data already generated

  Steps: start testbed -> wait healthy -> generate smaller data -> calibrate timings ->
         36 runs (4 systems x ETL x 3 faults x 3 reps) -> [case studies] -> tables and figures.
  Output: results/raw/minimum/ (raw), results/report/ (Tables 11-12, Figs 21-24).
  Keep the laptop plugged in, lid open, and don't use Docker for anything else meanwhile.
#>
param([switch]$SkipData, [switch]$CaseStudies, [switch]$Fresh)
$ErrorActionPreference = "Continue"   # PS 5.1 turns redirected native stderr into errors under "Stop"; exit codes are checked instead
function Step($m) { Write-Host "`n=== $m ($(Get-Date -Format HH:mm:ss)) ===" -ForegroundColor Cyan }
function Exec([string]$cmd) { docker compose exec -T controller bash -c "set -o pipefail; $cmd"; if ($LASTEXITCODE -ne 0) { throw "failed: $cmd" } }

Set-Location (Join-Path $PSScriptRoot "..")
$started = Get-Date

Step "1/6 starting the testbed"
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed - is Docker Desktop running?" }
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    $s = docker compose exec -T controller python -m controller.cli status 2>$null
    if (($s | Select-String "HEALTHY").Count -ge 2) { $healthy = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $healthy) { throw "clusters did not become HEALTHY - check http://localhost:8080 and :8090" }
docker compose exec -T controller python -m controller.cli status

if ($Fresh -and (Test-Path results\raw\minimum)) { Remove-Item -Recurse -Force results\raw\minimum }

if (-not $SkipData) {
    Step "2/6 generating smaller datasets (1.5 M trips, 1 M edges)"
    Exec "spark-submit --master spark://spark-master-a:7077 --conf spark.driver.host=controller --total-executor-cores 4 --executor-memory 576m jobs/datagen.py --taxi-rows 1500000 --graph-nodes 100000 --graph-edges 1000000"
}

Step "3/6 calibrating fault time and deadline from clean runs"
Exec "python -m experiments.calibrate experiments/configs/minimum.yaml --runs 2"

Step "4/6 running the 36-run experiment (about 1.5 h)"
Exec "python -m experiments.run_matrix experiments/configs/minimum.yaml 2>&1 | tee -a results/raw/minimum_console.txt"

if ($CaseStudies) {
    Step "5/6 case studies (fraud, predictive maintenance)"
    Exec "python scripts/download_data.py --case-studies"
    Exec "spark-submit --master spark://spark-master-a:7077 --conf spark.driver.host=controller --total-executor-cores 4 --executor-memory 576m jobs/ingest_local.py"
    Exec "python -m experiments.calibrate experiments/configs/cases.yaml --runs 1"
    Exec "python -m experiments.run_matrix experiments/configs/cases.yaml 2>&1 | tee -a results/raw/cases_console.txt"
} else { Step "5/6 case studies skipped (use -CaseStudies)" }

Step "6/6 producing tables and figures"
Exec "python -m analysis.report results/raw/minimum --out results/report"

$mins = [math]::Round(((Get-Date) - $started).TotalMinutes)
Write-Host "`nDONE in $mins min. Results: results\raw\minimum\runs.csv  and  results\report\" -ForegroundColor Green
Write-Host "Tell Claude 'results are ready' to update the paper." -ForegroundColor Green
