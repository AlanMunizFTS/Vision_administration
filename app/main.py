import os
from datetime import date, time
from io import BytesIO

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import change_log, glidepath, reports
from app.db import close_db, get_db
from app.migrator import run_migrations
from app.sync_runner import sync_runner
from scripts.generate_excel_report import ReportParams, build_workbook, default_period


app = FastAPI(
    title="Vision Administration API",
    description="Local API for model_results_central reports, glidepaths, and process change logs.",
    version="0.1.0",
)


def _run_migrations_on_startup():
    return os.getenv("RUN_MIGRATIONS", "true").strip().lower() not in {"0", "false", "no", "off"}


@app.on_event("startup")
def startup_event():
    if _run_migrations_on_startup():
        run_migrations()
    glidepath.ensure_schema(get_db())
    change_log.ensure_schema(get_db())


@app.on_event("shutdown")
def shutdown_event():
    close_db()


def db_dependency():
    try:
        return get_db()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection unavailable: {exc}",
        ) from exc


def handle_report_error(exc):
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@app.get("/health")
def health():
    try:
        db = get_db()
        return reports.get_health(db)
    except Exception as exc:
        return {"api": "ok", "database": "error", "detail": str(exc)}


@app.get("/api/v1/options")
def options(db=Depends(db_dependency)):
    return reports.get_options(db)


@app.post("/api/v1/sync-db")
def start_database_sync():
    return sync_runner.start()


@app.get("/api/v1/sync-db")
def database_sync_status():
    return sync_runner.status()


