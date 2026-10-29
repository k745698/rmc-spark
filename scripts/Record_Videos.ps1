# Records the execution videos for the RMC-Spark submission.
# Double-click scripts\Record_Videos.bat. Each video records the whole screen with ffmpeg
# while the commands run in this window, and is saved as an MP4 in this folder.

$ErrorActionPreference = "Continue"
$Project  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path         # the rmc-spark folder (this script is in scripts\)
$VideoDir = Join-Path $Project "deliverables\5_Execution_Videos"
New-Item -ItemType Directory -Force $VideoDir | Out-Null
Set-Location $Project
$Host.UI.RawUI.WindowTitle = "RMC-Spark - execution video recorder"

function Say($text, $color = "Cyan") { Write-Host ""; Write-Host ">>> $text" -ForegroundColor $color }
function Run($cmd) {
    Write-Host ""
    Write-Host "PS rmc-spark> $cmd" -ForegroundColor Yellow
    Invoke-Expression $cmd
}
function RmcCli($cliArgs) { Run "docker compose exec -T controller python -m controller.cli $cliArgs" }   # not "Cli": that is a built-in alias of Clear-Item
function Open-Urls($urls) { foreach ($u in $urls) { Start-Process $u; Start-Sleep -Milliseconds 700 } }

# ---------------------------------------------------------------- ffmpeg (screen recorder)
function Find-Ffmpeg {
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue |
           Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}
$Ffmpeg = Find-Ffmpeg
if (-not $Ffmpeg) {
    Say "ffmpeg (free screen recorder) is not installed." "Yellow"
    $ans = Read-Host "Install it now with winget (about 100 MB)? [Y/N]"
    if ($ans -notmatch '^[Yy]') { Say "Cannot record without ffmpeg. Closing." "Red"; Read-Host "Press Enter"; exit }
    winget install --id Gyan.FFmpeg -e --accept-source-agreements
    $Ffmpeg = Find-Ffmpeg
    if (-not $Ffmpeg) { Say "ffmpeg still not found - close this window and run the script again." "Red"; Read-Host "Press Enter"; exit }
}

