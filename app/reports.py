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


def defect_name_expr(column_name):
    return f"COALESCE(NULLIF(UPPER(TRIM({column_name})), ''), 'UNCLASSIFIED')"


def station_pair_expr(column_name="source_station"):
    return f"regexp_replace({column_name}, '_(LEFT|RIGHT)$', '', 'i')"


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


def build_piece_filters(start_at=None, end_at=None, source_station=None, source_id=None):
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

    where_sql = ""
    if filters:
        where_sql = "WHERE " + " AND ".join(f"({item})" for item in filters)
    return where_sql, params


def build_combined_piece_filters(start_at=None, end_at=None, source_station=None, source_id=None):
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
        filters.append("(%s = ANY(source_stations) OR station_pair = %s)")
        params.extend([source_station, source_station])
    if source_id is not None:
        filters.append("%s = ANY(source_ids)")
        params.append(source_id)

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


def combined_piece_cte():
    return f"""
{piece_cte()},
combined_ranked_defects AS (
    SELECT
        {station_pair_expr("source_station")} AS station_pair,
        jsn,
        main_defect,
        main_confidence,
        ROW_NUMBER() OVER (
            PARTITION BY {station_pair_expr("source_station")}, jsn
            ORDER BY main_confidence DESC NULLS LAST, created_at_last DESC NULLS LAST, source_station DESC NULLS LAST
        ) AS defect_rank
    FROM pieces
    WHERE model_result = 'NOK'
),
combined_base AS (
    SELECT
        {station_pair_expr("pieces.source_station")} AS station_pair,
        pieces.jsn,
        CASE
            WHEN COUNT(*) FILTER (WHERE pieces.model_result = 'NOK') > 0 THEN 'NOK'
            ELSE 'OK'
        END AS model_result,
        MIN(pieces.captured_at) AS captured_at,
        MIN(pieces.created_at_first) AS created_at_first,
        MAX(pieces.created_at_last) AS created_at_last,
        ARRAY_REMOVE(ARRAY_AGG(DISTINCT pieces.source_station ORDER BY pieces.source_station), NULL) AS source_stations,
        SUM(pieces.image_count) AS image_count,
        SUM(pieces.detections_count) AS detections_count,
        selected.main_defect,
        selected.main_confidence
    FROM pieces
    LEFT JOIN combined_ranked_defects selected
      ON selected.station_pair IS NOT DISTINCT FROM {station_pair_expr("pieces.source_station")}
     AND selected.jsn = pieces.jsn
     AND selected.defect_rank = 1
    GROUP BY {station_pair_expr("pieces.source_station")}, pieces.jsn, selected.main_defect, selected.main_confidence
),
combined_pieces AS (
    SELECT
        combined_base.*,
        ARRAY(
            SELECT DISTINCT source_id
            FROM pieces source_piece
            CROSS JOIN LATERAL unnest(source_piece.source_ids) AS source_id
            WHERE {station_pair_expr("source_piece.source_station")} IS NOT DISTINCT FROM combined_base.station_pair
              AND source_piece.jsn = combined_base.jsn
            ORDER BY source_id
        ) AS source_ids
    FROM combined_base
)
"""


def get_health(db):
    row = db.fetch_one("SELECT 1 AS ok")
    return {"api": "ok", "database": "ok" if row and row.get("ok") == 1 else "error"}


