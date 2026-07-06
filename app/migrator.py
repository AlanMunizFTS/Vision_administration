from pathlib import Path

import psycopg2

from app.config import get_settings


MIGRATIONS_DIR = Path(__file__).with_name("migrations")
SCHEMA_MIGRATIONS_FILE = "000_create_schema_migrations.sql"
ADVISORY_LOCK_ID = 720260703


def _migration_files():
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _connect(settings):
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )


def run_migrations():
    settings = get_settings()
    migration_files = _migration_files()
    if not migration_files:
        return []

    applied = []
    with _connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
            try:
                schema_file = MIGRATIONS_DIR / SCHEMA_MIGRATIONS_FILE
                if schema_file.exists():
                    cursor.execute(schema_file.read_text(encoding="utf-8"))
                    cursor.execute(
                        """
                        INSERT INTO public.schema_migrations (filename)
                        VALUES (%s)
                        ON CONFLICT (filename) DO NOTHING
                        """,
                        (schema_file.name,),
                    )

                for migration_file in migration_files:
                    if migration_file.name == SCHEMA_MIGRATIONS_FILE:
                        continue

                    cursor.execute(
                        "SELECT 1 FROM public.schema_migrations WHERE filename = %s",
                        (migration_file.name,),
                    )
                    if cursor.fetchone():
                        continue

                    cursor.execute(migration_file.read_text(encoding="utf-8"))
                    cursor.execute(
                        """
                        INSERT INTO public.schema_migrations (filename)
                        VALUES (%s)
                        """,
                        (migration_file.name,),
                    )
                    applied.append(migration_file.name)
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))

    return applied
