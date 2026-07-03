# Repo Map

Mapa rapido del repositorio `Vision_administration`.

## Proposito

Dashboard y API local para analizar resultados de vision desde `public.model_results_central`, exportar reportes Excel, administrar glidepaths y registrar cambios de proceso.

## Raiz

- `README.md`: guia de ejecucion, endpoints principales y uso del reporte Excel.
- `docker-compose.yml`: levanta backend `vision-api` y frontend `vision-web`.
- `Dockerfile`: imagen del backend FastAPI.
- `requirements.txt`: dependencias Python del backend y generador Excel.
- `.env.example`: variables requeridas para conectar PostgreSQL.
- `.gitignore`: ignora entorno virtual, cache, logs y reportes generados.

## Backend

- `app/main.py`: aplicacion FastAPI, rutas HTTP, modelos Pydantic y respuestas Excel.
- `app/db.py`: pool de conexiones PostgreSQL con `psycopg2`.
- `app/config.py`: carga `.env` local y valida variables de base de datos.
- `app/reports.py`: consultas SQL y agregaciones para resultados, piezas, defectos, series de tiempo y resumen de rechazos.
- `app/glidepath.py`: tablas auxiliares y CRUD para proyectos, subproyectos y milestones de glidepath.
- `app/change_log.py`: tablas auxiliares y CRUD para eventos de cambios de proceso.

## Frontend

- `frontend/src/main.jsx`: app React completa, filtros, vistas Overall/Machine/Head, graficas, glidepaths, change log y exportacion Excel.
- `frontend/src/styles.css`: estilos del dashboard.
- `frontend/package.json`: scripts Vite (`dev`, `build`, `preview`) y dependencias React/Recharts/Lucide.
- `frontend/vite.config.js`: proxy local de `/api` hacia `http://127.0.0.1:8000`.
- `frontend/Dockerfile`: build Vite y entrega con Nginx.
- `frontend/nginx.conf`: proxy Docker de `/api` hacia `vision-api:8000`.

## Scripts

- `scripts/generate_excel_report.py`: generador de workbook Excel. Se usa como CLI y tambien lo importa `app/main.py` para `/api/v1/reports/excel`.

## Tests

- `tests/test_reports.py`: pruebas de filtros, SQL generado y forma del resumen de rechazos.
- `tests/test_excel_endpoint.py`: pruebas del endpoint Excel de FastAPI sin consultar la base real.
- `tests/test_generate_excel_report.py`: pruebas del workbook, colores, filtros y guardado del Excel.

## Artefactos Locales

Estos no son codigo fuente y no deben versionarse:

- `venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `reports/*.xlsx`
- `.agents/*.log`
- `__pycache__/`
- `.pytest_cache/`

## Flujos Principales

- Docker completo: `docker compose up --build`
- Backend local: `.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- Frontend local: desde `frontend/`, `npm run dev`
- Tests Python: `.\venv\Scripts\python.exe -m unittest discover`
- Build frontend: desde `frontend/`, `npm run build`

