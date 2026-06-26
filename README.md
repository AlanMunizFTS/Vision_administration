# Vision Administration

API y dashboard local de solo lectura para consultar reportes desde `public.model_results_central`.

## Ejecutar con Docker

Requisitos:

- Docker Desktop abierto.
- PostgreSQL levantado en tu PC o en otro host accesible.
- `.env` con los datos reales de PostgreSQL.

Arranque recomendado:

```powershell
.\start_api_docker.bat
```

O directamente:

```powershell
docker compose up --build
```

En Docker, quedan disponibles:

```text
Dashboard: http://127.0.0.1:3000
API:       http://127.0.0.1:8000
Docs API:  http://127.0.0.1:8000/docs
```

La pagina divide los reportes por `source_station`, muestra resumen global, graficas por hora/dia, top 3 defectos y tabla de piezas por JSN.

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

O con un solo comando:

```powershell
.\start_api.bat
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
- `GET /api/v1/reports/excel`

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

Con la API levantada, genera un reporte agregado de los ultimos 30 dias:

```powershell
.\venv\Scripts\python.exe scripts\generate_excel_report.py
```

El archivo se guarda en `reports/vision_report_YYYYMMDD_HHMMSS.xlsx`. El Excel incluye hojas globales y hojas separadas por `source_station`.

Parametros utiles:

```powershell
.\venv\Scripts\python.exe scripts\generate_excel_report.py --days 30
.\venv\Scripts\python.exe scripts\generate_excel_report.py --start-at "2026-05-27T00:00:00" --end-at "2026-06-26T23:59:59"
.\venv\Scripts\python.exe scripts\generate_excel_report.py --source-station station-a --source-id 2
```

Si estas usando Docker, reconstruye el contenedor y ejecuta el script dentro de `vision-api`:

```powershell
docker compose up --build -d
docker compose exec vision-api python scripts/generate_excel_report.py
```

El volumen `./reports:/app/reports` hace que el Excel quede disponible en la carpeta local `reports`.
