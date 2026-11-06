@echo off
echo ========================================================================
echo   Starting Raphael FastAPI Backend Server
echo ========================================================================
echo   Local URL    : http://127.0.0.1:8000
echo   API Docs     : http://127.0.0.1:8000/docs
echo   Health Check : http://127.0.0.1:8000/health
echo ========================================================================

set PYTHONPATH=.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
