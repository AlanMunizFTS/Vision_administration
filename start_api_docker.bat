@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    echo Missing .env file. Copy .env.example to .env and update the database values.
    exit /b 1
)

docker compose up --build
