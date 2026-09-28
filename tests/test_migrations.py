"""Migrations: an old database gets upgraded in place, additively.

`app/schema.sql` only describes a *new* database; a portal that was booted weeks
ago already has its tables, so the schema script cannot add a column to them.
`app/migrations.py` is what closes that gap, and these tests are what keep it
honest:

  * a version-1 database gains exactly the missing columns and tables;
  * every row that was already there is still there, with sane defaults;
  * running it again changes nothing (it is idempotent);
  * a database already created from `schema.sql` needs no migration at all,
    which is how `schema.sql` and `SCHEMA_VERSION` are kept in step.

Standard library only, and no portal state: this module talks to a throwaway
SQLite file through `app.migrations` directly, so it can run beside the
HTTP-level isolation tests without touching their database.

    python -m unittest tests.test_migrations -v
"""

import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import migrations                                     # noqa: E402

# The parts of a version-1 database the migration has an opinion about, plus one
# row in each: the point of the test is that the rows survive the upgrade.
V1_SCHEMA = """
CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE users (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE, name TEXT NOT NULL,
  role TEXT NOT NULL, password_hash TEXT, created_at TEXT NOT NULL
);
CREATE TABLE events (
  id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  tagline TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
  rules TEXT NOT NULL DEFAULT '', seq INTEGER NOT NULL DEFAULT 100,
  status TEXT NOT NULL DEFAULT 'published',
  registration_open TEXT, registration_close TEXT, team_formation_close TEXT,
  submissions_open TEXT, submissions_close TEXT, judging_open TEXT,
  judging_close TEXT, results_publish_at TEXT,
  min_team_size INTEGER NOT NULL DEFAULT 1, max_team_size INTEGER NOT NULL DEFAULT 4,
  reviews_required INTEGER NOT NULL DEFAULT 3, target_reviews INTEGER NOT NULL DEFAULT 3,
  created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE event_stages (
  id TEXT PRIMARY KEY, event_id TEXT NOT NULL, seq INTEGER NOT NULL, key TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', opens_at TEXT,
  closes_at TEXT, status TEXT NOT NULL DEFAULT 'scheduled', UNIQUE (event_id, key)
);
CREATE TABLE tracks (
  id TEXT PRIMARY KEY, event_id TEXT NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', seq INTEGER NOT NULL DEFAULT 10,
  UNIQUE (event_id, slug)
);
CREATE TABLE prizes (
  id TEXT PRIMARY KEY, event_id TEXT NOT NULL, track_id TEXT, rank INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE legacy_only (id TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT '');
INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1');
INSERT INTO users(id, email, name, role, created_at)
  VALUES ('usr_old', 'old.organizer@example.org', 'Old Organizer', 'organizer', '2026-01-01T00:00:00Z');
INSERT INTO events(id, slug, name, created_at, updated_at)
  VALUES ('evt_old', 'old-event', 'Old Event', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
INSERT INTO event_stages(id, event_id, seq, key, name)
  VALUES ('stg_old', 'evt_old', 10, 'submission', 'Submission');
INSERT INTO tracks(id, event_id, slug, name)
  VALUES ('trk_old', 'evt_old', 'old-track', 'Old Track');
INSERT INTO prizes(id, event_id, rank, title)
  VALUES ('prz_old', 'evt_old', 1, 'Old Prize');
INSERT INTO legacy_only(id, note) VALUES ('x', 'not part of the current schema');
"""


