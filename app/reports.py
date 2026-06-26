from datetime import datetime
from decimal import Decimal


RESULTS_TABLE = "public.model_results_central"


CAPTURED_AT_EXPR = """
CASE
    WHEN substring(jsn from 6 for 12) ~ '^(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{2}([01][0-9]|2[0-3])[0-5][0-9][0-5][0-9]$'
    THEN
        CASE
            WHEN to_char(to_timestamp(substring(jsn from 6 for 12), 'MMDDYYHH24MISS'), 'MMDDYYHH24MISS') = substring(jsn from 6 for 12)
            THEN to_timestamp(substring(jsn from 6 for 12), 'MMDDYYHH24MISS')::timestamp
            ELSE NULL
        END
    ELSE NULL
END
"""


def normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


def normalize_row(row):
    return {key: normalize_value(value) for key, value in dict(row).items()}


def parse_datetime_param(value, name):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO datetime format") from exc


def build_base_filters(
    start_at=None,
    end_at=None,
    source_station=None,
    source_id=None,
    jsn=None,
    class_name=None,
    min_confidence=None,
):
    filters = []
    params = []

    parsed_start = parse_datetime_param(start_at, "start_at")
    parsed_end = parse_datetime_param(end_at, "end_at")

    if parsed_start is not None:
        filters.append(f"{CAPTURED_AT_EXPR} >= %s")
        params.append(parsed_start)
    if parsed_end is not None:
        filters.append(f"{CAPTURED_AT_EXPR} <= %s")
        params.append(parsed_end)
    if source_station:
        filters.append("source_station = %s")
        params.append(source_station)
    if source_id is not None:
        filters.append("source_id = %s")
        params.append(source_id)
    if jsn:
        filters.append("jsn = %s")
        params.append(jsn)
    if class_name:
        filters.append("class_name = %s")
        params.append(class_name)
    if min_confidence is not None:
        filters.append("confidence >= %s")
        params.append(min_confidence)

    where_sql = ""
    if filters:
        where_sql = "WHERE " + " AND ".join(f"({item})" for item in filters)
    return where_sql, params


def build_piece_filters(start_at=None, end_at=None, source_station=None, source_id=None, jsn=None):
    filters = []
    params = []

    parsed_start = parse_datetime_param(start_at, "start_at")
    parsed_end = parse_datetime_param(end_at, "end_at")

    if parsed_start is not None:
        filters.append("captured_at >= %s")
        params.append(parsed_start)
    if parsed_end is not None:
        filters.append("captured_at <= %s")
        params.append(parsed_end)
    if source_station:
        filters.append("source_station = %s")
        params.append(source_station)
    if source_id is not None:
        filters.append("%s = ANY(source_ids)")
        params.append(source_id)
    if jsn:
        filters.append("jsn = %s")
        params.append(jsn)

    where_sql = ""
    if filters:
        where_sql = "WHERE " + " AND ".join(f"({item})" for item in filters)
    return where_sql, params


def piece_cte():
    return f"""
WITH raw AS (
    SELECT
        central_id,
        source_station,
        source_id,
        img_name,
        jsn,
        class_name,
        confidence,
        created_at,
        {CAPTURED_AT_EXPR} AS captured_at
    FROM {RESULTS_TABLE}
),
ranked_defects AS (
    SELECT
        source_station,
        jsn,
        class_name,
        confidence,
        ROW_NUMBER() OVER (
            PARTITION BY source_station, jsn
            ORDER BY confidence DESC, created_at DESC NULLS LAST, central_id DESC
        ) AS defect_rank
    FROM raw
    WHERE UPPER(class_name) <> 'OK'
),
pieces AS (
    SELECT
        raw.source_station,
        raw.jsn,
        CASE
            WHEN COUNT(*) FILTER (WHERE UPPER(raw.class_name) <> 'OK') > 0 THEN 'NOK'
            ELSE 'OK'
        END AS model_result,
        MIN(raw.captured_at) AS captured_at,
        MIN(raw.created_at) AS created_at_first,
        MAX(raw.created_at) AS created_at_last,
        ARRAY_AGG(DISTINCT raw.source_id ORDER BY raw.source_id) AS source_ids,
        COUNT(DISTINCT raw.img_name) AS image_count,
        COUNT(*) AS detections_count,
        selected.class_name AS main_defect,
        selected.confidence AS main_confidence
    FROM raw
    LEFT JOIN ranked_defects selected
      ON selected.source_station IS NOT DISTINCT FROM raw.source_station
     AND selected.jsn = raw.jsn
     AND selected.defect_rank = 1
    GROUP BY raw.source_station, raw.jsn, selected.class_name, selected.confidence
)
"""


