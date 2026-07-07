import argparse
import io
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings


TARGET_TABLES = {
    "change_log_entries",
    "glidepath_projects",
    "glidepath_subprojects",
    "glidepath_milestones",
    "model_results_central",
}

SEQUENCE_FIXES = [
    ("change_log_entries_id_seq", "change_log_entries", "id"),
    ("glidepath_projects_id_seq", "glidepath_projects", "id"),
    ("glidepath_subprojects_id_seq", "glidepath_subprojects", "id"),
    ("glidepath_milestones_id_seq", "glidepath_milestones", "id"),
    ("model_results_central_central_id_seq", "model_results_central", "central_id"),
]


class CopyBlockReader(io.TextIOBase):
    def __init__(self, source):
        self.source = source
        self.pending = ""
        self.done = False
        self.rows = 0

    def readable(self):
        return True

    def _read_data_line(self):
        line = self.source.readline()
        if line == "":
            self.done = True
            return ""

        if line.rstrip("\r\n") == r"\.":
            self.done = True
            return ""

        self.rows += 1
        return line

    def read(self, size=-1):
        if size is None or size < 0:
            chunks = [self.pending]
            self.pending = ""
            while not self.done:
                chunks.append(self._read_data_line())
            return "".join(chunks)

        while len(self.pending) < size and not self.done:
            self.pending += self._read_data_line()

        output = self.pending[:size]
        self.pending = self.pending[size:]
        return output


def parse_copy_table(line):
    prefix = "COPY public."
    if not line.startswith(prefix):
        return None
    return line[len(prefix) :].split(" ", 1)[0]


def skip_copy_block(source):
    for line in source:
        if line.rstrip("\r\n") == r"\.":
            return
    raise RuntimeError("COPY block ended unexpectedly")


def ensure_target_tables_empty(cursor):
    non_empty = []
    for table in sorted(TARGET_TABLES):
        query = sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(table))
        cursor.execute(query)
        count = cursor.fetchone()[0]
        if count:
            non_empty.append((table, count))

    if non_empty:
        detail = ", ".join(f"{table}={count}" for table, count in non_empty)
        raise RuntimeError(f"Refusing to import because target tables are not empty: {detail}")


def apply_sequence_fixes(cursor):
    for sequence, table, column in SEQUENCE_FIXES:
        query = sql.SQL(
            """
            SELECT setval(
                %s,
                COALESCE((SELECT MAX({column}) FROM public.{table}), 1),
                (SELECT MAX({column}) IS NOT NULL FROM public.{table})
            )
            """
        ).format(table=sql.Identifier(table), column=sql.Identifier(column))
        cursor.execute(query, (f"public.{sequence}",))


def import_dump_data(dump_path, encoding):
    settings = get_settings()
    imported = {}

    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=10,
    )

    try:
        with conn:
            with conn.cursor() as cursor:
                ensure_target_tables_empty(cursor)

                with dump_path.open("r", encoding=encoding, errors="strict", newline="") as source:
                    for line in source:
                        clean = line.rstrip("\r\n")
                        table = parse_copy_table(clean)
                        if table is None:
                            continue

                        if table not in TARGET_TABLES:
                            skip_copy_block(source)
                            continue

                        reader = CopyBlockReader(source)
                        cursor.copy_expert(clean, reader)
                        imported[table] = reader.rows

                apply_sequence_fixes(cursor)
    finally:
        conn.close()

    return imported


def main():
    parser = argparse.ArgumentParser(
        description="Import only data COPY blocks from prod_backup.sql into the existing Vision schema."
    )
    parser.add_argument("dump_path", nargs="?", default="prod_backup.sql")
    parser.add_argument("--encoding", default="utf-16")
    args = parser.parse_args()

    dump_path = Path(args.dump_path)
    if not dump_path.exists():
        raise SystemExit(f"Dump file not found: {dump_path}")

    imported = import_dump_data(dump_path, args.encoding)
    print("Imported rows:")
    for table in sorted(TARGET_TABLES):
        print(f"  {table}: {imported.get(table, 0)}")
    print("Sequences synchronized.")


if __name__ == "__main__":
    main()
