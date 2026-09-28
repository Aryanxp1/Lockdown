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
   ├── db.init_db()            app/db.py:143     apply schema.sql (idempotent)
   ├── boot.seed()             app/boot.py:351   seed fixtures + practice event + demo logins
   └── server.serve()          app/server.py:258 ThreadingHTTPServer.serve_forever()
```

* **One process, many threads.** `ThreadingHTTPServer` with `daemon_threads`.
  One thread handles one request from socket to response. No background jobs,
  worker pools, schedulers, or cron tasks exist.
* **One SQLite connection per thread.** `db.conn()` caches the handle in
  `threading.local()`. `server.dispatch()` calls `db.release()` in a `finally:`
  block (`app/server.py:115`) so handles do not leak.
* **Serialised writes, concurrent reads.** WAL mode, `synchronous=NORMAL`,
  `foreign_keys=ON`, `busy_timeout=10000` (`app/db.py:23`). Mutations take a
  process-wide `RLock` and execute inside `BEGIN IMMEDIATE` (`app/db.py:87`,
  `app/db.py:97`). `db.tx()` nests cleanly.
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
| `app/schema.sql` | 30 SQLite tables + indexes | Applied at boot |
| `app/db.py` | SQLite connection pooling & tx helpers | `query`, `one`, `insert`, `tx` |
| `app/http.py` | `Request`, `Response`, `Problem`, `Router` | `match`, `field`, `json` |
| `app/server.py` | HTTP pipeline, static dispatch, guards | `handle_request`, guards |
| `app/routes.py` | Route declarations (31 endpoints) | `build_routes()` |
| `app/views/` | HTML view rendering & shell layout | `render_shell`, pages_* |
| `app/auth.py` | Sessions, cookies, role checks | `resolve`, `start`, `end` |
| `app/security.py` | Cryptographic primitives | `hash_password`, `sign` |
| `app/events.py` | Event lifecycles, windows, deadlines | `submission_window` |
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
7. **Handler dispatch & error mapping.** Exceptions map to structured responses: `Redirect` → `303`, `Problem` → `4xx/5xx` JSON or HTML error, unhandled → `500` + `audit_log` error event (`app/server.py:100`).
8. **Security headers.** Applied unconditionally to every response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'self'`, `Cache-Control: no-store` (`app/server.py:167`).

---

## 4. Route surface

The portal registers 31 routes in `build_routes()` (`app/routes.py:46`). Each route explicitly declares allowed roles and CSRF requirements:

| Area | Endpoints | Access |
| --- | --- | --- |
| **Public** | `GET /`<br>`GET /gallery`, `GET /projects` (alias)<br>`GET /gallery/{project_id}`<br>`GET /results` | Public |
| **Auth** | `GET /signin`, `GET /login`<br>`POST /signin` (public, CSRF bypassed)<br>`POST /signout` | Public / Authenticated |
| **Community** | `POST /gallery/{project_id}/vote`<br>`POST /gallery/{project_id}/comment` | Any role, CSRF |
| **Participant** | `GET /participant`<br>`POST /participant/team/create`<br>`GET /participant/project/new`, `GET /projects/new`<br>`POST /participant/project/new`, `POST /projects/new`<br>`GET /participant/project/edit`<br>`POST /participant/project/edit` | `participant`, `admin`<br>CSRF on POST |
| **Judge** | `GET /judge`<br>`GET /judge/assignments`<br>`GET /judge/evaluate/{project_id}`<br>`POST /judge/evaluate/{project_id}` | `judge`, `admin`<br>CSRF on POST |
| **Organizer** | `GET /organizer`<br>`GET /organizer/submissions`<br>`GET /organizer/judges`<br>`GET /organizer/audit`<br>`POST /organizer/publish` | `organizer`, `admin`<br>CSRF on POST |
| **API** | `GET /api/judge/scores`<br>`GET /api/export.csv`, `GET /organizer/export` | Authenticated / Organizer |

---

## 5. Single sources of truth

To prevent discrepancies across views, key business rules are centralized:

