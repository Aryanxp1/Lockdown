"""SQLite access layer.

One connection per worker thread, WAL journaling, foreign keys on. There is no
ORM: the queries in this project are short enough to read, and SQL is the one
interface that does not change when the portal is extended.

Every helper takes parameters and never interpolates values into SQL.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading

from . import config

_local = threading.local()
_write_lock = threading.RLock()


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(config.DB_PATH),
        timeout=20,
        isolation_level=None,          # we manage transactions explicitly
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def conn() -> sqlite3.Connection:
    existing = getattr(_local, "conn", None)
    if existing is None:
        existing = connect()
        _local.conn = existing
    return existing


def release() -> None:
    """Close this thread's connection. Called at the end of each request."""
    existing = getattr(_local, "conn", None)
    if existing is not None:
        with contextlib.suppress(Exception):
            existing.close()
        _local.conn = None


# --- reads --------------------------------------------------------------

def query(sql: str, params=()) -> list[sqlite3.Row]:
    return conn().execute(sql, params).fetchall()


def one(sql: str, params=()):
    return conn().execute(sql, params).fetchone()


def scalar(sql: str, params=(), default=None):
    row = conn().execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return default
    return row[0]


def exists(sql: str, params=()) -> bool:
    return one(sql, params) is not None


def dicts(rows) -> list[dict]:
    return [dict(row) for row in rows or ()]


def row_dict(row):
    return dict(row) if row is not None else None


# --- writes -------------------------------------------------------------

def execute(sql: str, params=()):
    with _write_lock:
        return conn().execute(sql, params)


def executemany(sql: str, seq):
    with _write_lock:
        return conn().executemany(sql, seq)


@contextlib.contextmanager
def tx():
    """Serialise + wrap a group of writes. Nested calls reuse the outer block."""
    depth = getattr(_local, "tx_depth", 0)
    database = conn()
    if depth:
        _local.tx_depth = depth + 1
        try:
            yield database
        finally:
            _local.tx_depth = depth
        return
    with _write_lock:
        database.execute("BEGIN IMMEDIATE")
        _local.tx_depth = 1
        try:
            yield database
            database.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(Exception):
                database.execute("ROLLBACK")
            raise
        finally:
            _local.tx_depth = 0


def insert(table: str, values: dict, *, replace: bool = False) -> None:
    keys = list(values.keys())
    placeholders = ", ".join("?" for _ in keys)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    sql = "%s INTO %s (%s) VALUES (%s)" % (
        verb, table, ", ".join(keys), placeholders)
    execute(sql, [values[k] for k in keys])


def update(table: str, values: dict, where: str, params=()) -> int:
    if not values:
        return 0
    assignments = ", ".join("%s = ?" % key for key in values)
    sql = "UPDATE %s SET %s WHERE %s" % (table, assignments, where)
    cursor = execute(sql, list(values.values()) + list(params))
    return cursor.rowcount


# --- schema -------------------------------------------------------------

def init_db() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    schema = (config.APP_DIR / "schema.sql").read_text(encoding="utf-8")
    database = conn()
    with _write_lock:
        database.executescript(schema)


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def json_load(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def setting(key: str, default=None):
    return scalar("SELECT value FROM settings WHERE key = ?", (key,), default)


def set_setting(key: str, value: str) -> None:
    from .timeutil import now_iso
    insert("settings", {"key": key, "value": value, "updated_at": now_iso()},
           replace=True)


def next_seq(counter: str) -> int:
    """Monotonic counter kept in the settings table (per-portal, non-racy)."""
    with tx():
        raw = setting("counter:" + counter, "0") or "0"
        try:
            value = int(raw)
        except ValueError:
            value = 0
        value += 1
        set_setting("counter:" + counter, str(value))
    return value
