# ==============================================================================
# Raphael API Server Startup Script (PowerShell)
# Starts the FastAPI backend with uvicorn on Windows / local environments
# ==============================================================================

param (
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload = $false
)

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Starting Raphael FastAPI Backend Server" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Local URL    : http://$HostAddress`:$Port" -ForegroundColor Green
Write-Host "  API Docs     : http://$HostAddress`:$Port/docs" -ForegroundColor Yellow
Write-Host "  Health Check : http://$HostAddress`:$Port/health" -ForegroundColor Gray
Write-Host "========================================================================" -ForegroundColor Cyan

$env:PYTHONPATH = "."

$PythonCmd = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $PythonCmd = ".\.venv\Scripts\python.exe"
}

if ($Reload) {
    Write-Host "[Mode] Auto-reload enabled" -ForegroundColor Magenta
    & $PythonCmd -m uvicorn backend.main:app --host $HostAddress --port $Port --reload
} else {
    Write-Host "[Mode] Production single-process" -ForegroundColor Gray
    & $PythonCmd -m uvicorn backend.main:app --host $HostAddress --port $Port
}
