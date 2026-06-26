@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    echo Missing .env file. Copy .env.example to .env and update the database values.
    exit /b 1
)

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
