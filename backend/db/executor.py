"""Phase 8 - Runtime.

Executes the generated SQL and captures the engine's own query plan, so the UI
can show what the database actually did next to what the compiler planned.

Both supported engines are reached through the same three calls. The connection
is read-only wherever the engine can enforce it: a URI flag on SQLite, a
read-only transaction on PostgreSQL.
"""
import os
import sqlite3
import time

from .config import ACTIVE, Backend
from .seed import DB_PATH, build

HARD_ROW_CAP = 1000
TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 5000


class ExecutionError(Exception):
    pass


# --- connections ---------------------------------------------------------
def _connect_sqlite(path=DB_PATH):
    if not os.path.exists(path):
        build(path)
    # read-only URI: the runtime cannot write even if something slips through
    uri = "file:%s?mode=ro" % path.replace("\\", "/")
    conn = sqlite3.connect(uri, uri=True, timeout=TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_postgres(backend):
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(backend.url, row_factory=dict_row,
                           connect_timeout=TIMEOUT_SECONDS)
    conn.read_only = True
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (STATEMENT_TIMEOUT_MS,))
    return conn


def connect(backend: Backend | None = None):
    backend = backend or ACTIVE
    if backend.is_postgres:
        return _connect_postgres(backend)
    return _connect_sqlite()


# kept for callers that predate the backend split
_connect = connect


# --- operations ----------------------------------------------------------
def execute(sql, params, backend: Backend | None = None, row_cap=HARD_ROW_CAP):
    backend = backend or ACTIVE
    conn = connect(backend)
    try:
        started = time.perf_counter()
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        rows = cur.fetchmany(row_cap)
        elapsed = (time.perf_counter() - started) * 1000
        truncated = len(cur.fetchmany(1)) > 0
        columns = [d[0] for d in cur.description] if cur.description else []
        return {
            "columns": columns,
            "rows": [dict(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": round(elapsed, 3),
            "backend": backend.name,
        }
    except Exception as e:
        raise ExecutionError(str(e))
    finally:
        conn.close()


def explain(sql, params, backend: Backend | None = None):
    """The engine's own plan, for comparison against the compiler's."""
    backend = backend or ACTIVE
    conn = connect(backend)
    try:
        cur = conn.cursor()
        if backend.is_postgres:
            cur.execute("EXPLAIN " + sql, tuple(params))
            return [{"detail": list(r.values())[0]} for r in cur.fetchall()]
        cur.execute("EXPLAIN QUERY PLAN " + sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return [{"detail": "EXPLAIN unavailable: %s" % e}]
    finally:
        conn.close()


def table_stats(backend: Backend | None = None):
    backend = backend or ACTIVE
    conn = connect(backend)
    try:
        out = {}
        cur = conn.cursor()
        for t in ("departments", "courses", "students", "enrollments"):
            cur.execute("SELECT COUNT(*) AS n FROM %s" % t)
            row = cur.fetchone()
            out[t] = row["n"] if isinstance(row, dict) else row[0]
        return out
    finally:
        conn.close()
