from io import BytesIO

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import reports
from app.db import close_db, get_db
from scripts.generate_excel_report import ReportParams, build_workbook, default_period


app = FastAPI(
    title="Vision Administration API",
    description="Local read-only API for model_results_central reports.",
    version="0.1.0",
)


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
    )
    workbook = build_workbook(report_params, data)
    return _workbook_response(workbook)