@app.get("/api/v1/results")
def results(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    class_name: str | None = None,
    min_confidence: float | None = None,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db=Depends(db_dependency),
):
    try:
        return reports.get_results(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
            class_name=class_name,
            min_confidence=min_confidence,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/pieces")
def pieces(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db=Depends(db_dependency),
):
    try:
        return reports.get_pieces(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/summary")
def summary(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/defects")
def defects(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_defects(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/timeseries")
def timeseries(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    bucket: str = Query("hour", pattern="^(hour|day)$"),
    db=Depends(db_dependency),
):
    try:
        return reports.get_timeseries(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
            bucket=bucket,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/stations/summary")
def station_summary(
    start_at: str | None = None,
    end_at: str | None = None,
    source_id: int | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_station_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_id=source_id,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/stations/defects")
def station_defects(
    start_at: str | None = None,
    end_at: str | None = None,
    source_id: int | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_station_defects(
            db,
            start_at=start_at,
            end_at=end_at,
            source_id=source_id,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/stations/timeseries")
def station_timeseries(
    start_at: str | None = None,
    end_at: str | None = None,
    source_id: int | None = None,
    bucket: str = Query("hour", pattern="^(hour|day)$"),
    db=Depends(db_dependency),
):
    try:
        return reports.get_station_timeseries(
            db,
            start_at=start_at,
            end_at=end_at,
            source_id=source_id,
            bucket=bucket,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/reject-summary")
def reject_summary(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_reject_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
        )
    except ValueError as exc:
        handle_report_error(exc)


def _excel_period(start_at, end_at):
    if start_at and end_at:
        return start_at, end_at
    if start_at or end_at:
        raise ValueError("start_at and end_at must be used together")

    default_start, default_end = default_period()
    return (
        default_start.isoformat(sep=" ", timespec="seconds"),
        default_end.isoformat(sep=" ", timespec="seconds"),
    )


def _workbook_response(workbook):
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vision_report.xlsx"'},
    )


def _source_station_filter_label(filters):
    station_pairs = filters.get("station_pairs")
    if isinstance(station_pairs, list):
        cleaned = [str(station).strip() for station in station_pairs if str(station or "").strip()]
        return ", ".join(cleaned) or None
    source_stations = filters.get("source_stations")
    if isinstance(source_stations, list):
        cleaned = [str(station).strip() for station in source_stations if str(station or "").strip()]
        return ", ".join(cleaned) or None
    return filters.get("source_station") or None


def _list_filter_values(filters, key):
    values = filters.get(key)
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _query_list_values(values):
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]


@app.get("/api/v1/reports/excel")
def excel_report(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    part_numbers: list[str] | None = Query(None),
    db=Depends(db_dependency),
):
    try:
        start_at, end_at = _excel_period(start_at, end_at)
        cleaned_part_numbers = _query_list_values(part_numbers)
        report_params = ReportParams(
            api_url="local",
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            part_numbers=cleaned_part_numbers or None,
        )
        data = reports.get_reject_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
        )
        workbook = build_workbook(report_params, data)
    except ValueError as exc:
        handle_report_error(exc)

    return _workbook_response(workbook)


@app.post("/api/v1/reports/excel")
def excel_report_from_summary(payload: dict = Body(...)):
    filters = payload.get("filters") or {}
    data = payload.get("data")
    if not isinstance(filters, dict) or not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Body must include filters and data objects")

    report_params = ReportParams(
        api_url="frontend",
        start_at=str(filters.get("start_at") or ""),
        end_at=str(filters.get("end_at") or ""),
        source_station=_source_station_filter_label(filters),
        part_numbers=_list_filter_values(filters, "part_numbers") or None,
        filter_part_numbers=False,
    )
    workbook = build_workbook(report_params, data)
    return _workbook_response(workbook)


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class SubprojectCreate(BaseModel):
    name: str
    station_pairs: list[str]
    start_date: date
    start_pct_nok: float
    status: str = "active"


class SubprojectUpdate(BaseModel):
    name: str | None = None
    station_pairs: list[str] | None = None
    start_date: date | None = None
    start_pct_nok: float | None = None
    status: str | None = None


class MilestoneCreate(BaseModel):
    target_date: date
    target_pct_nok: float
    label: str | None = None


class MilestoneUpdate(BaseModel):
    target_date: date | None = None
    target_pct_nok: float | None = None
    label: str | None = None


@app.get("/api/v1/glidepath/projects")
def glidepath_list_projects(db=Depends(db_dependency)):
    return {"items": glidepath.get_projects(db)}


@app.post("/api/v1/glidepath/projects")
def glidepath_create_project(payload: ProjectCreate, db=Depends(db_dependency)):
    try:
        return glidepath.create_project(db, name=payload.name, description=payload.description)
    except ValueError as exc:
        handle_report_error(exc)


@app.patch("/api/v1/glidepath/projects/{project_id}")
def glidepath_update_project(project_id: int, payload: ProjectUpdate, db=Depends(db_dependency)):
    try:
        return glidepath.update_project(db, project_id, name=payload.name, description=payload.description)
    except ValueError as exc:
        handle_report_error(exc)


@app.delete("/api/v1/glidepath/projects/{project_id}")
def glidepath_delete_project(project_id: int, db=Depends(db_dependency)):
    try:
        glidepath.delete_project(db, project_id)
        return {"deleted": True}
    except ValueError as exc:
        handle_report_error(exc)


@app.post("/api/v1/glidepath/projects/{project_id}/subprojects")
def glidepath_create_subproject(project_id: int, payload: SubprojectCreate, db=Depends(db_dependency)):
    try:
        return glidepath.create_subproject(
            db,
            project_id=project_id,
            name=payload.name,
            station_pairs=payload.station_pairs,
            start_date=payload.start_date,
            start_pct_nok=payload.start_pct_nok,
            status=payload.status,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.patch("/api/v1/glidepath/subprojects/{subproject_id}")
def glidepath_update_subproject(subproject_id: int, payload: SubprojectUpdate, db=Depends(db_dependency)):
    try:
        return glidepath.update_subproject(
            db,
            subproject_id,
            name=payload.name,
            station_pairs=payload.station_pairs,
            start_date=payload.start_date,
            start_pct_nok=payload.start_pct_nok,
            status=payload.status,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.delete("/api/v1/glidepath/subprojects/{subproject_id}")
def glidepath_delete_subproject(subproject_id: int, db=Depends(db_dependency)):
    try:
        glidepath.delete_subproject(db, subproject_id)
        return {"deleted": True}
    except ValueError as exc:
        handle_report_error(exc)


@app.post("/api/v1/glidepath/subprojects/{subproject_id}/milestones")
def glidepath_create_milestone(subproject_id: int, payload: MilestoneCreate, db=Depends(db_dependency)):
    try:
        return glidepath.create_milestone(
            db,
            subproject_id=subproject_id,
            target_date=payload.target_date,
            target_pct_nok=payload.target_pct_nok,
            label=payload.label,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.patch("/api/v1/glidepath/milestones/{milestone_id}")
def glidepath_update_milestone(milestone_id: int, payload: MilestoneUpdate, db=Depends(db_dependency)):
    try:
        return glidepath.update_milestone(
            db,
            milestone_id,
            target_date=payload.target_date,
            target_pct_nok=payload.target_pct_nok,
            label=payload.label,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.delete("/api/v1/glidepath/milestones/{milestone_id}")
def glidepath_delete_milestone(milestone_id: int, db=Depends(db_dependency)):
    try:
        glidepath.delete_milestone(db, milestone_id)
        return {"deleted": True}
    except ValueError as exc:
        handle_report_error(exc)


class ChangeLogEntryCreate(BaseModel):
    station_pair: str
    side: str = "both"
    change_date: date
    change_time: time | None = None
    employee_id: int
    category: str = "Other"
    label: str | None = None
    description: str | None = None


class ChangeLogEntryUpdate(BaseModel):
    station_pair: str | None = None
    side: str | None = None
    change_date: date | None = None
    change_time: time | None = None
    employee_id: int | None = None
    category: str | None = None
    label: str | None = None
    description: str | None = None


class EmployeeCreate(BaseModel):
    employee_number: str | None = None
    full_name: str


class EmployeeUpdate(BaseModel):
    employee_number: str | None = None
    full_name: str | None = None


@app.get("/api/v1/employees")
def employee_list(db=Depends(db_dependency)):
    return {"items": change_log.get_employees(db)}


@app.post("/api/v1/employees")
def employee_create(payload: EmployeeCreate, db=Depends(db_dependency)):
    try:
        return change_log.create_employee(
            db,
            employee_number=payload.employee_number,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.patch("/api/v1/employees/{employee_id}")
def employee_update(employee_id: int, payload: EmployeeUpdate, db=Depends(db_dependency)):
    try:
        return change_log.update_employee(
            db,
            employee_id,
            employee_number=payload.employee_number,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.delete("/api/v1/employees/{employee_id}")
def employee_delete(employee_id: int, db=Depends(db_dependency)):
    try:
        change_log.delete_employee(db, employee_id)
        return {"deleted": True}
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/change-log")
def change_log_list(db=Depends(db_dependency)):
    return {"items": change_log.get_entries(db)}


@app.post("/api/v1/change-log")
def change_log_create(payload: ChangeLogEntryCreate, db=Depends(db_dependency)):
    try:
        return change_log.create_entry(
            db,
            station_pair=payload.station_pair,
            change_date=payload.change_date,
            change_time=payload.change_time,
            employee_id=payload.employee_id,
            category=payload.category,
            label=payload.label,
            side=payload.side,
            description=payload.description,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.patch("/api/v1/change-log/{entry_id}")
def change_log_update(entry_id: int, payload: ChangeLogEntryUpdate, db=Depends(db_dependency)):
    try:
        fields = payload.model_dump(exclude_unset=True)
        return change_log.update_entry(
            db,
            entry_id,
            station_pair=payload.station_pair,
            change_date=payload.change_date,
            change_time=fields.get("change_time", change_log.UNSET),
            employee_id=fields.get("employee_id", change_log.UNSET),
            category=payload.category,
            label=payload.label,
            side=payload.side,
            description=fields.get("description", change_log.UNSET),
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.delete("/api/v1/change-log/{entry_id}")
def change_log_delete(entry_id: int, db=Depends(db_dependency)):
    try:
        change_log.delete_entry(db, entry_id)
        return {"deleted": True}
    except ValueError as exc:
        handle_report_error(exc)
