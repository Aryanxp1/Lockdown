"""Central configuration.

Nothing here is required: `python3 -m app` boots with sane defaults and every
value can be overridden with an environment variable so the same image works
on a laptop, in docker compose and in CI.
"""

from __future__ import annotations

import os
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


# --- networking ---------------------------------------------------------
HOST = _env("PORTAL_HOST", "0.0.0.0")
# 8081 rather than 8080: 8080 is the first port most local dev servers grab, and
# a collision there would look like a broken portal. Override with PORTAL_PORT
# or `python3 -m app --port`. `.dogfood.toml` points at this default.
PORT = int(_env("PORTAL_PORT", "8081"))
BASE_URL = _env("PORTAL_BASE_URL", "http://localhost:%d" % PORT).rstrip("/")
PUBLIC_EVENT_SLUG = _env("PORTAL_PRIMARY_EVENT", "sample-hack-2026")

# --- storage ------------------------------------------------------------
DATA_DIR = pathlib.Path(_env("PORTAL_DATA_DIR", str(ROOT_DIR / "data")))
DB_PATH = DATA_DIR / "portal.sqlite3"
FIXTURES_PATH = pathlib.Path(_env("PORTAL_FIXTURES", str(ROOT_DIR / "fixtures.json")))
STATIC_DIR = APP_DIR / "views" / "static"

# --- boot behaviour -----------------------------------------------------
SEED_ON_BOOT = _env("PORTAL_SEED", "1").lower() not in ("0", "false", "no")
RESET_ON_BOOT = _env("PORTAL_RESET", "0").lower() in ("1", "true", "yes")

# --- sessions -----------------------------------------------------------
SESSION_COOKIE = "session"
SESSION_TTL_DAYS = int(_env("PORTAL_SESSION_DAYS", "30"))
# Demo sessions handed to the acceptance checker never expire, otherwise a
# report generated months later would fail for the wrong reason.
DEMO_SESSION_EXPIRY = "2099-01-01T00:00:00Z"

# --- crypto -------------------------------------------------------------
PBKDF2_ITERATIONS = int(_env("PORTAL_PBKDF2_ITERATIONS", "120000"))
SCRYPT_N = 2 ** 14

# --- judging defaults ---------------------------------------------------
# Target number of completed reviews per project in the official fixtures.
# Projects that already have more are left alone; missing slots become
# pending assignments so the "unfinished batch" case is visible in the UI.
TARGET_REVIEWS_PER_PROJECT = int(_env("PORTAL_TARGET_REVIEWS", "3"))

# --- demo credentials ---------------------------------------------------
# These are seeded verbatim and printed on boot, so .dogfood.toml can be
# written once and keep working. They are demo credentials for synthetic
# fixture data, not secrets.
DEMO_PASSWORD = _env("PORTAL_DEMO_PASSWORD", "dogfood-demo-2026")
FIXTURE_PASSWORD = _env("PORTAL_FIXTURE_PASSWORD", "fixture-demo-2026")

DEMO_ACCOUNTS = (
    # key,          email,                    name,                role,        session token
    ("organizer", "organizer@dogfood.test", "Mira Halvorsen", "organizer", "sess_org_3f9a21c4"),
    ("admin", "admin@dogfood.test", "Rune Adel", "admin", "sess_adm_6c02ff31"),
    ("judge_a", "tomas.varga@example.org", "Tomas Varga", "judge", "sess_jdg_a_91bc4730"),
    ("judge_b", "wei.lindqvist@example.org", "Wei Lindqvist", "judge", "sess_jdg_b_44de8a12"),
    ("participant", "priya1@example.org", "Priya Raut", "participant", "sess_prt_2e8877ab"),
)

# Extra logins that are useful when exploring the portal by hand.
#
# `organizer_b` deliberately manages no hackathon: it is the account the
# isolation tests use to prove that an organizer cannot reach an event they were
# never added to (see tests/test_event_isolation.py).
EXTRA_DEMO_ACCOUNTS = (
    ("judge_c", "priya.nair@example.org", "Priya Nair", "judge", "sess_jdg_c_12ab78fe"),
    ("participant_2", "member1_1@example.org", "Ines Falk", "participant", "sess_prt_9d4c1b02"),
    ("organizer_b", "nadia.frost@dogfood.test", "Nadia Frost", "organizer",
     "sess_org_b_7c31de84"),
)

RUBRIC_DEFAULT = (
    # key, label, description, weight, min, max
    ("functionality", "Does it work", "The thing runs, does what it claims and survives being poked at.", 0.40, 1, 5),
    ("quality", "Build quality", "Code, structure, testing, documentation, the parts nobody demos.", 0.30, 1, 5),
    ("innovation", "Idea and originality", "Is this a new answer, or a sixth wrapper around the same answer.", 0.30, 1, 5),
)
