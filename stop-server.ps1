# ============================================================
#  LeadGen AI - Stop Backend
#  Stops the uvicorn server started by start-server.ps1
#  (kills the saved process tree, then hunts any stray backend
#   uvicorn processes) and confirms port 8000 is free.
#
#  Double-click stop-server.cmd  OR  run:  .\stop-server.ps1
# ============================================================
$ErrorActionPreference = "Stop"

$Root    = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$PidFile = Join-Path $Backend ".server.pid"
$Url     = "http://localhost:8000/"

Write-Host "LeadGen AI - backend stopper" -ForegroundColor Cyan

$stopped = $false

# ---- 1) Stop the process tree saved by start-server.ps1 -------------
function Read-PidFile {
    if (-not (Test-Path $PidFile)) { return $null }
    $raw = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $raw) { return $null }
    $n = 0
    if ([int]::TryParse($raw.Trim(), [ref]$n)) { return $n }
    return $null
}

$savedPid = Read-PidFile
if ($savedPid) {
    if (Get-Process -Id $savedPid -ErrorAction SilentlyContinue) {
        try { & taskkill /PID $savedPid /T /F 2>$null | Out-Null } catch { }
        Write-Host "[OK] Stopped PID $savedPid (and its child processes)" -ForegroundColor Green
        $stopped = $true
    } else {
        Write-Host "[INFO] PID $savedPid is not running (already stopped)." -ForegroundColor DarkGray
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "[INFO] No PID file found ($PidFile)." -ForegroundColor DarkGray
}

# ---- 2) Fallback: stop any stray still-running uvicorn from this project ----------
$stragglers = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='uvicorn.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and $_.CommandLine -like "*$Root*" -and $_.CommandLine -like "*uvicorn*" -and
        (Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue)
    }
foreach ($p in $stragglers) {
    try { & taskkill /PID $p.ProcessId /T /F 2>$null | Out-Null } catch { }
    Write-Host "[OK] Stopping stray uvicorn process $($p.ProcessId)" -ForegroundColor Green
    $stopped = $true
}

# ---- 3) Confirm ------------------------------------------------------
Start-Sleep -Seconds 1
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Host "[WARNING] Port 8000 is still in use by PID $($listener.OwningProcess)." -ForegroundColor Yellow
    Write-Host "          This is not our backend, so we left it alone." -ForegroundColor DarkGray
} elseif ($stopped) {
    Write-Host "[OK] Backend stopped. $Url is now free." -ForegroundColor Green
} else {
    Write-Host "[INFO] Nothing was running." -ForegroundColor DarkGray
}