# Vision Administration

API y dashboard local para consultar reportes desde `public.model_results_central`, administrar glidepaths y registrar cambios de proceso.

## Ejecutar con Docker

Requisitos:

- Docker Desktop abierto.
- PostgreSQL levantado en tu PC o en otro host accesible.
- `.env` con los datos reales de PostgreSQL.

Arranque recomendado:

```powershell
docker compose up --build
```

En Docker, quedan disponibles:

```text
Dashboard: http://127.0.0.1:3000
API:       http://127.0.0.1:8000
Docs API:  http://127.0.0.1:8000/docs
```

El dashboard permite revisar la planta completa, maquinas combinadas LEFT+RIGHT o cabezales individuales. Incluye filtros por fecha, maquina y `part_number`, graficas por dia, defectos por condicion, top 3 historico, metas de glidepath, marcadores de cambios de proceso y descarga de Excel.

Los servicios quedan vivos mientras el compose siga corriendo. Para detenerlos, usa `Ctrl+C`; si los levantaste en segundo plano con `-d`, usa:

```powershell
docker compose down
```

Para ver los logs:

```powershell
docker compose logs vision-api
docker compose logs vision-web
```

Para seguirlos en vivo:

```powershell
docker compose logs -f vision-api
```

Nota: dentro de Docker, `127.0.0.1` apunta al contenedor, no a tu PC. Por eso `docker-compose.yml` usa `host.docker.internal` como `DB_HOST` por defecto. Si PostgreSQL esta en otro equipo, agrega en `.env`:

```text
API_DB_HOST=192.168.x.x
```

## Ejecutar sin Docker

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con los datos reales de PostgreSQL.

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

La API queda viva mientras el comando siga abierto. Para detenerla, usa `Ctrl+C`.

Documentacion interactiva:

```text
http://127.0.0.1:8000/docs
```

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

Nota: los endpoints de reportes leen `public.model_results_central`; los endpoints de glidepath y change log crean tablas auxiliares propias para guardar proyectos, metas y eventos de cambio.

## Reglas

- La pieza se identifica por `source_station` + `jsn`.
- `captured_at` sale del JSN usando el formato `MMDDYYHHMMSS` en posiciones 6 a 17.
- Una pieza es `OK` si todas sus detecciones tienen `class_name = OK`.
- Una pieza es `NOK` si tiene al menos una deteccion no-OK.
- El defecto principal es la deteccion no-OK con mayor `confidence`.
- Los filtros de fecha usan `captured_at`.

## Ejemplo desde Python

```python
import requests

response = requests.get("http://127.0.0.1:8000/api/v1/summary", timeout=10)
response.raise_for_status()
print(response.json())
```

## Reporte Excel

Con la API levantada, genera un reporte basado en las mismas pestañas del frontend para los ultimos 7 dias:

```powershell
.\venv\Scripts\python.exe scripts\generate_excel_report.py
```

El archivo se guarda en `reports/vision_report_YYYYMMDD_HHMMSS.xlsx`. El Excel incluye las hojas `Por dia`, `Per Condition` y `Top 3 Historico`, con tablas y autofiltros basicos de Excel.

Parametros utiles:

```powershell
.\venv\Scripts\python.exe scripts\generate_excel_report.py --days 7
.\venv\Scripts\python.exe scripts\generate_excel_report.py --start-at "2026-06-19T00:00:00" --end-at "2026-06-26T23:59:59"
.\venv\Scripts\python.exe scripts\generate_excel_report.py --source-station station-a
.\venv\Scripts\python.exe scripts\generate_excel_report.py --part-number PN-1 --part-number PN-2
```

Desde el frontend, la descarga de Excel usa los datos ya cargados en el dashboard para generar el archivo mas rapido y replicar lo visible. Los filtros disponibles para el reporte son fecha, `source_station` y `part_number`; `JSN` ya no esta disponible como filtro.

Si estas usando Docker, reconstruye el contenedor y ejecuta el script dentro de `vision-api`:

```powershell
docker compose up --build -d
docker compose exec vision-api python scripts/generate_excel_report.py
```

El volumen `./reports:/app/reports` hace que el Excel quede disponible en la carpeta local `reports`.