class MigrationTest(unittest.TestCase):
    """A version-1 database, upgraded."""

    def setUp(self):
        handle, path = tempfile.mkstemp(prefix="lockdown-v1-", suffix=".sqlite3")
        os.close(handle)
        handle_path = pathlib.Path(path)
        self.addCleanup(handle_path.unlink, True)
        self.conn = sqlite3.connect(path)
        self.addCleanup(self.conn.close)
        self.conn.executescript(V1_SCHEMA)
        self.conn.commit()

    def columns(self, table):
        return {row[1] for row in self.conn.execute("PRAGMA table_info(%s)" % table)}

    def tables(self):
        return {row[0] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}

    # --- the upgrade ----------------------------------------------------

    def test_a_version_one_database_gains_exactly_what_is_missing(self):
        report = migrations.migrate(self.conn)
        self.assertEqual(report["from"], 1)
        self.assertEqual(report["to"], migrations.SCHEMA_VERSION)
        self.assertTrue(report["changed"])
        self.assertEqual(sorted(report["added"]), sorted(
            "%s.%s" % (table, column)
            for table, column, _definition in migrations.ADDED_COLUMNS))
        for table, column, _definition in migrations.ADDED_COLUMNS:
            self.assertIn(column, self.columns(table))
        self.assertIn("event_organizers", self.tables())
        self.assertEqual(migrations.recorded_version(self.conn),
                         migrations.SCHEMA_VERSION)

    def test_the_report_names_the_objects_it_had_to_ensure(self):
        """`__main__` prints this, so it has to name real objects."""
        report = migrations.migrate(self.conn)
        self.assertIn("table event_organizers", report["created"])
        self.assertIn("index idx_event_organizers_user", report["created"])
        # Everything it claims to have created must really exist.
        for item in report["created"]:
            kind, name = item.split(" ", 1)
            if kind == "index":
                continue
            self.assertIn(name, self.tables(),
                          "%s claims %r exists" % (report, name))
        # A create that was already satisfied is still reported, but that must not
        # be confused with a change: the second run is a no-op.
        again = migrations.migrate(self.conn)
        self.assertFalse(again["changed"], again)

    def test_every_existing_row_survives_with_a_default(self):
        migrations.migrate(self.conn)
        statement = "SELECT * FROM events WHERE id = 'evt_old'"
        names = [column[1] for column in self.conn.execute("PRAGMA table_info(events)")]
        row = dict(zip(names, self.conn.execute(statement).fetchone()))
        self.assertEqual(row["name"], "Old Event")
        self.assertEqual(row["status"], "published")
        # The new columns arrive with values that keep the old behaviour: an
        # existing hackathon stays visible and keeps its plain cover.
        self.assertEqual(row["banner"], "")
        self.assertEqual(row["cover_tone"], "ink")
        self.assertEqual(row["location"], "")
        self.assertEqual(row["gallery_visible"], 1)
        self.assertEqual(row["results_visible"], 1)
        for table, row_id in (("event_stages", "stg_old"), ("tracks", "trk_old"),
                              ("prizes", "prz_old"), ("users", "usr_old")):
            with self.subTest(table=table):
                self.assertEqual(self.conn.execute(
                    "SELECT COUNT(*) FROM %s WHERE id = ?" % table, (row_id,)).fetchone()[0], 1)

    def test_running_it_twice_changes_nothing(self):
        migrations.migrate(self.conn)
        again = migrations.migrate(self.conn)
        self.assertFalse(again["changed"])
        self.assertEqual(again["added"], [])
        self.assertEqual(again["from"], migrations.SCHEMA_VERSION)

    def test_an_event_organizer_gets_one_row_per_event(self):
        migrations.migrate(self.conn)
        insert = """INSERT INTO event_organizers(id, event_id, user_id, role, added_at)
                    VALUES (?, 'evt_old', 'usr_old', ?, '2026-01-02T00:00:00Z')"""
        self.conn.execute(insert, ("evo_1", "owner"))
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(insert, ("evo_2", "organizer"))
        self.conn.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(insert, ("evo_3", "dictator"))
        self.conn.rollback()

    def test_a_missing_table_is_skipped_not_invented(self):
        """A stripped-down database is upgraded, not invented."""
        self.conn.execute("DROP TABLE event_stages")
        self.conn.commit()
        report = migrations.migrate(self.conn)
        self.assertNotIn("event_stages", self.tables())
        self.assertIn("events.cover_tone", report["added"])
        self.assertNotIn("event_stages.published_at", report["added"])

    def test_a_broken_database_is_reported_loudly(self):
        """`schema.sql` runs first on every boot, so a missing indexed table is a fault.

        The migration refuses to guess: it names the statement it could not run
        instead of booting a portal whose indexes silently do not exist.
        """
        self.conn.execute("DROP TABLE prizes")
        self.conn.commit()
        with self.assertRaises(RuntimeError) as caught:
            migrations.migrate(self.conn)
        self.assertIn("idx_prizes_event", str(caught.exception))

    def test_an_unrelated_table_is_never_touched(self):
        migrations.migrate(self.conn)
        self.assertEqual(self.conn.execute(
            "SELECT note FROM legacy_only WHERE id = 'x'").fetchone()[0],
            "not part of the current schema")

    def test_the_real_version_one_schema_upgrades_with_every_row_intact(self):
        """The hand-made schema above is a stand-in; this is the genuine article.

        The version-1 schema this codebase actually shipped is read out of git
        history, so upgrading it is the exact path an existing single-event
        install takes. History is searched rather than a commit hash hard-coded,
        because once the multi-hackathon migration is itself committed, HEAD's
        `schema.sql` is no longer version 1 -- and a test that silently stops
        checking is worse than no test. There is no `git` in the Docker image, so
        in a container this steps aside and the hand-made schema carries on.
        """
        def show(reference):
            return subprocess.run(["git", "show", reference], cwd=str(ROOT),
                                  capture_output=True)

        try:
            history = subprocess.run(["git", "rev-list", "HEAD", "--",
                                      "app/schema.sql"],
                                     cwd=str(ROOT), capture_output=True)
        except OSError:                          # no git binary (the container)
            self.skipTest("git is not installed; nothing to compare against")
        if history.returncode != 0:
            self.skipTest("not a git checkout; nothing to compare against")

        legacy, source = None, ""
        for sha in history.stdout.decode("utf-8").split():
            blob = show("%s:app/schema.sql" % sha)
            if blob.returncode != 0:
                continue
            text = blob.stdout.decode("utf-8")
            if "schema_version', '1'" in text:
                legacy, source = text, sha
                break
        if legacy is None:
            self.skipTest("no version-1 schema found in history")

        self.assertNotIn("event_organizers", legacy,
                         "%s is already multi-hackathon" % source[:12])
        self.assertNotIn("gallery_visible", legacy, "%s is already multi-hackathon" % source[:12])

        handle, path = tempfile.mkstemp(prefix="lockdown-real-v1-", suffix=".sqlite3")
        os.close(handle)
        handle_path = pathlib.Path(path)
        self.addCleanup(handle_path.unlink, True)
        database = sqlite3.connect(path)
        self.addCleanup(database.close)
        database.executescript(legacy)

        # One row in every table a competition lives in, inserted generically so
        # the test does not drift when the old schema's columns change.
        def insert(table, **values):
            missing = [row[1] for row in database.execute(
                "PRAGMA table_info(%s)" % table) if row[3] and row[4] is None
                and row[5] == 0 and row[1] not in values]
            for column in missing:
                # NOT NULL foreign keys need a row that really exists.
                values[column] = {"created_by": "usr_r1", "event_id": "evt_r1"}.get(
                    column, "filler")
            keys = list(values)
            database.execute("INSERT INTO %s (%s) VALUES (%s)"
                             % (table, ", ".join(keys), ", ".join("?" for _ in keys)),
                             [values[k] for k in keys])

        insert("users", id="usr_r1", email="r1@old.test", name="R1", role="organizer",
               created_at="2026-01-01T00:00:00Z")
        insert("events", id="evt_r1", slug="real-old-event", name="Real Old Event",
               created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
        insert("rubrics", id="rub_r1", event_id="evt_r1", name="Old rubric",
               created_at="2026-01-01T00:00:00Z")
        insert("tracks", id="trk_r1", event_id="evt_r1", slug="old-track",
               name="Old Track")
        insert("teams", id="tm_r1", event_id="evt_r1", name="Old Team", slug="old-team",
               invite_code="OLD1", created_by="usr_r1",
               created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
        insert("projects", id="prj_r1", event_id="evt_r1", team_id="tm_r1",
               title="Real Old Project", created_by="usr_r1",
               created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
        insert("result_publications", id="pub_r1", event_id="evt_r1", revision_no=1,
               published_by="usr_r1", published_at="2026-01-01T00:00:00Z",
               checksum="cafebabe")
        database.commit()

        watched = ("users", "events", "rubrics", "tracks", "teams", "projects",
                   "result_publications")
        before = {table: database.execute(
            "SELECT COUNT(*) FROM %s" % table).fetchone()[0] for table in watched}

        report = migrations.migrate(database)
        database.commit()

        self.assertEqual(report["from"], 1, "the real schema starts at version 1")
        self.assertTrue(report["changed"])
        self.assertEqual(migrations.recorded_version(database),
                         migrations.SCHEMA_VERSION)
        for table in watched:
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0],
                before[table], "%s lost a row in the upgrade" % table)
        self.assertEqual(
            database.execute("SELECT name FROM events WHERE id = 'evt_r1'"
                             ).fetchone()[0], "Real Old Event")
        self.assertEqual(
            database.execute("SELECT title FROM projects WHERE id = 'prj_r1'"
                             ).fetchone()[0], "Real Old Project")
        self.assertEqual(
            database.execute("SELECT checksum FROM result_publications"
                             " WHERE id = 'pub_r1'").fetchone()[0], "cafebabe")
        self.assertEqual(
            database.execute("SELECT cover_tone FROM events WHERE id = 'evt_r1'"
                             ).fetchone()[0], "ink", "the new column defaulted")
        self.assertEqual(
            database.execute("SELECT gallery_visible FROM events WHERE id = 'evt_r1'"
                             ).fetchone()[0], 1)
        self.assertIn("event_organizers", {row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")})
        # Idempotent on the real schema too.
        self.assertFalse(migrations.migrate(database)["changed"])
        self.assertEqual(
            database.execute("SELECT title FROM projects WHERE id = 'prj_r1'"
                             ).fetchone()[0], "Real Old Project")

    def test_schema_sql_already_describes_the_current_version(self):
        """A brand new database must need no migration at all."""
        handle, path = tempfile.mkstemp(prefix="lockdown-fresh-", suffix=".sqlite3")
        os.close(handle)
        handle_path = pathlib.Path(path)
        handle_path.unlink(missing_ok=True)
        self.addCleanup(handle_path.unlink, True)
        database = sqlite3.connect(path)
        self.addCleanup(database.close)
        database.executescript((ROOT / "app" / "schema.sql").read_text(encoding="utf-8"))
        report = migrations.migrate(database)
        self.assertFalse(report["changed"],
                         "schema.sql is behind SCHEMA_VERSION: %s" % (report,))
        self.assertEqual(migrations.recorded_version(database),
                         migrations.SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main(verbosity=2)

