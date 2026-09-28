"""Isolation tests: many hackathons on one install, and no way between them.

These tests boot a private portal (its own data directory, its own port, its own
HTTP server thread) from the same fixtures the portal ships with, then behave
like a hostile organizer: one login that manages nothing, one that manages the
fixture events, and forms full of row ids belonging to an event the caller was
never added to.

The rule under test is the one the platform rests on: authorization is decided
in the API from the event the request actually addresses, never from what a page
happened to render. Every check therefore goes through HTTP with the real
cookies the portal issues.

Standard library only. Run it with:

    python -m unittest tests.test_event_isolation -v
"""

import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import warnings

# The portal holds one SQLite connection per thread and closes them when its
# server stops; the interpreter's own shutdown warning adds nothing here.
warnings.filterwarnings("ignore", category=ResourceWarning)

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The portal reads its data directory when it is imported, so this has to be
# decided first: an in-process test never touches the operator's database.
DATA_DIR = tempfile.mkdtemp(prefix="lockdown-isolation-")
os.environ["PORTAL_DATA_DIR"] = DATA_DIR

from app import boot, config, db, server                        # noqa: E402

FIXTURE_EVENT = "evt_01"
ZERO_DEP_EVENT = "evt_zero_dep"
FIXTURE_SLUG = "sample-hack-2026"
ZERO_DEP_SLUG = "zero-dependency-2026"

ORGANIZER = "sess_org_3f9a21c4"          # manages the three seeded events
ORGANIZER_EMAIL = "organizer@dogfood.test"
OUTSIDER = "sess_org_b_7c31de84"         # a valid organizer who manages nothing
OUTSIDER_EMAIL = "nadia.frost@dogfood.test"

