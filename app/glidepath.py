from datetime import date, datetime


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS glidepath_projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS glidepath_subprojects (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES glidepath_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    station_pairs TEXT[] NOT NULL DEFAULT '{}',
    start_date DATE NOT NULL,
    start_pct_nok DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS glidepath_milestones (
    id SERIAL PRIMARY KEY,
    subproject_id INTEGER NOT NULL REFERENCES glidepath_subprojects(id) ON DELETE CASCADE,
    target_date DATE NOT NULL,
    target_pct_nok DOUBLE PRECISION NOT NULL,
    label TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_glidepath_subprojects_project ON glidepath_subprojects(project_id);
CREATE INDEX IF NOT EXISTS idx_glidepath_milestones_subproject ON glidepath_milestones(subproject_id);
"""

VALID_STATUSES = {"active", "completed", "archived"}


def ensure_schema(db):
    with db.cursor() as cursor:
        cursor.execute(SCHEMA_SQL)


def normalize_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def normalize_row(row):
    return {key: normalize_value(value) for key, value in dict(row).items()}


def normalize_station_pairs(station_pairs):
    if not station_pairs:
        raise ValueError("station_pairs must include at least one station")
    cleaned = [str(item).strip() for item in station_pairs if str(item or "").strip()]
    if not cleaned:
        raise ValueError("station_pairs must include at least one station")
    return cleaned


def get_projects(db):
    projects = db.fetch("SELECT * FROM glidepath_projects ORDER BY created_at DESC")
    subprojects = db.fetch("SELECT * FROM glidepath_subprojects ORDER BY start_date ASC")
    milestones = db.fetch("SELECT * FROM glidepath_milestones ORDER BY target_date ASC")

    milestones_by_subproject = {}
    for milestone in milestones:
        milestones_by_subproject.setdefault(milestone["subproject_id"], []).append(normalize_row(milestone))

    subprojects_by_project = {}
    for subproject in subprojects:
        item = normalize_row(subproject)
        item["milestones"] = milestones_by_subproject.get(subproject["id"], [])
        subprojects_by_project.setdefault(subproject["project_id"], []).append(item)

    output = []
    for project in projects:
        item = normalize_row(project)
        item["subprojects"] = subprojects_by_project.get(project["id"], [])
        output.append(item)
    return output


def create_project(db, name, description=None):
    name = str(name or "").strip()
    if not name:
        raise ValueError("name is required")
    row = db.fetch_one(
        "INSERT INTO glidepath_projects (name, description) VALUES (%s, %s) RETURNING *",
        [name, description],
    )
    return normalize_row(row)


def update_project(db, project_id, name=None, description=None):
    fields = []
    params = []
    if name is not None:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        fields.append("name = %s")
        params.append(cleaned)
    if description is not None:
        fields.append("description = %s")
        params.append(description)
    if not fields:
        raise ValueError("nothing to update")
    params.append(project_id)
    row = db.fetch_one(
        f"UPDATE glidepath_projects SET {', '.join(fields)} WHERE id = %s RETURNING *",
        params,
    )
    if not row:
        raise ValueError("project not found")
    return normalize_row(row)


def delete_project(db, project_id):
    row = db.fetch_one("DELETE FROM glidepath_projects WHERE id = %s RETURNING id", [project_id])
    if not row:
        raise ValueError("project not found")


def create_subproject(db, project_id, name, station_pairs, start_date, start_pct_nok, status="active"):
    name = str(name or "").strip()
    if not name:
        raise ValueError("name is required")
    cleaned_pairs = normalize_station_pairs(station_pairs)
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
    if start_pct_nok is None or start_pct_nok < 0:
        raise ValueError("start_pct_nok must be a non-negative number")

    project = db.fetch_one("SELECT id FROM glidepath_projects WHERE id = %s", [project_id])
    if not project:
        raise ValueError("project not found")

    row = db.fetch_one(
        """
        INSERT INTO glidepath_subprojects (project_id, name, station_pairs, start_date, start_pct_nok, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [project_id, name, cleaned_pairs, start_date, start_pct_nok, status],
    )
    item = normalize_row(row)
    item["milestones"] = []
    return item


def update_subproject(db, subproject_id, name=None, station_pairs=None, start_date=None, start_pct_nok=None, status=None):
    fields = []
    params = []
    if name is not None:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        fields.append("name = %s")
        params.append(cleaned)
    if station_pairs is not None:
        fields.append("station_pairs = %s")
        params.append(normalize_station_pairs(station_pairs))
    if start_date is not None:
        fields.append("start_date = %s")
        params.append(start_date)
    if start_pct_nok is not None:
        if start_pct_nok < 0:
            raise ValueError("start_pct_nok must be a non-negative number")
        fields.append("start_pct_nok = %s")
        params.append(start_pct_nok)
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        fields.append("status = %s")
        params.append(status)
    if not fields:
        raise ValueError("nothing to update")
    params.append(subproject_id)
    row = db.fetch_one(
        f"UPDATE glidepath_subprojects SET {', '.join(fields)} WHERE id = %s RETURNING *",
        params,
    )
    if not row:
        raise ValueError("subproject not found")
    return normalize_row(row)


def delete_subproject(db, subproject_id):
    row = db.fetch_one("DELETE FROM glidepath_subprojects WHERE id = %s RETURNING id", [subproject_id])
    if not row:
        raise ValueError("subproject not found")


def create_milestone(db, subproject_id, target_date, target_pct_nok, label=None):
    if target_pct_nok is None or target_pct_nok < 0:
        raise ValueError("target_pct_nok must be a non-negative number")

    subproject = db.fetch_one("SELECT id FROM glidepath_subprojects WHERE id = %s", [subproject_id])
    if not subproject:
        raise ValueError("subproject not found")

    row = db.fetch_one(
        """
        INSERT INTO glidepath_milestones (subproject_id, target_date, target_pct_nok, label)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        [subproject_id, target_date, target_pct_nok, label],
    )
    return normalize_row(row)


def update_milestone(db, milestone_id, target_date=None, target_pct_nok=None, label=None):
    fields = []
    params = []
    if target_date is not None:
        fields.append("target_date = %s")
        params.append(target_date)
    if target_pct_nok is not None:
        if target_pct_nok < 0:
            raise ValueError("target_pct_nok must be a non-negative number")
        fields.append("target_pct_nok = %s")
        params.append(target_pct_nok)
    if label is not None:
        fields.append("label = %s")
        params.append(label)
    if not fields:
        raise ValueError("nothing to update")
    params.append(milestone_id)
    row = db.fetch_one(
        f"UPDATE glidepath_milestones SET {', '.join(fields)} WHERE id = %s RETURNING *",
        params,
    )
    if not row:
        raise ValueError("milestone not found")
    return normalize_row(row)


def delete_milestone(db, milestone_id):
    row = db.fetch_one("DELETE FROM glidepath_milestones WHERE id = %s RETURNING id", [milestone_id])
    if not row:
        raise ValueError("milestone not found")
