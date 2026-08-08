# ============================================================
#  LeadGen AI - Start Backend
#  Launches uvicorn (main:app) on http://localhost:8000 with
#  --reload, in the background. Logs go to backend\uvicorn.log
#  and backend\uvicorn.err.log. Saved PID -> backend\.server.pid
#
#  Double-click start-server.cmd  OR  run:  .\start-server.ps1
# ============================================================
$ErrorActionPreference = "Stop"

$Root    = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python  = Join-Path $Backend "venv\Scripts\python.exe"
$PidFile = Join-Path $Backend ".server.pid"
$Url     = "http://localhost:8000/"

if (-not (Test-Path $Python)) {
    Write-Host "[ERROR] Backend venv not found:" -ForegroundColor Red
    Write-Host "        $Python" -ForegroundColor Red
    Write-Host "        Run setup.ps1 first, then try again." -ForegroundColor Yellow
    exit 1
}

Write-Host "LeadGen AI - backend launcher" -ForegroundColor Cyan
Write-Host "URL: $Url" -ForegroundColor DarkGray

# ---- Load a valid PID from the pid file (if any) -------------------
function Read-PidFile {
    if (-not (Test-Path $PidFile)) { return $null }
    $raw = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $raw) { return $null }
    $n = 0
    if ([int]::TryParse($raw.Trim(), [ref]$n)) { return $n }
    return $null
}

# ---- 1) Already running under our pid file? ------------------------
$savedPid = Read-PidFile
if ($savedPid -and (Get-Process -Id $savedPid -ErrorAction SilentlyContinue)) {
    Write-Host "[OK] Backend already running (PID $savedPid). Opening dashboard..." -ForegroundColor Green
    Start-Process $Url
    exit 0
}

# ---- 2) Port 8000 busy with a LeadGen dashboard already? ------------
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200 -and $resp.Content -match "LeadGen AI") {
            Write-Host "[OK] A LeadGen dashboard is already running on port 8000. Opening browser..." -ForegroundColor Green
            Start-Process $Url
            exit 0
        }
    } catch { }

    Write-Host "[WARNING] Port 8000 is busy, but it is NOT serving the LeadGen dashboard." -ForegroundColor Red
    Write-Host "          It may be a stale/old server. Run stop-server.cmd, then start again." -ForegroundColor Yellow
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
    exit 1
}

# ---- 3) Everything is clear — launch a fresh server -----------------
Write-Host "[START] Launching uvicorn (main:app --host 127.0.0.1 --port 8000 --reload)..." -ForegroundColor Yellow

$outLog = Join-Path $Backend "uvicorn.log"
$errLog = Join-Path $Backend "uvicorn.err.log"

try {
    $proc = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload") `
        -WorkingDirectory $Backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru
} catch {
    Write-Host "[ERROR] Could not start uvicorn: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$proc.Id | Set-Content $PidFile
Write-Host "[OK] Started (PID $($proc.Id)). Waiting for it to come up..." -ForegroundColor Green

$up = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 750
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch { }
}

if ($up) {
    Write-Host "[OK] Backend is live at $Url" -ForegroundColor Green
    Start-Process $Url
} else {
    Write-Host "[ERROR] Backend did not respond within 30s." -ForegroundColor Red
    Write-Host "        Check the logs: backend\uvicorn.err.log" -ForegroundColor Yellow
    exit 1
}