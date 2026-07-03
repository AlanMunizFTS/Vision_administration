# AGENTS.md

Instrucciones para agentes y colaboradores que trabajen en este repositorio.

## Contexto Del Proyecto

Esta app combina un backend FastAPI, un frontend React/Vite y un generador Excel. Los reportes leen datos desde `public.model_results_central`; `glidepath` y `change-log` crean y modifican tablas auxiliares propias.

## Antes De Cambiar Codigo

- Revisa `REPO_MAP.md` para ubicar el area correcta.
- Usa `rg` para buscar referencias antes de borrar o renombrar archivos, rutas, endpoints o campos.
- No borres `scripts/generate_excel_report.py`: tambien se importa desde `app/main.py`.
- No asumas que todo es solo lectura: `glidepath` y `change-log` tienen operaciones `POST`, `PATCH` y `DELETE`.
- No modifiques `.env` con secretos reales. Usa `.env.example` para documentar variables.

## Backend

- Punto de entrada: `app/main.py`.
- Manten la logica SQL compartida en `app/reports.py` cuando afecte reportes o resumen de rechazos.
- Manten CRUD de glidepath en `app/glidepath.py` y CRUD de cambios en `app/change_log.py`.
- Si agregas parametros a filtros o endpoints, actualiza frontend, Excel y tests relacionados.
- Los errores de validacion de reportes deben convertirse a HTTP 400 mediante `handle_report_error`.

## Frontend

- Punto de entrada: `frontend/src/main.jsx`.
- Los endpoints se llaman con rutas relativas `/api/...`; en local Vite usa proxy y en Docker Nginx usa `vision-api`.
- Conserva la compatibilidad entre filtros visibles del dashboard y el payload usado para exportar Excel.
- Si cambias nombres de campos del API, revisa agregaciones como `filterReportData`, `combinedAsStationData` y `plantWideData`.

## Excel

- `scripts/generate_excel_report.py` soporta dos caminos:
  - CLI: consulta `/health` y `/api/v1/reject-summary`.
  - API/frontend: recibe datos ya cargados y construye el workbook.
- Si cambias estructura de `reject-summary`, actualiza workbook y pruebas.

## Pruebas Recomendadas

Despues de cambios Python:

```powershell
.\venv\Scripts\python.exe -m unittest discover
```

Despues de cambios frontend:

```powershell
cd frontend
npm run build
```

Despues de cambios Docker:

```powershell
docker compose up --build
```

## Documentacion

- Actualiza `README.md` cuando cambien comandos, endpoints, variables de entorno o comportamiento visible.
- Actualiza `REPO_MAP.md` cuando agregues, muevas o elimines archivos principales.
- Manten este archivo enfocado en instrucciones operativas, no en descripcion larga del producto.

## Limpieza

No confundas artefactos generados con codigo muerto. Estos directorios/archivos pueden limpiarse localmente, pero no son parte del producto:

- `frontend/dist/`
- `reports/*.xlsx`
- `.agents/*.log`
- `__pycache__/`
- `.pytest_cache/`
- `venv/`
- `frontend/node_modules/`
