# Repo Map

Quick map of the `Vision_administration` repository.

## Purpose

Local dashboard and API for analyzing vision results from `public.model_results_central`, exporting Excel reports, managing glidepaths, tracking process changes, and associating logs with employees.

## Root

- `README.md`: run guide, main endpoints, and Excel report usage.
- `docker-compose.yml`: starts the `vision-db` PostgreSQL service, the `vision-api` backend, and the `vision-web` frontend.
- `Dockerfile`: FastAPI backend image.
- `requirements.txt`: Python dependencies for the backend and Excel generator.
- `.env.example`: required variables for PostgreSQL connectivity.
- `.gitignore`: ignores the virtual environment, cache, logs, and generated reports.

## Backend

- `app/main.py`: FastAPI app, HTTP routes, Pydantic models, and Excel responses.
- `app/db.py`: PostgreSQL connection pool using `psycopg2`.
- `app/config.py`: loads local `.env` values and validates database settings.
- `app/reports.py`: SQL queries and aggregations for results, pieces, defects, time series, and reject summary.
- `app/glidepath.py`: auxiliary tables and CRUD for glidepath projects, subprojects, and milestones.
- `app/change_log.py`: auxiliary tables and CRUD for employees and process change events.

## Frontend

- `frontend/src/main.jsx`: complete React app with filters, Overall/Machine/Head views, charts, glidepaths, employee management, change log, and Excel export.
- `frontend/src/styles.css`: dashboard styles.
- `frontend/package.json`: Vite scripts (`dev`, `build`, `preview`) and React/Recharts/Lucide dependencies.
- `frontend/vite.config.js`: local `/api` proxy to `http://127.0.0.1:8000`.
- `frontend/Dockerfile`: Vite build served with Nginx.
- `frontend/nginx.conf`: Docker `/api` proxy to `vision-api:8000`.

## Scripts

- `scripts/generate_excel_report.py`: Excel workbook generator. It runs as a CLI tool and is also imported by `app/main.py` for `/api/v1/reports/excel`.

## Tests

- `tests/test_reports.py`: filter tests, generated SQL checks, and reject summary shape validation.
- `tests/test_excel_endpoint.py`: FastAPI Excel endpoint tests without hitting the real database.
- `tests/test_generate_excel_report.py`: workbook, color, filter, and Excel save tests.

## Local Artifacts

These are not source code and should not be committed:

- `venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `reports/*.xlsx`
- `.agents/*.log`
- `__pycache__/`
- `.pytest_cache/`

## Main Workflows

- Full Docker stack: `docker compose up --build`
- Local backend: `.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- Local frontend: from `frontend/`, run `npm run dev`
- Python tests: `.\venv\Scripts\python.exe -m unittest discover`
- Frontend build: from `frontend/`, run `npm run build`
