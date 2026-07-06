# AGENTS.md

Instructions for agents and collaborators working in this repository.

## Project Context

This app combines a FastAPI backend, a React/Vite frontend, and an Excel generator. Reports read data from `public.model_results_central`; `glidepath` and `change-log` create and update their own auxiliary tables.

## Before Changing Code

- Review `REPO_MAP.md` to locate the correct area.
- Use `rg` to search for references before deleting or renaming files, routes, endpoints, or fields.
- Do not delete `scripts/generate_excel_report.py`: it is also imported from `app/main.py`.
- Do not assume everything is read-only: `glidepath` and `change-log` include `POST`, `PATCH`, and `DELETE` operations.
- Do not modify `.env` with real secrets. Use `.env.example` to document variables.

## Backend

- Entry point: `app/main.py`.
- Keep shared SQL logic in `app/reports.py` when it affects reports or reject summary behavior.
- Keep glidepath CRUD in `app/glidepath.py` and process-change CRUD in `app/change_log.py`.
- If you add filter parameters or endpoint parameters, update the frontend, Excel generator, and related tests.
- Report validation errors must be converted to HTTP 400 via `handle_report_error`.

## Frontend

- Entry point: `frontend/src/main.jsx`.
- Endpoints are called through relative `/api/...` routes; locally Vite uses a proxy and in Docker Nginx uses `vision-api`.
- Keep compatibility between visible dashboard filters and the payload used for Excel export.
- If you rename API fields, review aggregations such as `filterReportData`, `combinedAsStationData`, and `plantWideData`.

## Excel

- `scripts/generate_excel_report.py` supports two paths:
  - CLI: calls `/health` and `/api/v1/reject-summary`.
  - API/frontend: receives already loaded data and builds the workbook.
- If you change the `reject-summary` structure, update the workbook and tests.

## Recommended Tests

After Python changes:

```powershell
.\venv\Scripts\python.exe -m unittest discover
```

After frontend changes:

```powershell
cd frontend
npm run build
```

After Docker changes:

```powershell
docker compose up --build
```

## Documentation

- Update `README.md` when commands, endpoints, environment variables, or visible behavior change.
- Update `REPO_MAP.md` when you add, move, or remove major files.
- Keep this file focused on operational instructions, not a long product description.

## Cleanup

Do not confuse generated artifacts with dead code. These directories/files may be cleaned locally, but they are not part of the product:

- `frontend/dist/`
- `reports/*.xlsx`
- `.agents/*.log`
- `__pycache__/`
- `.pytest_cache/`
- `venv/`
- `frontend/node_modules/`
