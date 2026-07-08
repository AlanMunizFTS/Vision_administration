# Vision Administration

Local API and dashboard for querying reports from `public.model_results_central`, managing glidepaths, and tracking process changes.

## Run With Docker

Requirements:

- Docker Desktop running.
- `.env` populated with the project PostgreSQL values.

The Docker stack includes its own dedicated PostgreSQL container, so it does not need to reuse another local database service. Automatic SQL migrations are controlled with `RUN_MIGRATIONS`.
`DB_NAME`, `DB_USER`, and `DB_PASSWORD` initialize PostgreSQL and are also used by the API. `DB_PORT` publishes PostgreSQL to your machine; inside Docker, the API always connects to `vision-db:5432`.

Recommended startup:

```powershell
docker compose up --build
```

If you want the containers in the background:

```powershell
docker compose up --build -d
```

If `vision-api` and `vision-web` already exist and you only need to add the
dedicated PostgreSQL container, start just the database first:

```powershell
docker compose up -d vision-db
```

Then restart only the API so it picks up the internal Docker database host
(`vision-db:5432`). The web container can keep running:

```powershell
docker compose up -d --no-deps --force-recreate vision-api
```

When running in Docker, these services are available:

```text
Dashboard: http://127.0.0.1:3000
API:       http://127.0.0.1:8000
API Docs:  http://127.0.0.1:8000/docs
Postgres:  127.0.0.1:5433
```

The dashboard lets you review the whole plant, combined LEFT+RIGHT machines, or individual heads. It includes filters for date, machine, and `part_number`, day-by-day charts, per-condition defects, top 3 history, glidepath targets, process-change markers, and Excel export.

The services stay up while `docker compose` is running. To stop them, press `Ctrl+C`; if you started them in the background with `-d`, use:

```powershell
docker compose down
```

To view logs:

```powershell
docker compose logs vision-api
docker compose logs vision-web
```

To stream logs live:

```powershell
docker compose logs -f vision-api
```

Startup migrations are controlled from `.env`:

```text
RUN_MIGRATIONS=true
```

Inside Docker, the API connects to the `vision-db` service over the Compose network. Outside Docker, local tools can reach the same database with the `DB_*` values from `.env`, which default to `127.0.0.1:5433`.

## Run Without Docker

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your real PostgreSQL values.

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API stays up while that command is running. To stop it, press `Ctrl+C`.

Interactive documentation:

```text
http://127.0.0.1:8000/docs
```

## Sincronizar bases remotas

El flujo unificado esta en `app/IE_db.py`. Lee las estaciones desde `.env`, exporta por SSH, transforma los datos e importa a PostgreSQL central con un solo log.

Configura las estaciones en `.env` con este formato:

```text
SYNC_STATIONS=STATION_A|192.168.1.10|station_a_db.sql|true;STATION_B|192.168.1.11|station_b_db.sql|true
```

Cada estacion usa `name|ip|output_file|enabled`, y las estaciones se separan con `;`. No guardes IPs, usuarios o nombres reales en archivos versionados.

```powershell
py -m app.IE_db
```

Por defecto guarda:

- Log unico: `app\sync.log`
- Dumps diarios: `app\Database_ddMMyy`
- SQL temporal: `app\Database_ddMMyy\_temp`, eliminado al terminar

El sync puede preparar una llave SSH local si no existe y saltar ese paso cuando la conexion ya funciona. Para instalar la llave automaticamente en las estaciones se requiere `SYNC_SSH_COPY_PASSWORD`; si no se define, el log indicara que la llave debe instalarse manualmente. `SYNC_SSH_AUTHORIZED_KEYS_MODE` acepta `windows_admin`, `windows_user` o `linux_user`.

El backend expone `POST /api/v1/sync-db` para iniciar la sincronizacion y `GET /api/v1/sync-db` para consultar estado/log. Para conectar esto a un boton, el backend debe correr con acceso a `ssh` y a PostgreSQL central. En Docker puede usar `psql` directo con `SYNC_POSTGRES_HOST`; fuera de Docker puede usar `docker exec` contra `SYNC_POSTGRES_DOCKER_CONTAINER`.

## Endpoints

- `GET /health`
- `GET /api/v1/options`
- `GET /api/v1/results`
- `GET /api/v1/pieces`
- `GET /api/v1/summary`
- `GET /api/v1/defects`
- `GET /api/v1/timeseries?bucket=hour`
- `GET /api/v1/stations/summary`
- `GET /api/v1/stations/defects`
- `GET /api/v1/stations/timeseries?bucket=hour`
- `GET /api/v1/reject-summary`
- `GET /api/v1/reports/excel`
- `POST /api/v1/reports/excel`
- `GET /api/v1/glidepath/projects`
- `POST /api/v1/glidepath/projects`
- `PATCH /api/v1/glidepath/projects/{project_id}`
- `DELETE /api/v1/glidepath/projects/{project_id}`
- `POST /api/v1/glidepath/projects/{project_id}/subprojects`
- `PATCH /api/v1/glidepath/subprojects/{subproject_id}`
- `DELETE /api/v1/glidepath/subprojects/{subproject_id}`
- `POST /api/v1/glidepath/subprojects/{subproject_id}/milestones`
- `PATCH /api/v1/glidepath/milestones/{milestone_id}`
- `DELETE /api/v1/glidepath/milestones/{milestone_id}`
- `GET /api/v1/change-log`
- `POST /api/v1/change-log`
- `PATCH /api/v1/change-log/{entry_id}`
- `DELETE /api/v1/change-log/{entry_id}`

Note: report endpoints read from `public.model_results_central`; glidepath and change-log endpoints create their own auxiliary tables to store projects, targets, and change events.

## Rules

- A piece is identified by `source_station` + `jsn`.
- `captured_at` is parsed from the JSN using the `MMDDYYHHMMSS` format in positions 6 to 17.
- A piece is `OK` when all detections have `class_name = OK`.
- A piece is `NOK` when it has at least one non-OK detection.
- The primary defect is the non-OK detection with the highest `confidence`.
- Date filters use `captured_at`.

## Python Example

```python
import requests

response = requests.get("http://127.0.0.1:8000/api/v1/summary", timeout=10)
response.raise_for_status()
print(response.json())
```

## Excel Report

With the API running, generate a report based on the same frontend tabs for the last 7 days:

```powershell
.\venv\Scripts\python.exe scripts\generate_excel_report.py
```

The file is saved to `reports/vision_report_YYYYMMDD_HHMMSS.xlsx`. The workbook includes the `By Day`, `Per Condition`, and `Top 3 History` sheets, with tables and basic Excel autofilters.

Useful parameters:

```powershell
.\venv\Scripts\python.exe scripts\generate_excel_report.py --days 7
.\venv\Scripts\python.exe scripts\generate_excel_report.py --start-at "2026-06-19T00:00:00" --end-at "2026-06-26T23:59:59"
.\venv\Scripts\python.exe scripts\generate_excel_report.py --source-station station-a
.\venv\Scripts\python.exe scripts\generate_excel_report.py --part-number PN-1 --part-number PN-2
```

From the frontend, Excel export uses the data already loaded in the dashboard so generation is faster and matches what is visible. The available report filters are date, `source_station`, and `part_number`; `JSN` is no longer available as a filter.

If you are using Docker, rebuild the container and run the script inside `vision-api`:

```powershell
docker compose up --build -d
docker compose exec vision-api python scripts/generate_excel_report.py
```

The `./reports:/app/reports` volume makes the Excel file available in the local `reports` folder.
