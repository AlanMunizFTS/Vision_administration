from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from app.config import get_settings


class PostgresPool:
    def __init__(self):
        settings = get_settings()
        self._pool = psycopg2.pool.SimpleConnectionPool(
            settings.db_minconn,
            settings.db_maxconn,
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
        )

    @contextmanager
    def cursor(self):
        connection = self._pool.getconn()
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            self._pool.putconn(connection)

    def fetch(self, query, params=None):
        with self.cursor() as cursor:
            cursor.execute(query, params or [])
            return list(cursor.fetchall())

    def fetch_one(self, query, params=None):
        with self.cursor() as cursor:
            cursor.execute(query, params or [])
            return cursor.fetchone()

    def close(self):
        self._pool.closeall()


db_pool = None


def get_db():
    global db_pool
    if db_pool is None:
        db_pool = PostgresPool()
    return db_pool


def close_db():
    global db_pool
    if db_pool is not None:
        db_pool.close()
        db_pool = None
