"""Idempotent schema migrations.

`app/schema.sql` describes a *new* database. A database that was booted weeks ago
keeps the tables it already has, so `CREATE TABLE IF NOT EXISTS` would silently
leave it behind: a new column would never appear, and every query that reads it
would fail at runtime instead of at boot.

This module closes that gap. It runs right after the schema script on every
boot, compares the definition against the live database and adds whatever is
missing. It only ever *adds* tables and defaulted columns, so existing events,
teams, projects, reviews and published results are preserved byte for byte.

Migration history
-----------------

  1 -> 2  Multi-hackathon. Events gain presentation and visibility columns
          (banner, cover tone, location, gallery visibility, results
          visibility) and the `event_organizers` membership table that decides
          which organizer may manage which hackathon.
"""

from __future__ import annotations

import contextlib

SCHEMA_VERSION = 2

# (table, column, column definition). Added only when the column is missing.
# No UNIQUE or CHECK here on purpose: SQLite cannot add those to an existing
# table, so the same rules are enforced by `app/eventadmin.py` on the way in.
ADDED_COLUMNS = (
    ("events", "banner", "TEXT NOT NULL DEFAULT ''"),
    ("events", "cover_tone", "TEXT NOT NULL DEFAULT 'ink'"),
    ("events", "location", "TEXT NOT NULL DEFAULT ''"),
    ("events", "gallery_visible", "INTEGER NOT NULL DEFAULT 1"),
    ("events", "results_visible", "INTEGER NOT NULL DEFAULT 1"),
    ("event_stages", "published_at", "TEXT"),
)

# Statements run on every boot after the column pass. `IF NOT EXISTS` makes them
# safe to repeat, and they are the tables that cannot be expressed as a column.
EXTRA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS event_organizers (
         id       TEXT PRIMARY KEY,
         event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
         user_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
         role     TEXT NOT NULL DEFAULT 'organizer'
                  CHECK (role IN ('owner','organizer')),
         added_by TEXT REFERENCES users(id),
         added_at TEXT NOT NULL,
         UNIQUE (event_id, user_id)
       )""",
    "CREATE INDEX IF NOT EXISTS idx_event_organizers_user ON event_organizers(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tracks_event ON tracks(event_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_prizes_event ON prizes(event_id, rank)",
)


def tables(database) -> set:
    rows = database.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def columns(database, table: str) -> set:
    with contextlib.suppress(Exception):
        return {row[1] for row in database.execute("PRAGMA table_info(%s)" % table).fetchall()}
    return set()


def recorded_version(database) -> int:
    with contextlib.suppress(Exception):
        row = database.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
        if row is not None:
            return int(row[0])
    return 0


def migrate(database) -> dict:
    """Bring an existing database up to `SCHEMA_VERSION`. Returns a report.

    Called by `db.init_db()` on every boot. On a brand new database everything
    already exists, so the report is empty and this costs one PRAGMA per table.
    """
    known = tables(database)
    added, created = [], []

    for table, column, definition in ADDED_COLUMNS:
        if table not in known:
            continue                      # schema.sql created it with the column
        if column in columns(database, table):
            continue
        database.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, definition))
        added.append("%s.%s" % (table, column))

    for statement in EXTRA_STATEMENTS:
        try:
            database.execute(statement)
        except Exception as exc:            # pragma: no cover - defensive only
            raise RuntimeError("migration statement failed: %s" % statement) from exc
        # `CREATE TABLE IF NOT EXISTS <name>` and `CREATE INDEX IF NOT EXISTS
        # <name>` both put the name in the same position. Whether the object
        # already existed is not worth a second query: the statement is
        # idempotent by construction.
        words = statement.split()
        if len(words) >= 6 and words[0] == "CREATE" and words[1] in ("TABLE", "INDEX"):
            created.append("%s %s" % (words[1].lower(), words[5]))

    previous = recorded_version(database)
    if previous != SCHEMA_VERSION:
        database.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),))

    return {"from": previous, "to": SCHEMA_VERSION, "added": added,
            "created": created,
            "changed": bool(added) or previous != SCHEMA_VERSION}
