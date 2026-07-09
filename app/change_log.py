from datetime import date, datetime, time


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS change_log_entries (
    id SERIAL PRIMARY KEY,
    station_pair TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'both',
    change_date DATE NOT NULL,
    change_time TIME,
    category TEXT NOT NULL DEFAULT 'Other',
    label TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_change_log_station_date ON change_log_entries(station_pair, change_date);
ALTER TABLE change_log_entries ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'Other';
ALTER TABLE change_log_entries ADD COLUMN IF NOT EXISTS change_time TIME;
"""

VALID_SIDES = {"left", "right", "both"}
VALID_CATEGORIES = {"Lots", "Burger", "Chamfer", "RPMs", "Infeed Advance", "Outfeed Advance", "Other"}
DESCRIPTION_MIN_LENGTH = 20
EMPLOYEE_NUMBER_MAX_LENGTH = 10
EMPLOYEE_NAME_MAX_LENGTH = 50


def ensure_schema(db):
    with db.cursor() as cursor:
        cursor.execute(SCHEMA_SQL)


def normalize_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def normalize_row(row):
    return {key: normalize_value(value) for key, value in dict(row).items()}


def get_employees(db):
    rows = db.fetch("SELECT * FROM employees ORDER BY full_name ASC, employee_number ASC")
    return [normalize_row(row) for row in rows]


def create_employee(db, employee_number, full_name):
    employee_number = str(employee_number or "").strip()
    full_name = str(full_name or "").strip()
    if len(employee_number) > EMPLOYEE_NUMBER_MAX_LENGTH:
        raise ValueError(f"employee_number must be at most {EMPLOYEE_NUMBER_MAX_LENGTH} characters")
    if not full_name:
        raise ValueError("full_name is required")
    if len(full_name) > EMPLOYEE_NAME_MAX_LENGTH:
        raise ValueError(f"full_name must be at most {EMPLOYEE_NAME_MAX_LENGTH} characters")
    employee_number = employee_number or None

    row = db.fetch_one(
        """
        INSERT INTO employees (employee_number, full_name)
        VALUES (%s, %s)
        ON CONFLICT (employee_number) DO NOTHING
        RETURNING *
        """,
        [employee_number, full_name],
    )
    if not row:
        raise ValueError("employee_number already exists")
    return normalize_row(row)


def update_employee(db, employee_id, employee_number=None, full_name=None):
    fields = []
    params = []
    if employee_number is not None:
        employee_number = str(employee_number or "").strip()
        if len(employee_number) > EMPLOYEE_NUMBER_MAX_LENGTH:
            raise ValueError(f"employee_number must be at most {EMPLOYEE_NUMBER_MAX_LENGTH} characters")
        if employee_number:
            existing = db.fetch_one(
                "SELECT id FROM employees WHERE employee_number = %s AND id <> %s",
                [employee_number, employee_id],
            )
            if existing:
                raise ValueError("employee_number already exists")
        fields.append("employee_number = %s")
        params.append(employee_number or None)
    if full_name is not None:
        full_name = str(full_name or "").strip()
        if not full_name:
            raise ValueError("full_name cannot be empty")
        if len(full_name) > EMPLOYEE_NAME_MAX_LENGTH:
            raise ValueError(f"full_name must be at most {EMPLOYEE_NAME_MAX_LENGTH} characters")
        fields.append("full_name = %s")
        params.append(full_name)
    if not fields:
        raise ValueError("nothing to update")

    params.append(employee_id)
    row = db.fetch_one(
        f"""
        UPDATE employees
        SET {', '.join(fields)}
        WHERE id = %s
        RETURNING *
        """,
        params,
    )
    if not row:
        raise ValueError("employee not found")
    return normalize_row(row)


def delete_employee(db, employee_id):
    row = db.fetch_one("DELETE FROM employees WHERE id = %s RETURNING id", [employee_id])
    if not row:
        raise ValueError("employee not found")


def get_entries(db):
    rows = db.fetch(
        """
        SELECT
            change_log_entries.*,
            employees.employee_number,
            employees.full_name AS employee_name
        FROM change_log_entries
        LEFT JOIN employees ON employees.id = change_log_entries.employee_id
        ORDER BY change_log_entries.change_date DESC, change_log_entries.created_at DESC
        """
    )
    return [normalize_row(row) for row in rows]


def _resolve_label(category, label):
    category = str(category or "Other").strip()
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
    if category == "Other":
        label = str(label or "").strip()
        if not label:
            raise ValueError("label is required when category is Other")
        return category, label
    return category, category


def _resolve_description(description, required=False):
    if description is None:
        if required:
            raise ValueError("description is required")
        return None
    cleaned = str(description).strip()
    if not cleaned:
        raise ValueError("description is required")
    if len(cleaned) < DESCRIPTION_MIN_LENGTH:
        raise ValueError(f"description must be at least {DESCRIPTION_MIN_LENGTH} characters")
    return cleaned


def _resolve_employee_id(db, employee_id, required=False):
    if employee_id is None:
        if required:
            raise ValueError("employee_id is required")
        return None
    try:
        resolved_id = int(employee_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("employee_id must be an integer") from exc
    employee = db.fetch_one("SELECT id FROM employees WHERE id = %s", [resolved_id])
    if not employee:
        raise ValueError("employee not found")
    return resolved_id


def create_entry(db, station_pair, change_date, category="Other", label=None, side="both", description=None, change_time=None, employee_id=None):
    station_pair = str(station_pair or "").strip()
    if not station_pair:
        raise ValueError("station_pair is required")
    category, label = _resolve_label(category, label)
    side = str(side or "both").strip().lower()
    if side not in VALID_SIDES:
        raise ValueError(f"side must be one of {sorted(VALID_SIDES)}")
    description = _resolve_description(description, required=True)
    employee_id = _resolve_employee_id(db, employee_id, required=True)

    row = db.fetch_one(
        """
        INSERT INTO change_log_entries (station_pair, side, change_date, change_time, employee_id, category, label, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [station_pair, side, change_date, change_time, employee_id, category, label, description],
    )
    return normalize_row(row)


UNSET = object()


def update_entry(db, entry_id, station_pair=None, change_date=None, change_time=UNSET, category=None, label=None, side=None, description=UNSET, employee_id=UNSET):
    fields = []
    params = []
    if station_pair is not None:
        cleaned = str(station_pair).strip()
        if not cleaned:
            raise ValueError("station_pair cannot be empty")
        fields.append("station_pair = %s")
        params.append(cleaned)
    if change_date is not None:
        fields.append("change_date = %s")
        params.append(change_date)
    if change_time is not UNSET:
        fields.append("change_time = %s")
        params.append(change_time)
    if employee_id is not UNSET:
        fields.append("employee_id = %s")
        params.append(_resolve_employee_id(db, employee_id, required=False))
    if category is not None or label is not None:
        existing = db.fetch_one("SELECT category, label FROM change_log_entries WHERE id = %s", [entry_id])
        if not existing:
            raise ValueError("entry not found")
        resolved_category, resolved_label = _resolve_label(
            category if category is not None else existing["category"],
            label if label is not None else existing["label"],
        )
        fields.append("category = %s")
        params.append(resolved_category)
        fields.append("label = %s")
        params.append(resolved_label)
    if side is not None:
        cleaned_side = str(side).strip().lower()
        if cleaned_side not in VALID_SIDES:
            raise ValueError(f"side must be one of {sorted(VALID_SIDES)}")
        fields.append("side = %s")
        params.append(cleaned_side)
    if description is not UNSET:
        description = _resolve_description(description, required=True)
        fields.append("description = %s")
        params.append(description)
    if not fields:
        raise ValueError("nothing to update")
    params.append(entry_id)
    row = db.fetch_one(
        f"UPDATE change_log_entries SET {', '.join(fields)} WHERE id = %s RETURNING *",
        params,
    )
    if not row:
        raise ValueError("entry not found")
    return normalize_row(row)


def delete_entry(db, entry_id):
    row = db.fetch_one("DELETE FROM change_log_entries WHERE id = %s RETURNING id", [entry_id])
    if not row:
        raise ValueError("entry not found")