def get_health(db):
    row = db.fetch_one("SELECT 1 AS ok")
    return {"api": "ok", "database": "ok" if row and row.get("ok") == 1 else "error"}


def get_options(db):
    query = f"""
    SELECT
        ARRAY_REMOVE(ARRAY_AGG(DISTINCT source_station ORDER BY source_station), NULL) AS source_stations,
        ARRAY_REMOVE(ARRAY_AGG(DISTINCT class_name ORDER BY class_name), NULL) AS class_names,
        MIN({CAPTURED_AT_EXPR}) AS min_captured_at,
        MAX({CAPTURED_AT_EXPR}) AS max_captured_at,
        MIN(created_at) AS min_created_at,
        MAX(created_at) AS max_created_at
    FROM {RESULTS_TABLE}
    """
    return normalize_row(db.fetch_one(query) or {})


def get_results(
    db,
    start_at=None,
    end_at=None,
    source_station=None,
    source_id=None,
    jsn=None,
    class_name=None,
    min_confidence=None,
    limit=100,
    offset=0,
):
    where_sql, params = build_base_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
        jsn=jsn,
        class_name=class_name,
        min_confidence=min_confidence,
    )
    query = f"""
    SELECT
        central_id,
        source_station,
        source_id,
        img_name,
        jsn,
        class_name,
        confidence,
        created_at,
        {CAPTURED_AT_EXPR} AS captured_at
    FROM {RESULTS_TABLE}
    {where_sql}
    ORDER BY captured_at DESC NULLS LAST, created_at DESC NULLS LAST, central_id DESC
    LIMIT %s OFFSET %s
    """
    rows = db.fetch(query, [*params, limit, offset])
    return {"items": [normalize_row(row) for row in rows], "limit": limit, "offset": offset}


def get_pieces(
    db,
    start_at=None,
    end_at=None,
    source_station=None,
    source_id=None,
    jsn=None,
    limit=100,
    offset=0,
):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT *
    FROM pieces
    {where_sql}
    ORDER BY captured_at DESC NULLS LAST, created_at_last DESC NULLS LAST, jsn DESC
    LIMIT %s OFFSET %s
    """
    rows = db.fetch(query, [*params, limit, offset])
    return {"items": [normalize_row(row) for row in rows], "limit": limit, "offset": offset}


def get_summary(db, start_at=None, end_at=None, source_station=None, source_id=None, jsn=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT
        COUNT(*) AS total_pieces,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
    FROM pieces
    {where_sql}
    """
    return normalize_row(db.fetch_one(query, params) or {})


