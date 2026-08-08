# Lead-Gen SaaS setup script (Windows PowerShell)
# Run from the leadgen-saas/leadgen-saas directory:
#   .\setup.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host "=== Lead-Gen SaaS Setup ===" -ForegroundColor Cyan

# Backend
Write-Host "`n[1/3] Setting up backend..." -ForegroundColor Yellow
Push-Location "$Root\backend"
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Pop-Location

# Scraper
Write-Host "`n[2/3] Setting up scraper..." -ForegroundColor Yellow
Push-Location "$Root\scraper"
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Pop-Location

Write-Host "`n[3/3] Setup complete!" -ForegroundColor Green
Write-Host @"

Next steps:
  1. Install Ollama (optional, for AI features): https://ollama.com/download
     ollama pull llama3.1

  2. Start the API server:
     cd backend
     .\venv\Scripts\Activate.ps1
     uvicorn main:app --reload

  3. Open http://localhost:8000/docs for the interactive API docs

  4. Test a scrape (requires Playwright/Chromium):
     curl -X POST http://localhost:8000/search-jobs `
       -H "Content-Type: application/json" `
       -d '{\"query\": \"dentists in Karachi\", \"limit\": 10}'

"@