MANAGE_PATHS = ("", "/stages", "/teams", "/submissions", "/judges", "/assignments",
                "/reviews", "/results", "/audit", "/settings")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report 3xx instead of following it, so a redirect can be asserted."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class IsolationTest(unittest.TestCase):
    """One portal, three hackathons, two organizers."""

    @classmethod
    def setUpClass(cls):
        db.init_db()
        boot.seed(force=True, quiet=True)
        cls.httpd = server.build_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.opener = urllib.request.build_opener(NoRedirect)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    # --- request helpers ------------------------------------------------

    def call(self, path, *, session=None, method="GET", form=None, csrf=None):
        """Return (status, body). Never raises on an HTTP error status."""
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data, headers = None, {}
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if session:
            headers["Cookie"] = "session=" + session
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read().decode("utf-8", "replace")
            finally:
                exc.close()

    def csrf_for(self, email):
        """The CSRF token the portal issued to that account's demo session."""
        conn = sqlite3.connect(str(config.DB_PATH))
        try:
            row = conn.execute("""SELECT s.csrf_token FROM sessions s
                                   JOIN users u ON u.id = s.user_id
                                  WHERE u.email = ? AND s.revoked_at IS NULL""",
                               (email,)).fetchone()
        finally:
            conn.close()
        return row[0] if row else ""

    def scalar(self, sql, params=()):
        conn = sqlite3.connect(str(config.DB_PATH))
        try:
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()

    def execute(self, *statements):
        conn = sqlite3.connect(str(config.DB_PATH))
        try:
            for sql, params in statements:
                conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    # --- the tests ------------------------------------------------------

    def test_shelf_lists_only_the_events_the_caller_manages(self):
        status, body = self.call("/organizer", session=ORGANIZER)
        self.assertEqual(status, 200)
        self.assertIn("Sample Hack 2026", body)
        self.assertIn("Zero Dependency 2026", body)

        status, body = self.call("/organizer", session=OUTSIDER)
        self.assertEqual(status, 200)
        self.assertIn("do not manage a hackathon yet", body)
        self.assertNotIn("Sample Hack 2026", body)
        self.assertNotIn("Zero Dependency 2026", body)

    def test_an_outsider_cannot_open_any_management_page(self):
        for suffix in MANAGE_PATHS:
            with self.subTest(path=suffix or "/organizer/events/{id}"):
                status, body = self.call(
                    "/organizer/events/%s%s" % (FIXTURE_EVENT, suffix), session=OUTSIDER)
                self.assertEqual(status, 403)
                self.assertIn("do not manage", body)
                self.assertNotIn("Sample Hack 2026", body)

    def test_an_outsider_cannot_use_the_shortcuts(self):
        for path in ("/organizer/submissions", "/organizer/judges", "/organizer/audit"):
            with self.subTest(path=path):
                status, _ = self.call(path, session=OUTSIDER)
                self.assertEqual(status, 403)
        # Being allowed to call an endpoint is not the same as owning its data.
        status, _ = self.call("/api/export.csv", session=OUTSIDER)
        self.assertEqual(status, 403)
        status, _ = self.call("/api/judge/scores", session=OUTSIDER)
        self.assertEqual(status, 403)

    def test_the_organizer_who_does_manage_them_still_gets_in(self):
        status, _ = self.call("/api/export.csv", session=ORGANIZER)
        self.assertEqual(status, 200)
        status, _ = self.call("/api/export.csv?event=" + ZERO_DEP_EVENT,
                              session=ORGANIZER)
        self.assertEqual(status, 200)
        status, body = self.call("/organizer/events/%s" % ZERO_DEP_EVENT,
                                 session=ORGANIZER)
        self.assertEqual(status, 200)
        self.assertIn("Zero Dependency 2026", body)

    def test_an_outsider_cannot_write_to_someone_elses_event(self):
        before = self.scalar("SELECT COUNT(*) FROM event_stages WHERE event_id = ?",
                             (FIXTURE_EVENT,))
        for path, form in (
                ("/organizer/events/%s/stages" % FIXTURE_EVENT,
                 {"name": "Hostile stage"}),
                ("/organizer/events/%s/judges" % FIXTURE_EVENT,
                 {"email": "hostile@example.org"}),
                ("/organizer/events/%s/organizers" % FIXTURE_EVENT,
                 {"email": "hostile@example.org"}),
                ("/organizer/events/%s/results" % FIXTURE_EVENT, {"note": "hostile"})):
            with self.subTest(path=path):
                status, _ = self.call(path, session=OUTSIDER, method="POST", form=form,
                                      csrf=self.csrf_for(OUTSIDER_EMAIL))
                self.assertEqual(status, 403)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM event_stages WHERE event_id = ?",
                        (FIXTURE_EVENT,)), before,
            "a refused write changed the event")
        self.assertEqual(
            self.scalar("""SELECT COUNT(*) FROM judge_invitations
                            WHERE event_id = ? AND email = 'hostile@example.org'""",
                        (FIXTURE_EVENT,)), 0)
        self.assertEqual(
            self.scalar("""SELECT COUNT(*) FROM event_organizers eo
                             JOIN users u ON u.id = eo.user_id
                            WHERE eo.event_id = ? AND u.email = 'hostile@example.org'""",
                        (FIXTURE_EVENT,)), 0)


    def test_an_organizer_cannot_borrow_row_ids_from_another_event(self):
        """The organizer *is* allowed to write -- just not across events.

        Both ids are re-checked against the event in the URL, so a crafted form
        becomes a 404 instead of an assignment that spans two hackathons.
        """
        csrf = self.csrf_for(ORGANIZER_EMAIL)
        foreign_project = self.scalar(
            """SELECT id FROM projects WHERE event_id = ? AND status = 'submitted'
                AND duplicate_of IS NULL LIMIT 1""", (ZERO_DEP_EVENT,))
        judge = self.scalar(
            "SELECT email FROM users WHERE role = 'judge' ORDER BY email LIMIT 1")
        before = self.scalar("SELECT COUNT(*) FROM assignments WHERE event_id = ?",
                             (FIXTURE_EVENT,))

        status, _ = self.call("/organizer/events/%s/assignments" % FIXTURE_EVENT,
                              session=ORGANIZER, method="POST", csrf=csrf,
                              form={"project_id": foreign_project, "judge": judge})
        self.assertEqual(status, 404, "a project from another event was accepted")
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM assignments WHERE event_id = ?",
                        (FIXTURE_EVENT,)), before)

        foreign_stage = self.scalar(
            "SELECT id FROM event_stages WHERE event_id = ? LIMIT 1", (ZERO_DEP_EVENT,))
        status, _ = self.call("/organizer/events/%s/stages/remove" % FIXTURE_EVENT,
                              session=ORGANIZER, method="POST", csrf=csrf,
                              form={"stage_id": foreign_stage})
        self.assertEqual(status, 404, "a stage from another event was deleted")
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM event_stages WHERE id = ?",
                        (foreign_stage,)), 1)

    def test_public_pages_never_mix_two_hackathons(self):
        zero_dep_title = self.scalar(
            """SELECT title FROM projects WHERE event_id = ? AND status = 'submitted'
                LIMIT 1""", (ZERO_DEP_EVENT,))
        fixture_title = self.scalar(
            """SELECT title FROM projects WHERE event_id = ? AND status = 'submitted'
                LIMIT 1""", (FIXTURE_EVENT,))

        status, body = self.call("/events/%s" % ZERO_DEP_SLUG)
        self.assertEqual(status, 200)
        self.assertIn("Zero Dependency 2026", body)

        status, body = self.call("/events/%s/gallery" % ZERO_DEP_SLUG)
        self.assertEqual(status, 200)
        self.assertIn(zero_dep_title, body)
        self.assertNotIn(fixture_title, body)

        status, body = self.call("/events/%s/gallery" % FIXTURE_SLUG)
        self.assertEqual(status, 200)
        self.assertIn(fixture_title, body)
        self.assertNotIn(zero_dep_title, body)

        status, body = self.call("/events")
        self.assertEqual(status, 200)
        self.assertIn("Sample Hack 2026", body)
        self.assertIn("Zero Dependency 2026", body)


    def test_a_hidden_gallery_is_hidden_from_the_public_only(self):
        """`gallery_visible = 0` is a switch, not a deletion: organizers keep it."""
        self.execute(("UPDATE events SET gallery_visible = 0 WHERE id = ?",
                      (ZERO_DEP_EVENT,)))
        try:
            status, body = self.call("/events/%s/gallery" % ZERO_DEP_SLUG)
            self.assertEqual(status, 403)
            self.assertIn("not public", body)
            status, _ = self.call("/events/%s/gallery" % ZERO_DEP_SLUG, session=ORGANIZER)
            self.assertEqual(status, 200,
                             "an organizer lost access to their own gallery")
            status, _ = self.call("/events/%s/gallery" % ZERO_DEP_SLUG, session=OUTSIDER)
            self.assertEqual(status, 403, "an outsider was let into a hidden gallery")
        finally:
            self.execute(("UPDATE events SET gallery_visible = 1 WHERE id = ?",
                          (ZERO_DEP_EVENT,)))
        status, _ = self.call("/events/%s/gallery" % ZERO_DEP_SLUG)
        self.assertEqual(status, 200)

    def test_a_draft_hackathon_is_invisible_to_everyone_else(self):
        csrf = self.csrf_for(ORGANIZER_EMAIL)
        status, _ = self.call("/organizer/events/new", session=ORGANIZER)
        self.assertEqual(status, 200)
        status, _ = self.call("/organizer/events/new", session=ORGANIZER, method="POST",
                              csrf=csrf, form=self.create_form(name=""))
        self.assertEqual(status, 400, "an unnamed hackathon was created")
        status, _ = self.call("/organizer/events/new", session=ORGANIZER, method="POST",
                              csrf=csrf, form=self.create_form())
        self.assertEqual(status, 303)
        try:
            self.assertEqual(self.call("/events/hidden-draft")[0], 404)
            self.assertEqual(self.call("/events/hidden-draft", session=OUTSIDER)[0], 404)
            status, body = self.call("/events/hidden-draft", session=ORGANIZER)
            self.assertEqual(status, 200)
            self.assertIn("Hidden Draft", body)
        finally:
            self.remove_draft()

    def test_every_refusal_lands_in_the_audit_log(self):
        refused = self.scalar("""SELECT COUNT(*) FROM audit_log
                                  WHERE outcome = 'refused'
                                    AND action = 'event.manage_refused'""")
        attributable = self.scalar(
            """SELECT COUNT(*) FROM audit_log
                WHERE outcome = 'refused'
                  AND actor_id = (SELECT id FROM users WHERE email = ?)""",
            (OUTSIDER_EMAIL,))
        self.assertGreaterEqual(refused, len(MANAGE_PATHS))
        self.assertGreaterEqual(attributable, len(MANAGE_PATHS),
                                "the outsider's attempts are not attributable")

    # --- fixtures for the tests above -----------------------------------

    def remove_draft(self):
        """Delete the draft the create test made, if it got that far."""
        event_id = self.scalar("SELECT id FROM events WHERE slug = 'hidden-draft'")
        if not event_id:
            return
        self.execute(("DELETE FROM event_organizers WHERE event_id = ?", (event_id,)),
                     ("DELETE FROM event_stages WHERE event_id = ?", (event_id,)),
                     ("DELETE FROM tracks WHERE event_id = ?", (event_id,)),
                     ("DELETE FROM prizes WHERE event_id = ?", (event_id,)),
                     ("DELETE FROM rubrics WHERE event_id = ?", (event_id,)),
                     ("DELETE FROM events WHERE id = ?", (event_id,)))

    @staticmethod
    def create_form(**overrides):
        """A create form that passes validation, before overrides."""
        form = {
            "name": "Hidden Draft",
            "slug": "hidden-draft",
            "tagline": "Only its organizers may see this.",
            "description": "A draft hackathon, used to prove that an unpublished "
                           "event is invisible to everyone who does not run it.",
            "rules": "One project per team.",
            "banner": "HD",
            "cover_tone": "green",
            "location": "Online",
            "status": "draft",
            "min_team_size": "1",
            "max_team_size": "4",
            "target_reviews": "3",
            "tracks_text": "Only track | The single track here.",
            "prizes_text": "One prize | Best score | Nobody yet.",
            "rubric_text": "craft | Craft | 1.0 | Is it built well?",
            "gallery_visible": "1",
            "results_visible": "1",
        }
        form.update(overrides)
        return form


if __name__ == "__main__":
    unittest.main(verbosity=2)