def get_options(db):
    query = f"""
    SELECT
        ARRAY_REMOVE(ARRAY_AGG(DISTINCT source_station ORDER BY source_station), NULL) AS source_stations,
        ARRAY_REMOVE(ARRAY_AGG(DISTINCT {station_pair_expr()} ORDER BY {station_pair_expr()}), NULL) AS station_pairs,
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
    limit=100,
    offset=0,
):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
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


def get_summary(db, start_at=None, end_at=None, source_station=None, source_id=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
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


def get_station_summary(db, start_at=None, end_at=None, source_id=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_id=source_id,
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


def get_defects(db, start_at=None, end_at=None, source_station=None, source_id=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
    )
    query = f"""
    {piece_cte()}
    SELECT
        {defect_name_expr("main_defect")} AS class_name,
        COUNT(*) AS piece_count,
        MAX(main_confidence) AS max_confidence,
        AVG(main_confidence) AS avg_confidence
    FROM pieces
    {where_sql}
    {"AND" if where_sql else "WHERE"} model_result = 'NOK'
    GROUP BY {defect_name_expr("main_defect")}
    ORDER BY class_name ASC
    """
    return {"items": [normalize_row(row) for row in db.fetch(query, params)]}


def get_station_defects(db, start_at=None, end_at=None, source_id=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_id=source_id,
    )
    query = f"""
    {piece_cte()}
    SELECT
        source_station,
        {defect_name_expr("main_defect")} AS class_name,
        COUNT(*) AS piece_count,
        MAX(main_confidence) AS max_confidence,
        AVG(main_confidence) AS avg_confidence
    FROM pieces
    {where_sql}
    {"AND" if where_sql else "WHERE"} model_result = 'NOK'
    GROUP BY source_station, {defect_name_expr("main_defect")}
    ORDER BY source_station ASC NULLS LAST, class_name ASC
    """
    return {"items": [normalize_row(row) for row in db.fetch(query, params)]}


def get_timeseries(
    db,
    start_at=None,
    end_at=None,
    source_station=None,
    source_id=None,
    bucket="hour",
):
    if bucket not in {"hour", "day"}:
        raise ValueError("bucket must be 'hour' or 'day'")

    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
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
    bucket="hour",
):
    if bucket not in {"hour", "day"}:
        raise ValueError("bucket must be 'hour' or 'day'")

    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_id=source_id,
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


def get_reject_summary(db, start_at=None, end_at=None, source_station=None, source_id=None):
    where_sql, params = build_piece_filters(
        start_at=start_at,
        end_at=end_at,
        source_station=source_station,
        source_id=source_id,
    )
    query = f"""
    {piece_cte()},
    filtered_pieces AS (
        SELECT
            source_station,
            jsn,
            model_result,
            captured_at,
            created_at_last,
            main_confidence,
            {defect_name_expr("main_defect")} AS condition_name
        FROM pieces
        {where_sql}
    ),
    station_rows AS (
        SELECT
            source_station,
            COUNT(*) AS total_pieces,
            COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
            COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
        FROM filtered_pieces
        GROUP BY source_station
    ),
    daily_rows AS (
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
    ),
    day_bounds AS (
        SELECT
            source_station,
            date_trunc('day', captured_at)::date AS reject_date,
            MIN(captured_at) AS period_start,
            MAX(captured_at) AS period_end
        FROM filtered_pieces
        WHERE captured_at IS NOT NULL
        GROUP BY source_station, date_trunc('day', captured_at)::date
    ),
    condition_period_rows AS (
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
    ),
    condition_total_rows AS (
        SELECT
            source_station,
            condition_name AS class_name,
            COUNT(*) AS nok_pieces
        FROM filtered_pieces
        WHERE model_result = 'NOK'
        GROUP BY source_station, condition_name
    ),
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
    ),
    top3_history_rows AS (
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
    ),
    combined_ranked_defects AS (
        SELECT
            {station_pair_expr("source_station")} AS station_pair,
            jsn,
            condition_name,
            main_confidence,
            ROW_NUMBER() OVER (
                PARTITION BY {station_pair_expr("source_station")}, jsn
                ORDER BY main_confidence DESC NULLS LAST, created_at_last DESC NULLS LAST, source_station DESC NULLS LAST
            ) AS defect_rank
        FROM filtered_pieces
        WHERE model_result = 'NOK'
    ),
    combined_pieces AS (
        SELECT
            {station_pair_expr("filtered_pieces.source_station")} AS station_pair,
            filtered_pieces.jsn,
            CASE
                WHEN COUNT(*) FILTER (WHERE filtered_pieces.model_result = 'NOK') > 0 THEN 'NOK'
                ELSE 'OK'
            END AS model_result,
            MIN(filtered_pieces.captured_at) AS captured_at,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT filtered_pieces.source_station ORDER BY filtered_pieces.source_station), NULL) AS source_stations,
            selected.condition_name
        FROM filtered_pieces
        LEFT JOIN combined_ranked_defects selected
          ON selected.station_pair IS NOT DISTINCT FROM {station_pair_expr("filtered_pieces.source_station")}
         AND selected.jsn = filtered_pieces.jsn
         AND selected.defect_rank = 1
        GROUP BY {station_pair_expr("filtered_pieces.source_station")}, filtered_pieces.jsn, selected.condition_name
    ),
    station_sides AS (
        SELECT
            station_pair,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT side_station ORDER BY side_station), NULL) AS source_stations
        FROM combined_pieces
        LEFT JOIN LATERAL unnest(source_stations) AS side_station ON true
        GROUP BY station_pair
    ),
    combined_station_rows AS (
        SELECT
            combined_pieces.station_pair,
            station_sides.source_stations,
            COUNT(*) AS total_pieces,
            COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
            COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
        FROM combined_pieces
        LEFT JOIN station_sides
          ON station_sides.station_pair IS NOT DISTINCT FROM combined_pieces.station_pair
        GROUP BY combined_pieces.station_pair, station_sides.source_stations
    ),
    combined_daily_rows AS (
        SELECT
            station_pair,
            date_trunc('day', captured_at)::date AS reject_date,
            COUNT(*) AS total_pieces,
            COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
            COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'OK')::float / COUNT(*) END AS pct_ok,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE COUNT(*) FILTER (WHERE model_result = 'NOK')::float / COUNT(*) END AS pct_nok
        FROM combined_pieces
        WHERE captured_at IS NOT NULL
        GROUP BY station_pair, date_trunc('day', captured_at)::date
    ),
    combined_day_bounds AS (
        SELECT
            station_pair,
            date_trunc('day', captured_at)::date AS reject_date,
            MIN(captured_at) AS period_start,
            MAX(captured_at) AS period_end
        FROM combined_pieces
        WHERE captured_at IS NOT NULL
        GROUP BY station_pair, date_trunc('day', captured_at)::date
    ),
    combined_condition_period_rows AS (
        SELECT
            combined_pieces.station_pair,
            date_trunc('day', combined_pieces.captured_at)::date AS reject_date,
            combined_day_bounds.period_start,
            combined_day_bounds.period_end,
            CASE WHEN model_result = 'OK' THEN 'OK' ELSE condition_name END AS class_name,
            COUNT(*) FILTER (WHERE model_result = 'OK') AS ok_pieces,
            COUNT(*) FILTER (WHERE model_result = 'NOK') AS nok_pieces,
            COUNT(*) AS total_pieces
        FROM combined_pieces
        INNER JOIN combined_day_bounds
          ON combined_day_bounds.station_pair IS NOT DISTINCT FROM combined_pieces.station_pair
         AND combined_day_bounds.reject_date = date_trunc('day', combined_pieces.captured_at)::date
        WHERE combined_pieces.captured_at IS NOT NULL
        GROUP BY
            combined_pieces.station_pair,
            date_trunc('day', combined_pieces.captured_at)::date,
            combined_day_bounds.period_start,
            combined_day_bounds.period_end,
            CASE WHEN model_result = 'OK' THEN 'OK' ELSE condition_name END
    ),
    combined_condition_total_rows AS (
        SELECT
            station_pair,
            condition_name AS class_name,
            COUNT(*) AS nok_pieces
        FROM combined_pieces
        WHERE model_result = 'NOK'
        GROUP BY station_pair, condition_name
    ),
    combined_ranked_classes AS (
        SELECT
            station_pair,
            condition_name AS class_name,
            COUNT(*) AS nok_pieces,
            ROW_NUMBER() OVER (
                PARTITION BY station_pair
                ORDER BY COUNT(*) DESC, condition_name ASC
            ) AS class_rank
        FROM combined_pieces
        WHERE model_result = 'NOK'
        GROUP BY station_pair, condition_name
    ),
    combined_top3_history_rows AS (
        SELECT
            combined_pieces.station_pair,
            combined_ranked_classes.class_name,
            combined_ranked_classes.nok_pieces AS total_nok_pieces,
            combined_ranked_classes.class_rank,
            date_trunc('day', combined_pieces.captured_at)::date AS reject_date,
            COUNT(*) AS nok_pieces
        FROM combined_pieces
        INNER JOIN combined_ranked_classes
          ON combined_ranked_classes.station_pair IS NOT DISTINCT FROM combined_pieces.station_pair
         AND combined_ranked_classes.class_name = combined_pieces.condition_name
         AND combined_ranked_classes.class_rank <= 3
        WHERE combined_pieces.model_result = 'NOK'
          AND combined_pieces.captured_at IS NOT NULL
        GROUP BY
            combined_pieces.station_pair,
            combined_ranked_classes.class_name,
            combined_ranked_classes.nok_pieces,
            combined_ranked_classes.class_rank,
            date_trunc('day', combined_pieces.captured_at)::date
    )
    SELECT
        COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM station_rows ORDER BY source_station ASC NULLS LAST) row_data), '[]'::json) AS stations,
        COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM daily_rows ORDER BY reject_date ASC, source_station ASC NULLS LAST) row_data), '[]'::json) AS daily,
        COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM condition_period_rows ORDER BY reject_date ASC, source_station ASC NULLS LAST, class_name ASC) row_data), '[]'::json) AS condition_periods,
        COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM condition_total_rows ORDER BY source_station ASC NULLS LAST, class_name ASC) row_data), '[]'::json) AS condition_totals,
        COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM top3_history_rows ORDER BY source_station ASC NULLS LAST, class_rank ASC, reject_date ASC) row_data), '[]'::json) AS top3_history,
        json_build_object(
            'stations', COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM combined_station_rows ORDER BY station_pair ASC NULLS LAST) row_data), '[]'::json),
            'daily', COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM combined_daily_rows ORDER BY reject_date ASC, station_pair ASC NULLS LAST) row_data), '[]'::json),
            'condition_periods', COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM combined_condition_period_rows ORDER BY reject_date ASC, station_pair ASC NULLS LAST, class_name ASC) row_data), '[]'::json),
            'condition_totals', COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM combined_condition_total_rows ORDER BY station_pair ASC NULLS LAST, class_name ASC) row_data), '[]'::json),
            'top3_history', COALESCE((SELECT json_agg(row_to_json(row_data)) FROM (SELECT * FROM combined_top3_history_rows ORDER BY station_pair ASC NULLS LAST, class_rank ASC, reject_date ASC) row_data), '[]'::json)
        ) AS combined
    """
    row = normalize_row(db.fetch_one(query, params) or {})
    return {
        "stations": row.get("stations") or [],
        "daily": row.get("daily") or [],
        "condition_periods": row.get("condition_periods") or [],
        "condition_totals": row.get("condition_totals") or [],
        "top3_history": row.get("top3_history") or [],
        "combined": row.get("combined") or {
            "stations": [],
            "daily": [],
            "condition_periods": [],
            "condition_totals": [],
            "top3_history": [],
        },
    }
