# Lockdown — architecture

Lockdown is a self-hosted submission and judging portal for hackathons. It is
one Python process, one SQLite file and the standard library. This document
describes how the code in `app/` is put together: what runs, in what order, and
where each rule lives.

Everything here reflects the actual codebase. Where the implementation stops
short of a feature, [README.md](README.md#known-limitations) documents the gap.

---

## 1. Non-negotiables

Three constraints shape every other decision:

| Constraint | What it means in the code |
| --- | --- |
| **No third-party dependencies** | `app/` imports only standard library (`http.server`, `sqlite3`, `hashlib`, `hmac`, `secrets`, `urllib.parse`, `json`, `re`, `math`, `datetime`, `threading`). There is no `requirements.txt` and the Docker build installs nothing. |
| **No outbound network** | No client connection is ever opened. No CDN, font host, analytics, or telemetry. Pages reference only local `/static/app.css` and `/static/app.js`. Webhook rows exist but no daemon delivers them. |
| **No external state** | All state lives in `data/portal.sqlite3` (+ WAL/SHM). No Redis, memcached, message queue, or S3. |

---

## 2. Runtime shape

```
python -m app
   │
   ├── db.init_db()            app/db.py:143     apply schema.sql, then migrations.migrate()
   ├── boot.seed()             app/boot.py:674   seed fixtures + practice + demo events + logins
   └── server.serve()          app/server.py:260 ThreadingHTTPServer.serve_forever()
```

`db.init_db()` always runs `app/schema.sql` first and `migrations.migrate()` second
(`app/db.py:154`). `schema.sql` describes a *new* database; the migration pass brings
an *existing* one forward. Both are idempotent, so boot order never matters.

* **One process, many threads.** `ThreadingHTTPServer` with `daemon_threads`.
  One thread handles one request from socket to response. No background jobs,
  worker pools, schedulers, or cron tasks exist.
* **One SQLite connection per thread.** `db.conn()` caches the handle in
  `threading.local()`. `server.dispatch()` calls `db.release()` in a `finally:`
  block (`app/server.py:116`) so handles do not leak.
* **Serialised writes, concurrent reads.** WAL mode, `synchronous=NORMAL`,
  `foreign_keys=ON`, `busy_timeout=10000` (`app/db.py:32`). Mutations take a
  process-wide `RLock` and execute inside `BEGIN IMMEDIATE` (`app/db.py:87`,
  `app/db.py:110`). `db.tx()` nests cleanly (`app/db.py:98`).
* **Single write path.** `db.insert`, `db.update`, `db.execute` always pass
  parameter tuples, never interpolated strings (`app/db.py:123`).
* **Startup is the only batch run.** `python -m app` seeds automatically when
  the database has no events; `--seed-only` exits after seed; `--reset` wipes
  first.

### Module map

| Module | Responsibility | Key entry points |
| --- | --- | --- |
| `app/__main__.py` | CLI parsing, startup coordination | `main()` |
| `app/config.py` | Environment configuration & defaults | `HOST`, `PORT`, `DATA_DIR`, … |
| `app/schema.sql` | 31 SQLite tables + indexes (schema version 2) | Applied at boot |
| `app/db.py` | SQLite connection pooling & tx helpers | `query`, `one`, `insert`, `tx` |
| `app/migrations.py` | Additive, idempotent upgrades for older databases | `migrate`, `SCHEMA_VERSION` |
| `app/http.py` | `Request`, `Response`, `Problem`, `Router` | `match`, `field`, `json` |
| `app/server.py` | HTTP pipeline, static dispatch, guards | `handle_request`, guards |
| `app/routes.py` | Route declarations (56 endpoints) | `build_routes()` |
| `app/views/` | HTML view rendering & shell layout | `render_shell`, pages_* |
| `app/views/pages_events.py` | Public event directory, event cover page, per-event gallery & results | `event_directory`, `event_page` |
| `app/views/pages_manage.py` | The shelf of hackathons and one event's management desk | `manage_home`, `event_overview` |
| `app/auth.py` | Sessions, cookies, role checks | `resolve`, `start`, `end` |
| `app/security.py` | Cryptographic primitives | `hash_password`, `sign` |
| `app/events.py` | Event lifecycles, windows, deadlines, **membership** | `submission_window`, `can_manage` |
| `app/eventadmin.py` | Creating and configuring hackathons, validating forms | `validate`, `create`, `update` |
| `app/scoring.py` | Rubrics, z-scores, rollups | `scoreboard`, `normalize` |
| `app/results.py` | Publications, certificates, advancements | `publish`, `issue_certificates` |
| `app/seed.py` | Fixture transformations | `seed_*`, `plan_assignments` |
| `app/boot.py` | Seeding orchestration & demo sessions | `seed`, `wipe` |
| `app/audit.py` | Append-only audit logger | `record`, `refused` |
| `app/timeutil.py` | UTC ISO-8601 lexicographical dates | `now_iso`, `parse` |
| `app/util.py` | Identifier generators & helpers | `new_id`, `slugify` |


---

## 3. The request path

`PortalHandler.handle_request()` (`app/server.py:139`) executes the request lifecycle:

1. **Body cap.** Reads up to `MAX_BODY` (2 MiB, `app/server.py:23`). Payloads exceeding this receive `413 Payload Too Large`.
2. **Static file shortcut.** `/static/` is handled directly (`app/server.py:142`) before routing. Paths are sanitized against directory traversal (`..`, `/`, `\`), mapped to MIME types, and cached via `Cache-Control: public, max-age=300`.
3. **Route matching.** `Router.match()` returns the matching handler. Path matches with incorrect HTTP methods return `405 Method Not Allowed` with an `Allow` header (`app/http.py:330`). Unmatched paths return `404 Not Found`.
4. **Session resolution.** `auth.resolve()` reads `session` cookie or bearer header, hashes token with SHA-256, looks up non-revoked session, loads user record, and bumps `last_seen_at` (`app/auth.py:78`).
5. **Role guards.** If route defines `roles=`, `auth.role_allows()` verifies membership (`app/server.py:194`). Unauthenticated web requests redirect to `/login?next=…`; API requests return `401 Unauthorized`. Refusals log to `audit_log` as `access.denied`.
6. **CSRF enforcement.** State-changing verbs on routes with `csrf=True` require valid token via `X-CSRF-Token`, `_csrf`, or `csrf_token` fields (`app/server.py:215`). Tokens are compared constant-time. Failures return `403 csrf_failed` and audit as `csrf.rejected`.
7. **Handler dispatch & error mapping.** Exceptions map to structured responses: `Redirect` → `303`, `Problem` → `4xx/5xx` JSON or HTML error, unhandled → `500` + `audit_log` error event (`app/server.py:102`).
8. **Security headers.** Applied unconditionally to every response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'self'`, `Cache-Control: no-store` (`app/server.py:167`).

---

## 4. Route surface

The portal registers 56 routes in `build_routes()` (`app/routes.py:59`) — 36 GET and
20 POST. Each route explicitly declares allowed roles and CSRF requirements:

| Area | Endpoints | Access |
| --- | --- | --- |
| **Public** | `GET /`<br>`GET /gallery`, `GET /projects` (alias)<br>`GET /gallery/{project_id}`<br>`GET /results` | Public |
| **Event directory** | `GET /events`<br>`GET /events/{slug}`<br>`GET /events/{slug}/gallery`<br>`GET /events/{slug}/results` | Public |
| **Auth** | `GET /signin`, `GET /login`<br>`POST /signin` (public, CSRF bypassed)<br>`POST /signout` | Public / Authenticated |
| **Community** | `POST /gallery/{project_id}/vote`<br>`POST /gallery/{project_id}/comment` | Any role, CSRF |
| **Participant** | `GET /participant`<br>`POST /participant/team/create`<br>`GET /participant/project/new`, `GET /projects/new`<br>`POST /participant/project/new`, `POST /projects/new`<br>`GET /participant/project/edit`<br>`POST /participant/project/edit` | `participant`, `admin`<br>CSRF on POST |
| **Judge** | `GET /judge`<br>`GET /judge/assignments`<br>`GET /judge/evaluate/{project_id}`<br>`POST /judge/evaluate/{project_id}` | `judge`, `admin`<br>CSRF on POST |
| **Organizer — shelf** | `GET /organizer`<br>`GET\|POST /organizer/events/new`<br>`GET /organizer/submissions`<br>`GET /organizer/judges`<br>`GET /organizer/audit`<br>`POST /organizer/publish`<br>`GET /organizer/export` | `organizer`, `admin`<br>CSRF on POST |
| **Organizer — one event** | `GET /organizer/events/{event_id}`<br>`GET\|POST /organizer/events/{event_id}/stages`<br>`POST /organizer/events/{event_id}/stages/remove`<br>`GET /organizer/events/{event_id}/teams`<br>`GET /organizer/events/{event_id}/submissions`<br>`GET\|POST /organizer/events/{event_id}/judges`<br>`GET\|POST /organizer/events/{event_id}/assignments`<br>`POST /organizer/events/{event_id}/assignments/revoke`<br>`GET /organizer/events/{event_id}/reviews`<br>`GET\|POST /organizer/events/{event_id}/results`<br>`GET /organizer/events/{event_id}/audit`<br>`GET\|POST /organizer/events/{event_id}/settings`<br>`POST /organizer/events/{event_id}/organizers`<br>`POST /organizer/events/{event_id}/organizers/remove` | `organizer`, `admin`<br>CSRF on POST<br>**plus** `events.can_manage` |
| **API** | `GET /api/judge/scores`<br>`GET /api/export.csv`, `GET /organizer/export` | Authenticated / Organizer |

Every route matching `/organizer/events/{event_id}/...` resolves the event and calls
`events.can_manage()` before touching a row; the URL alone grants nothing.

---

## 5. Single sources of truth

To prevent discrepancies across views, key business rules are centralized:

* **Event windows.** Deadlines and states are computed once in `app/events.py`. `submission_window()` dictates if teams can edit or submit. Both the HTML form and the POST endpoint call `_require_window()` (`app/routes.py:239`), ensuring identical behavior across UI and API.
* **Scoring engine.** `scoring.scoreboard(event)` (`app/scoring.py:288`) is the sole ranking calculator, and it is scoped to one event. The organizer dashboard, CSV exporter, public results page, and publication pipeline all consume this function. Rankings never diverge across pages, and two hackathons in the same database can never influence each other's standings.
* **Audit trail.** `app/audit.py:record()` logs operations synchronously in the calling transaction. A convenience wrapper `audit.refused()` records rejected actions (e.g. `access.denied`, `csrf.rejected`, `scores.refused`) and never raises an exception.

---

## 6. Views and front-end architecture

The portal uses server-side template-less string rendering:

* **Pure Python string builders.** Views in `app/views/` return HTML strings. All user-supplied input is sanitized through `views.ui.esc()` (`app/views/ui.py:12`), which routes to `html.escape(..., quote=True)`.
* **Layout shell.** `render_shell()` (`app/views/layout.py:10`) wraps all pages with consistent semantic navigation, user context, flash notifications, and role-based links.
* **Content Security Policy.** Script execution is restricted by `default-src 'self'`. No inline JavaScript (`<script>...</script>`) or inline event handlers (`onclick=`) exist anywhere in the application.
* **Progressive enhancement (`app/views/static/app.js`).** Pages remain fully functional with JavaScript disabled. When active, `app.js` provides:
  * Dynamic deadline countdowns with minute precision.
  * Auto-submitting filters on gallery and submission rosters.
  * 1–5 number-row keyboard shortcuts on evaluation forms.
  * Background autosave for draft reviews via `fetch` with `X-Requested-With: Fetch`.
  * Destructive action confirmation dialogs (`data-confirm`).

---

## 7. Multi-hackathon & event isolation

One install is a **shelf of hackathons**, not a single competition. Three seeded
events share one database:

| Event | id | slug | Contents |
| --- | --- | --- | --- |
| Sample Hack 2026 | `evt_01` | `sample-hack-2026` | The full fixture: 41 projects, 40 teams, 126 reviews, published results |
| Autumn Practice Sprint | `evt_practice` | `autumn-practice-sprint` | Small sandbox event for trying flows |
| Zero Dependency 2026 | `evt_zero_dep` | `zero-dependency-2026` | Second demo event: own tracks, prizes and rubric |

### How a row belongs to an event

Ownership is explicit, never inferred. `events.id` is the scope key and is carried
as an `event_id` foreign key on every table that describes a competition:
`event_stages`, `tracks`, `prizes`, `teams`, `projects`, `assignments`, `reviews`,
`rubrics`, `advancements`, plus `event_organizers` (the membership table).
`review_scores` and `team_members` reach their event through their parent row and
therefore have no column of their own.

### Membership decides access

Role alone is no longer sufficient. `event_organizers` maps `(event_id, user_id)`
with a role of `owner` or `organizer`, and `events.can_manage()` (`app/events.py:104`)
is the single check every organizer route makes. `events.manageable_events()`
(`app/events.py:115`) backs the shelf on `GET /organizer`, so an organizer sees
exactly the hackathons they belong to. `events.member_role()` distinguishes the two
tiers, and `eventadmin` writes the membership row inside the same transaction that
creates the event, so a hackathon is never ownerless.

### Visibility is a switch, not a deletion

`events.gallery_visible` and `events.results_visible` hide a hackathon's public
surfaces without destroying anything. `events.gallery_is_visible()` and
`events.results_are_visible()` (`app/events.py:184`, `app/events.py:189`) gate the
public pages; organizers keep full access through the management desk. Draft events
are excluded from the public directory by `events.visible_events()`
(`app/events.py:137`).

### Migration strategy

Event scoping was added to a database that already held live data, so it ships as a
migration rather than a rewrite (`app/migrations.py`, `SCHEMA_VERSION = 2`):

* **Additive only.** `ADDED_COLUMNS` lists each new defaulted column; the pass runs
  `ALTER TABLE ... ADD COLUMN` only when `PRAGMA table_info` says it is missing.
  `EXTRA_STATEMENTS` creates `event_organizers` and the new indexes with
  `IF NOT EXISTS`.
* **No invented data.** A table that is absent is skipped, not recreated — a
  stripped-down database is upgraded, never fabricated.
* **Existing rows are re-homed.** Every pre-migration project, team and review
  belongs to Sample Hack 2026, so the fixture's rows keep working untouched.
* **Idempotent.** Running it twice changes nothing, and `schema.sql` already
  describes version 2, so a brand new database needs no migration at all.
* **Loud on damage.** A missing *indexed* table raises rather than limping on,
  because `schema.sql` runs first on every boot and its absence is a real fault.

`tests/test_event_isolation.py` proves the boundary (a draft event is invisible,
public pages never mix two hackathons, an outsider cannot borrow row ids from
another event, every refusal lands in `audit_log`); `tests/test_migrations.py`
proves the upgrade path.

---

## 8. Persistence & Docker deployment

* **Single-file storage.** All tables reside in `data/portal.sqlite3`. With WAL mode enabled, SQLite generates temporary `-wal` and `-shm` files during operation.
* **Docker container.** Runs with unprivileged `python:3.12-alpine`. The `lockdown-portal` service mounts a named Docker volume (`portal-data`) to `/data`. The service uses `PORTAL_DATA_DIR=/data` to keep database files safe across container restarts.
* **Deterministic seeding.** Seeding occurs automatically if the database has zero registered events. The bootstrapper loads `fixtures.json`, initializes the practice event and the Zero Dependency 2026 demo event, pre-generates demo sessions, records event ownership, and issues initial publications.
* **Demo session permanence.** Demo sessions are injected with an expiration timestamp of `2099-01-01T00:00:00Z` (`app/config.py:74`), allowing test suites and judges to access accounts without re-authenticating.


---

## 9. Security posture

* **Session tokens.** High-entropy 32-byte hexadecimal strings generated with `secrets.token_hex(32)`. The database only stores SHA-256 hashes of tokens (`app/auth.py:46`).
* **Cookies.** Emitted with `HttpOnly`, `SameSite=Lax`, `Path=/`, and a 30-day lifetime. Because Lockdown is designed to run over plain HTTP on LANs or loopback addresses, the `Secure` flag is omitted (`app/http.py:164`). For public networks, an external TLS-terminating reverse proxy is expected.
* **CSRF protection.** Compares session-bound tokens using `hmac.compare_digest()`. The `/signin` POST endpoint intentionally skips CSRF validation because the client has no session prior to authenticating.
* **Password hashing.** Uses standard library `hashlib.scrypt()` (16384 cost, 8 block size, 1 parallelization) with fallback to PBKDF2-SHA256 (120,000 iterations) (`app/security.py:27`).
* **Evaluation integrity.** Review scores are signed with an HMAC-SHA256 digest computed from `review_id`, `project_id`, `judge_user_id`, `weighted_raw`, and the server secret (`app/security.py:68`).
* **Cross-event authorisation.** A role guard alone is not enough to reach another tenant's data, so `events.can_manage()` re-checks membership on every event-scoped read and write. Row ids in URLs are therefore not a capability.
* **Path traversal prevention.** Static asset requests reject `..`, absolute paths, and backslashes before checking that the resolved path is contained in the static directory (`app/server.py:242`).

---

## 10. Verification & test suite

Verification tools included in the repository:

* `run.py`: Acceptance test suite testing login flows, CSRF, judging, score normalization, public embargo enforcement, and certificate issuance.
* `tmp/smoke.py`: End-to-end smoke verification executing complete judging lifecycles.
* `tmp/doc_facts.py`: Real-time inspector validating table schemas, row counts, and rubric configurations directly against live database volumes.
* `tests/test_event_isolation.py`: Multi-hackathon boundary — draft visibility, per-event public pages, cross-event write refusal, audit coverage (unittest).
* `tests/test_migrations.py`: The version 1 → 2 upgrade path, idempotency, and "never invent a missing table" (unittest).