def get_station_summary(db, start_at=None, end_at=None, source_id=None, jsn=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT
        source_station,
        COUNT(*) AS total_pieces,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
    FROM pieces
    {where_sql}
    GROUP BY source_station
    ORDER BY source_station ASC NULLS LAST
    """
    return {"items": [normalize_row(row) for row in db.fetch(query, params)]}


def get_defects(db, start_at=None, end_at=None, source_station=None, source_id=None, jsn=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT
        COALESCE(main_defect, 'UNCLASSIFIED') AS class_name,
        COUNT(*) AS piece_count,
        MAX(main_confidence) AS max_confidence,
        AVG(main_confidence) AS avg_confidence
    FROM pieces
    {where_sql}
    {"AND" if where_sql else "WHERE"} model_result = 'NOK'
    GROUP BY COALESCE(main_defect, 'UNCLASSIFIED')
    ORDER BY piece_count DESC, class_name ASC
    """
    return {"items": [normalize_row(row) for row in db.fetch(query, params)]}


def get_station_defects(db, start_at=None, end_at=None, source_id=None, jsn=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT
        source_station,
        COALESCE(main_defect, 'UNCLASSIFIED') AS class_name,
        COUNT(*) AS piece_count,
        MAX(main_confidence) AS max_confidence,
        AVG(main_confidence) AS avg_confidence
    FROM pieces
    {where_sql}
    {"AND" if where_sql else "WHERE"} model_result = 'NOK'
    GROUP BY source_station, COALESCE(main_defect, 'UNCLASSIFIED')
    ORDER BY source_station ASC NULLS LAST, piece_count DESC, class_name ASC
    """
    return {"items": [normalize_row(row) for row in db.fetch(query, params)]}


def get_timeseries(
    db,
    start_at=None,
    end_at=None,
    source_station=None,
    source_id=None,
    jsn=None,
    bucket="hour",
):
    if bucket not in {"hour", "day"}:
        raise ValueError("bucket must be 'hour' or 'day'")

    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT
        date_trunc(%s, captured_at) AS bucket_start,
        COUNT(*) AS total_pieces,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces
    FROM pieces
    {where_sql}
    {"AND" if where_sql else "WHERE"} captured_at IS NOT NULL
    GROUP BY date_trunc(%s, captured_at)
    ORDER BY bucket_start ASC
    """
    rows = db.fetch(query, [bucket, *params, bucket])
    return {"bucket": bucket, "items": [normalize_row(row) for row in rows]}


def get_station_timeseries(
    db,
    start_at=None,
    end_at=None,
    source_id=None,
    jsn=None,
    bucket="hour",
):
    if bucket not in {"hour", "day"}:
        raise ValueError("bucket must be 'hour' or 'day'")

    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_id=source_id,
        jsn=jsn,
    )
    query = f"""
    {piece_cte()}
    SELECT
        source_station,
        date_trunc(%s, captured_at) AS bucket_start,
        COUNT(*) AS total_pieces,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces
    FROM pieces
    {where_sql}
    {"AND" if where_sql else "WHERE"} captured_at IS NOT NULL
    GROUP BY source_station, date_trunc(%s, captured_at)
    ORDER BY source_station ASC NULLS LAST, bucket_start ASC
    """
    rows = db.fetch(query, [bucket, *params, bucket])
    return {"bucket": bucket, "items": [normalize_row(row) for row in rows]}


def get_reject_summary(db, start_at=None, end_at=None, source_station=None, source_id=None, jsn=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
        jsn=jsn,
    )
    filtered_sql = f"""
    {piece_cte()},
    filtered_pieces AS (
        SELECT
            source_station,
            jsn,
            model_result,
            captured_at,
            COALESCE(main_defect, 'UNCLASSIFIED') AS condition_name
        FROM pieces
        {where_sql}
    )
    """

    stations_query = f"""
    {filtered_sql}
    SELECT
        source_station,
        COUNT(*) AS total_pieces,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
    FROM filtered_pieces
    GROUP BY source_station
    ORDER BY source_station ASC NULLS LAST
    """

    daily_query = f"""
    {filtered_sql}
    SELECT
        source_station,
        date_trunc('day', captured_at)::date AS reject_date,
        COUNT(*) AS total_pieces,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
        CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
    FROM filtered_pieces
    WHERE captured_at IS NOT NULL
    GROUP BY source_station, date_trunc('day', captured_at)::date
    ORDER BY reject_date ASC, source_station ASC NULLS LAST
    """

    condition_periods_query = f"""
    {filtered_sql},
    day_bounds AS (
        SELECT
            source_station,
            date_trunc('day', captured_at)::date AS reject_date,
            MIN(captured_at) AS period_start,
            MAX(captured_at) AS period_end
        FROM filtered_pieces
        WHERE captured_at IS NOT NULL
        GROUP BY source_station, date_trunc('day', captured_at)::date
    )
    SELECT
        filtered_pieces.source_station,
        date_trunc('day', filtered_pieces.captured_at)::date AS reject_date,
        day_bounds.period_start,
        day_bounds.period_end,
        CASE WHEN model_result = 'OK' THEN 'OK' ELSE condition_name END AS class_name,
        COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
        COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
        COUNT(*) AS total_pieces
    FROM filtered_pieces
    INNER JOIN day_bounds
      ON day_bounds.source_station IS NOT DISTINCT FROM filtered_pieces.source_station
     AND day_bounds.reject_date = date_trunc('day', filtered_pieces.captured_at)::date
    WHERE filtered_pieces.captured_at IS NOT NULL
    GROUP BY
        filtered_pieces.source_station,
        date_trunc('day', filtered_pieces.captured_at)::date,
        day_bounds.period_start,
        day_bounds.period_end,
        CASE WHEN model_result = 'OK' THEN 'OK' ELSE condition_name END
    ORDER BY reject_date ASC, source_station ASC NULLS LAST, nok_pieces DESC, class_name ASC
    """

    condition_totals_query = f"""
    {filtered_sql}
    SELECT
        source_station,
        condition_name AS class_name,
        COUNT(*) AS nok_pieces
    FROM filtered_pieces
    WHERE model_result = 'NOK'
    GROUP BY source_station, condition_name
    ORDER BY source_station ASC NULLS LAST, nok_pieces DESC, class_name ASC
    """

    top3_history_query = f"""
    {filtered_sql},
    ranked_classes AS (
        SELECT
            source_station,
            condition_name AS class_name,
            COUNT(*) AS nok_pieces,
            ROW_NUMBER() OVER (
                PARTITION BY source_station
                ORDER BY COUNT(*) DESC, condition_name ASC
            ) AS class_rank
        FROM filtered_pieces
        WHERE model_result = 'NOK'
        GROUP BY source_station, condition_name
    )
    SELECT
        filtered_pieces.source_station,
        ranked_classes.class_name,
        ranked_classes.nok_pieces AS total_nok_pieces,
        ranked_classes.class_rank,
        date_trunc('day', filtered_pieces.captured_at)::date AS reject_date,
        COUNT(*) AS nok_pieces
    FROM filtered_pieces
    INNER JOIN ranked_classes
      ON ranked_classes.source_station IS NOT DISTINCT FROM filtered_pieces.source_station
     AND ranked_classes.class_name = filtered_pieces.condition_name
     AND ranked_classes.class_rank <= 3
    WHERE filtered_pieces.model_result = 'NOK'
      AND filtered_pieces.captured_at IS NOT NULL
    GROUP BY
        filtered_pieces.source_station,
        ranked_classes.class_name,
        ranked_classes.nok_pieces,
        ranked_classes.class_rank,
        date_trunc('day', filtered_pieces.captured_at)::date
    ORDER BY filtered_pieces.source_station ASC NULLS LAST, ranked_classes.class_rank ASC, reject_date ASC
    """

    return {
        "stations": [normalize_row(row) for row in db.fetch(stations_query, params)],
        "daily": [normalize_row(row) for row in db.fetch(daily_query, params)],
        "condition_periods": [normalize_row(row) for row in db.fetch(condition_periods_query, params)],
        "condition_totals": [normalize_row(row) for row in db.fetch(condition_totals_query, params)],
        "top3_history": [normalize_row(row) for row in db.fetch(top3_history_query, params)],
    }