$script:Rec = $null
$script:Single = $false      # true while the one continuous video is being recorded
function Start-Rec($name) {
    if ($script:Single) { return }
    $out = Join-Path $VideoDir "$name.mp4"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Ffmpeg
    $psi.Arguments = "-y -loglevel error -f gdigrab -framerate 15 -draw_mouse 1 -i desktop " +
                     "-vf scale=trunc(iw/2)*2:trunc(ih/2)*2 -c:v libx264 -preset ultrafast -crf 26 -pix_fmt yuv420p `"$out`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.CreateNoWindow = $true
    $script:Rec = [System.Diagnostics.Process]::Start($psi)
    Say "RECORDING  ->  $name.mp4" "Red"
    Start-Sleep 2
}
function Stop-Rec {
    if ($script:Single -and $args.Count -eq 0) { return }
    if ($script:Rec -and -not $script:Rec.HasExited) {
        Start-Sleep 2
        $script:Rec.StandardInput.Write("q")          # ffmpeg finishes the MP4 cleanly on 'q'
        $script:Rec.WaitForExit(20000) | Out-Null
        if (-not $script:Rec.HasExited) { $script:Rec.Kill() }
    }
    Say "Recording stopped and saved." "Green"
}

# ---------------------------------------------------------------- checks
function Check-Docker {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Say "Docker Desktop is not running. Start Docker Desktop, wait until it says 'Engine running', then press Enter." "Yellow"
        Read-Host | Out-Null
        docker info *> $null
        if ($LASTEXITCODE -ne 0) { Say "Docker still not reachable." "Red"; return $false }
    }
    return $true
}
function Test-Controller {
    docker compose exec -T controller python -m controller.cli status *> $null
    return ($LASTEXITCODE -eq 0)
}
function Ensure-Up {
    if (Test-Controller) { return $true }
    Say "Testbed or controller is not running - starting it (not recorded)." "Yellow"
    docker compose up -d
    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep 5
        if (Test-Controller) { Say "Testbed ready." "Green"; Start-Sleep 20; return $true }
        Write-Host "  waiting for the controller... $(($i + 1) * 5) s"
    }
    Say "The controller did not start. Its last log lines:" "Red"
    docker compose logs --tail 40 controller
    return $false
}

# ---------------------------------------------------------------- the videos
function V01 {
    Start-Rec "01_testbed_startup"
    Say "Video 1 - starting the two-cluster Spark testbed (Docker Compose)"
    Run "docker compose up -d"
    Say "Waiting 45 s for both clusters to register their workers..."
    Start-Sleep 45
    for ($i = 0; $i -lt 24 -and -not (Test-Controller); $i++) { Start-Sleep 5 }
    Run "docker compose ps"
    Say "Opening the web UIs: Spark cluster A, Spark cluster B, MinIO storage, Grafana dashboard"
    Open-Urls @("http://localhost:8080", "http://localhost:8090", "http://localhost:9001", "http://localhost:3000")
    Start-Sleep 25
    RmcCli "status"
    Start-Sleep 5
    Stop-Rec
}
function V02 {
    if (-not (Ensure-Up)) { return }
    Start-Rec "02_unit_tests"
    Say "Video 2 - running the 56 automated tests"
    Run "docker compose exec -T controller python -m pytest -v"
    Start-Sleep 5
    Stop-Rec
}
function V03 {
    if (-not (Ensure-Up)) { return }
    Start-Rec "03_data_generation"
    Say "Video 3 - generating the synthetic taxi-trip and graph datasets with Spark"
    Open-Urls @("http://localhost:8080")
    Run "docker compose exec -T controller spark-submit --master spark://spark-master-a:7077 --conf spark.driver.host=controller --total-executor-cores 4 --executor-memory 576m jobs/datagen.py"
    Open-Urls @("http://localhost:9001")
    Start-Sleep 10
    Stop-Rec
}
function V04 {
    if (-not (Ensure-Up)) { return }
    Say "Opening Spark A, Spark B and Grafana - arrange them so this window stays visible, then press Enter." "Yellow"
    if (-not $script:Single) {
        Open-Urls @("http://localhost:8080", "http://localhost:8090", "http://localhost:3000")
        Read-Host | Out-Null
    }
    Start-Rec "04_cluster_outage_failover"
    Say "Video 4 - a job runs, its cluster is killed, RMC-Spark detects the outage and moves the job to the other cluster"
    RmcCli "status"
    Write-Host ""
    Write-Host "PS rmc-spark> docker compose exec -T controller python -m controller.cli submit etl_taxi --mode smart --policy adaptive" -ForegroundColor Yellow
    $sub = docker compose exec -T controller python -m controller.cli submit etl_taxi --mode smart --policy adaptive 2>&1 | Out-String
    Write-Host $sub
    $jobId = if ($sub -match '"job_id":\s*"([^"]+)"') { $matches[1] } else { "etl_taxi" }
    # the controller places the job itself (A or B); the outage must hit the cluster the job runs on
    $target = $null
    for ($i = 0; $i -lt 8; $i++) {
        Start-Sleep 5
        $st = docker compose exec -T controller python -m controller.cli status 2>&1 | Out-String
        Write-Host $st
        if ($st -match ("job " + [regex]::Escape($jobId) + ": RUNNING on (\w+)")) { $target = $matches[1] }
    }
    if (-not $target) { $target = "A" }
    $other = if ($target -eq "A") { "B" } else { "A" }
    Say "Job $jobId is running on cluster $target. INJECTING FAULT: full outage of cluster $target" "Red"
    RmcCli "chaos cluster_outage --cluster $target"
    Say "Watch: the controller detects the outage of $target and moves the job to cluster $other"
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep 5
        $s = docker compose exec -T controller python -m controller.cli status 2>&1 | Out-String
        Write-Host $s
        if ($s -match ("job " + [regex]::Escape($jobId) + ": (SUCCEEDED|FAILED)")) { break }
    }
    Say "Why the controller acted - the explained decision log"
    RmcCli "decisions --limit 20"
    Say "Restoring cluster $target"
    RmcCli "restore"
    Start-Sleep 5
    Stop-Rec
}
function V05 {
    if (-not (Ensure-Up)) { return }
    Start-Rec "05_decision_log"
    Say "Video 5 - explainable decisions and the reliability score per cluster"
    RmcCli "decisions --limit 20"
    RmcCli "status"
    Open-Urls @("http://localhost:8000/docs", "http://localhost:3000")
    Start-Sleep 20
    Stop-Rec
}
function V06 {
    Start-Rec "06_results"
    Say "Video 6 - measured results of the 36-run experiment (results/raw and results/report)"
    Run "Get-ChildItem results\raw\minimum | Format-Table Name, Length -AutoSize"
    Run "Import-Csv results\raw\minimum\runs.csv | Group-Object system, fault | Select-Object Count, Name | Format-Table -AutoSize"
    Run "Get-Content 'results\report\Table 11 Experimental Results Summary.md'"
    foreach ($f in Get-ChildItem "results\report\Fig *.png") { Start-Process $f.FullName; Start-Sleep 6 }
    Start-Sleep 5
    Stop-Rec
}

# ---------------------------------------------------------------- one continuous video
Clear-Host
Write-Host "RMC-Spark - execution video (one continuous recording)" -ForegroundColor Cyan
Write-Host "Saved as: $(Join-Path $VideoDir 'RMC-Spark_Execution_Demo.mp4')"
Write-Host ""
Write-Host "It records, in order: testbed start-up -> 56 tests -> data generation ->"
Write-Host "cluster-outage failover with the explained decisions -> experiment results."
Write-Host "Total about 10-15 minutes. Do not type in this window while it records."
if (-not (Check-Docker)) { Read-Host "Press Enter to close"; exit }

# start every container first and wait until all web UIs answer, so the browser tabs load
function Test-Url($u) {
    try { Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}
Say "Starting the testbed and waiting until Spark A, Spark B, Grafana and the controller respond (not recorded)..." "Yellow"
docker compose up -d
$urls = "http://localhost:8080", "http://localhost:8090", "http://localhost:3000", "http://localhost:8000/docs"
$ready = $false
for ($i = 0; $i -lt 48; $i++) {
    $down = @($urls | Where-Object { -not (Test-Url $_) })
    $st = docker compose exec -T controller python -m controller.cli status 2>$null | Out-String
    if ($down.Count -eq 0 -and $st -match "cluster A: HEALTHY" -and $st -match "cluster B: HEALTHY") { $ready = $true; break }
    if ($down.Count -eq 0) { $down = @("controller still marks a cluster unhealthy") }
    Write-Host ("  {0,3} s - still starting: {1}" -f (($i + 1) * 5), ($down -join ", "))
    $sparkDown = @($down | Where-Object { $_ -match ":80[89]0" })
    if ($i -eq 5 -and ($sparkDown.Count -gt 0 -or $st -match "FAILED") -and (Test-Controller)) {
        # a fault left over from an earlier experiment (disconnected network, netem delay, paused or
        # killed container) is not undone by 'docker compose up'; the fault injector's restore is
        Say "A Spark master is still not answering - undoing any leftover injected fault (restore)..." "Yellow"
        docker unpause rmc-master-a rmc-worker-a1 rmc-worker-a2 rmc-master-b rmc-worker-b1 rmc-worker-b2 *> $null
        docker compose exec -T controller python -m controller.cli restore
    }
    if ($i -eq 17 -and $sparkDown.Count -gt 0) {
        Say "Still not answering - restarting the Spark clusters..." "Yellow"
        docker compose restart spark-master-a spark-master-b spark-worker-a1 spark-worker-a2 spark-worker-b1 spark-worker-b2
    }
    Start-Sleep 5
}
if (-not $ready) {
    Say "The testbed did not come up within 4 minutes. Container status:" "Red"
    docker compose ps -a
    Say "Last log lines of Spark master A and the controller:" "Red"
    docker compose logs --tail 25 spark-master-a controller
    Read-Host "Send a screenshot of this window. Press Enter to close"
    exit
}
Say "Testbed ready." "Green"

Say "Opening Spark A, Spark B and Grafana. Arrange the browser and this window side by side," "Yellow"
Say "close anything private (the whole screen is recorded), then press Enter to START recording." "Yellow"
Open-Urls @("http://localhost:8080", "http://localhost:8090", "http://localhost:3000")
Read-Host | Out-Null

$script:Single = $false
Start-Rec "RMC-Spark_Execution_Demo"
$script:Single = $true
$started = Get-Date
foreach ($step in "V01", "V02", "V03", "V04", "V06") {
    try { & $step } catch { Write-Host $_ -ForegroundColor Red }
}
Say ("Demo complete - total time {0:mm\:ss}" -f ((Get-Date) - $started)) "Green"
Start-Sleep 3
Stop-Rec "final"
$script:Single = $false
Write-Host ""
Write-Host "Video saved: $(Join-Path $VideoDir 'RMC-Spark_Execution_Demo.mp4')" -ForegroundColor Green
Read-Host "Press Enter to close"