* **Event windows.** Deadlines and states are computed once in `app/events.py`. `submission_window()` dictates if teams can edit or submit. Both the HTML form and the POST endpoint call `_require_window()` (`app/routes.py:687`), ensuring identical behavior across UI and API.
* **Scoring engine.** `scoring.scoreboard(event)` (`app/scoring.py:317`) is the sole ranking calculator. The organizer dashboard, CSV exporter, public results page, and publication pipeline all consume this function. Rankings never diverge across pages.
* **Audit trail.** `app/audit.py:record()` logs operations synchronously in the calling transaction. A convenience wrapper `audit.refused()` records rejected actions (e.g. `access.denied`, `csrf.rejected`, `scores.refused`) and never raises an exception.

---

## 6. Views and front-end architecture

The portal uses server-side template-less string rendering:

* **Pure Python string builders.** Views in `app/views/` return HTML strings. All user-supplied input is sanitized through `util.esc()` (`app/util.py:10`).
* **Layout shell.** `render_shell()` (`app/views/layout.py:73`) wraps all pages with consistent semantic navigation, user context, flash notifications, and role-based links.
* **Content Security Policy.** Script execution is restricted by `default-src 'self'`. No inline JavaScript (`<script>...</script>`) or inline event handlers (`onclick=`) exist anywhere in the application.
* **Progressive enhancement (`app/views/static/app.js`).** Pages remain fully functional with JavaScript disabled. When active, `app.js` provides:
  * Dynamic deadline countdowns with minute precision.
  * Auto-submitting filters on gallery and submission rosters.
  * 1–5 number-row keyboard shortcuts on evaluation forms.
  * Background autosave for draft reviews via `fetch` with `X-Requested-With: Fetch`.
  * Destructive action confirmation dialogs (`data-confirm`).

---

## 7. Persistence & Docker deployment

* **Single-file storage.** All tables reside in `data/portal.sqlite3`. With WAL mode enabled, SQLite generates temporary `-wal` and `-shm` files during operation.
* **Docker container.** Runs with unprivileged `python:3.12-alpine`. The `lockdown-portal` service mounts a named Docker volume (`portal-data`) to `/data`. The service uses `PORTAL_DATA_DIR=/data` to keep database files safe across container restarts.
* **Deterministic seeding.** Seeding occurs automatically if the database has zero registered events. The bootstrapper loads `data/fixtures.json`, initializes the practice event, pre-generates demo sessions, and issues initial publications.
* **Demo session permanence.** Demo sessions are injected with an expiration timestamp of `2099-01-01T00:00:00Z` (`app/config.py:74`), allowing test suites and judges to access accounts without re-authenticating.


---

## 8. Security posture

* **Session tokens.** High-entropy 32-byte hexadecimal strings generated with `secrets.token_hex(32)`. The database only stores SHA-256 hashes of tokens (`app/auth.py:46`).
* **Cookies.** Emitted with `HttpOnly`, `SameSite=Lax`, `Path=/`, and a 30-day lifetime. Because Lockdown is designed to run over plain HTTP on LANs or loopback addresses, the `Secure` flag is omitted (`app/http.py:164`). For public networks, an external TLS-terminating reverse proxy is expected.
* **CSRF protection.** Compares session-bound tokens using `hmac.compare_digest()`. The `/signin` POST endpoint intentionally skips CSRF validation because the client has no session prior to authenticating.
* **Password hashing.** Uses standard library `hashlib.scrypt()` (16384 cost, 8 block size, 1 parallelization) with fallback to PBKDF2-SHA256 (120,000 iterations) (`app/security.py:27`).
* **Evaluation integrity.** Review scores are signed with an HMAC-SHA256 digest computed from `review_id`, `project_id`, `judge_user_id`, `weighted_raw`, and the server secret (`app/security.py:68`).
* **Path traversal prevention.** Static asset requests reject `..`, absolute paths, and backslashes before checking that the resolved path is contained in the static directory (`app/server.py:242`).

---

## 9. Verification & test suite

Verification tools included in the repository:

* `run.py`: Acceptance test suite testing login flows, CSRF, judging, score normalization, public embargo enforcement, and certificate issuance.
* `tmp/smoke.py`: End-to-end smoke verification executing complete judging lifecycles.
* `tmp/doc_facts.py`: Real-time inspector validating table schemas, row counts, and rubric configurations directly against live database volumes.

