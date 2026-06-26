from fastapi import Depends, FastAPI, HTTPException, Query

from app import reports
from app.db import close_db, get_db


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
