from io import BytesIO

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import reports
from app.db import close_db, get_db
from scripts.generate_excel_report import ReportParams, build_workbook


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
    jsn: str | None = None,
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
            jsn=jsn,
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
    jsn: str | None = None,
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
            jsn=jsn,
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
    jsn: str | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
            jsn=jsn,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/defects")
def defects(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    jsn: str | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_defects(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
            jsn=jsn,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/timeseries")
def timeseries(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    jsn: str | None = None,
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
            jsn=jsn,
            bucket=bucket,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/stations/summary")
def station_summary(
    start_at: str | None = None,
    end_at: str | None = None,
    source_id: int | None = None,
    jsn: str | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_station_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_id=source_id,
            jsn=jsn,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/stations/defects")
def station_defects(
    start_at: str | None = None,
    end_at: str | None = None,
    source_id: int | None = None,
    jsn: str | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_station_defects(
            db,
            start_at=start_at,
            end_at=end_at,
            source_id=source_id,
            jsn=jsn,
        )
    except ValueError as exc:
        handle_report_error(exc)


@app.get("/api/v1/stations/timeseries")
def station_timeseries(
    start_at: str | None = None,
    end_at: str | None = None,
    source_id: int | None = None,
    jsn: str | None = None,
    bucket: str = Query("hour", pattern="^(hour|day)$"),
    db=Depends(db_dependency),
):
    try:
        return reports.get_station_timeseries(
            db,
            start_at=start_at,
            end_at=end_at,
            source_id=source_id,
            jsn=jsn,
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
    jsn: str | None = None,
    db=Depends(db_dependency),
):
    try:
        return reports.get_reject_summary(
            db,
            start_at=start_at,
            end_at=end_at,
            source_station=source_station,
            source_id=source_id,
            jsn=jsn,
        )
    except ValueError as exc:
        handle_report_error(exc)


def _collect_excel_data(db, start_at, end_at, source_station, source_id, jsn):
    common = {
        "start_at": start_at,
        "end_at": end_at,
        "source_station": source_station,
        "source_id": source_id,
        "jsn": jsn,
    }
    data = {
        "summary": reports.get_summary(db, **common),
        "defects": reports.get_defects(db, **common),
        "timeseries_hour": reports.get_timeseries(db, **common, bucket="hour"),
        "timeseries_day": reports.get_timeseries(db, **common, bucket="day"),
        "station_reports": [],
    }

    options = reports.get_options(db)
    stations = options.get("source_stations") or []
    if source_station:
        stations = [source_station]

    for station in stations:
        station_common = {**common, "source_station": station}
        data["station_reports"].append(
            {
                "source_station": station,
                "summary": reports.get_summary(db, **station_common),
                "defects": reports.get_defects(db, **station_common),
                "timeseries_hour": reports.get_timeseries(db, **station_common, bucket="hour"),
                "timeseries_day": reports.get_timeseries(db, **station_common, bucket="day"),
                "pieces": reports.get_pieces(db, **station_common, limit=5000, offset=0),
            }
        )
    return data


@app.get("/api/v1/reports/excel")
def excel_report(
    start_at: str | None = None,
    end_at: str | None = None,
    source_station: str | None = None,
    source_id: int | None = None,
    jsn: str | None = None,
    db=Depends(db_dependency),
):
    try:
        report_params = ReportParams(
            api_url="local",
            start_at=start_at or "",
            end_at=end_at or "",
            source_station=source_station,
            source_id=source_id,
        )
        data = _collect_excel_data(db, start_at, end_at, source_station, source_id, jsn)
        workbook = build_workbook(report_params, data)
    except ValueError as exc:
        handle_report_error(exc)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vision_report.xlsx"'},
    )
