from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import DATABASE_URL


@contextmanager
def get_conn():
    """Yield a psycopg connection that returns rows as dicts."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set — populate .env (see .env.example)")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def query(sql: str, params: dict | tuple | None = None) -> list[dict]:
    """Run a read query with parameters and return a list of dict rows."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()
