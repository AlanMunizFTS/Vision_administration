from datetime import date, datetime, time


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS public.scrap_entries (
    id SERIAL PRIMARY KEY,
    station_pair TEXT NOT NULL,
    scrap_date DATE NOT NULL,
    scrap_time TIME NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT chk_scrap_entries_whole_hour
        CHECK (
            date_part('minute', scrap_time) = 0
            AND date_part('second', scrap_time) = 0
        )
);

CREATE INDEX IF NOT EXISTS idx_scrap_entries_station_date
ON public.scrap_entries(station_pair, scrap_date);
"""

UNSET = object()


def ensure_schema(db):
    with db.cursor() as cursor:
        cursor.execute(SCHEMA_SQL)


def normalize_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def normalize_row(row):
    return {key: normalize_value(value) for key, value in dict(row).items()}


def get_entries(db):
    rows = db.fetch(
        """
        SELECT *
        FROM public.scrap_entries
        ORDER BY scrap_date DESC, scrap_time DESC, created_at DESC
        """
    )
    return [normalize_row(row) for row in rows]


def _clean_station_pair(station_pair, field_name="station_pair"):
    cleaned = str(station_pair or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _clean_whole_hour(scrap_time):
    if scrap_time is None:
        raise ValueError("scrap_time is required")
    if scrap_time.minute != 0 or scrap_time.second != 0 or scrap_time.microsecond != 0:
        raise ValueError("scrap_time must be a whole hour")
    return scrap_time


def _clean_quantity(quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValueError("quantity must be an integer")
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")
    return quantity


def create_entry(db, station_pair, scrap_date, scrap_time, quantity):
    station_pair = _clean_station_pair(station_pair)
    scrap_time = _clean_whole_hour(scrap_time)
    quantity = _clean_quantity(quantity)

    row = db.fetch_one(
        """
        INSERT INTO public.scrap_entries (station_pair, scrap_date, scrap_time, quantity)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        [station_pair, scrap_date, scrap_time, quantity],
    )
    return normalize_row(row)


def update_entry(db, entry_id, station_pair=None, scrap_date=None, scrap_time=UNSET, quantity=None):
    fields = []
    params = []
    if station_pair is not None:
        fields.append("station_pair = %s")
        params.append(_clean_station_pair(station_pair, "station_pair"))
    if scrap_date is not None:
        fields.append("scrap_date = %s")
        params.append(scrap_date)
    if scrap_time is not UNSET:
        fields.append("scrap_time = %s")
        params.append(_clean_whole_hour(scrap_time))
    if quantity is not None:
        fields.append("quantity = %s")
        params.append(_clean_quantity(quantity))
    if not fields:
        raise ValueError("nothing to update")

    params.append(entry_id)
    row = db.fetch_one(
        f"""
        UPDATE public.scrap_entries
        SET {', '.join(fields)}
        WHERE id = %s
        RETURNING *
        """,
        params,
    )
    if not row:
        raise ValueError("scrap entry not found")
    return normalize_row(row)


def delete_entry(db, entry_id):
    row = db.fetch_one("DELETE FROM public.scrap_entries WHERE id = %s RETURNING id", [entry_id])
    if not row:
        raise ValueError("scrap entry not found")
