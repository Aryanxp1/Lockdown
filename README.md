# Lockdown

A self-hosted submission and judging portal for hackathons. Python standard
library only: no package installs, no external services, no API keys, no
CDN. Your data stays in one SQLite file.

One install hosts **many hackathons**. `/events` is the public directory, each
hackathon has its own cover, gallery and results page, and organizer access is
per-event — so two competitions in the same database never see each other's
projects, scores or results.

## One command

```
docker compose up
```

That builds the image, creates the volume, seeds the database from
`fixtures.json` and serves on <http://127.0.0.1:8081>. The boot banner prints
the demo session cookies:

```
seeded. test logins:
  organizer      Cookie: session=sess_org_3f9a21c4
  judge_a        Cookie: session=sess_jdg_a_91bc4730
  judge_b        Cookie: session=sess_jdg_b_44de8a12
  participant    Cookie: session=sess_prt_2e8877ab
```

Open <http://127.0.0.1:8081/gallery> for the public gallery, browse every
hackathon in the install at <http://127.0.0.1:8081/events>, or sign in at
`/login` with a demo account (`organizer@dogfood.test`, password
`dogfood-demo-2026`; fixture accounts use `fixture-demo-2026`).

The very first build needs the `python:3.12-alpine` base image, so it needs
network access once. Nothing else is downloaded, at build time or at boot.

```
docker compose ps          # health
docker compose logs -f     # follow the portal log
docker compose down        # stop, keep the database
docker compose down -v     # stop and throw the database away
```

## Configuration

Everything has a default; override only what you need.

| Setting | Default | Meaning |
| --- | --- | --- |
| `LOCKDOWN_PORT` | `8081` | host port to publish |
| `LOCKDOWN_BIND` | `127.0.0.1` | host interface to bind (set `0.0.0.0` for LAN) |
| `PORTAL_PORT` | `8081` | port inside the container |
| `PORTAL_DATA_DIR` | `/data` | where `portal.sqlite3` lives (the `portal-data` volume) |
| `PORTAL_FIXTURES` | `/app/fixtures.json` | fixture file used to seed an empty database |
| `PORTAL_RESET` | `0` | set `1` to wipe and re-seed on boot |

`docker compose up` keeps the database in the `portal-data` named volume, so
`docker compose down` followed by `docker compose up` starts where you left
off. A name volume is used on purpose: SQLite runs in WAL mode, and WAL on a
Windows or network-mounted directory is how databases get corrupted.

Example: `LOCKDOWN_PORT=9000 docker compose up`

## Running without Docker

```
python3 -m app             # http://localhost:8081, seeds on first run
python3 -m app --reset     # wipe and re-seed
```

Same application, same port, same database directory (`./data`).

## Acceptance suite

```
python3 run.py .dogfood.toml
```

The checker talks HTTP only, so it works against a containerised portal. It
also ships inside the image, which makes it runnable without a host Python:

```
docker compose exec portal python3 run.py .dogfood.toml
```

On Windows, `python3` may be the Microsoft Store placeholder rather than an
interpreter; use `py -3 run.py .dogfood.toml` or `python run.py .dogfood.toml`
there. Inside the container (Alpine Linux) `python3` always exists.

Current status, both on the host and inside the container: `claimed T1 T2,
verified T1 T2` (see `acceptance-report.txt`).

## Offline

The portal has no outbound network calls at all: the rendered pages reference
no external assets, and `app/` never imports an HTTP client. To check that
rather than take it on faith:

```
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
docker compose -f docker-compose.yml -f docker-compose.offline.yml exec -T portal python3 run.py .dogfood.toml
docker compose -f docker-compose.yml -f docker-compose.offline.yml down
```

`docker-compose.offline.yml` puts the container on an internal network with no
gateway, so DNS and outbound TCP both fail, and the suite still passes.

## Layout

| Path | What it is |
| --- | --- |
| `app/` | the portal: `server.py` (HTTP + guards), `routes.py`, `db.py`, `schema.sql`, `seed.py`, `views/` |
| `app/eventadmin.py` | creating and reconfiguring hackathons, form validation |
| `app/migrations.py` | additive upgrades that bring an older database to schema version 2 |
| `fixtures.json` | the official fixture data, seeded on first boot |
| `run.py` | the DOGFOOD acceptance checker |
| `spec.md` | the competition brief this project is built against |
| `tests/` | `unittest` suites: event isolation and schema migrations |
| `Dockerfile`, `docker-compose.yml`, `docker-compose.offline.yml` | container build and run |
| `tmp/` | developer checks (`smoke.py`, `docker_probe.py`, `persist_check.py`); not part of the portal |
| `ARCHITECTURE.md` | System design, zero-dependency HTTP stack, guards, and lifecycle |
| `DATA-MODEL.md` | Schema of all 31 tables, foreign keys, snapshots, and seed mappings |
| `JUDGING.md` | Rubric weighting, cross-judge z-score normalization, and worked examples |

## Demo credentials

All demo accounts use the standard password `dogfood-demo-2026`:

| Role | Email | Session Cookie |
| --- | --- | --- |
| **Admin** | `admin@dogfood.test` | `Cookie: session=demo:admin` |
| **Organizer** | `organizer@dogfood.test` | `Cookie: session=demo:organizer` |
| **Judge A** | `judge_a@dogfood.test` | `Cookie: session=demo:judge_a` |
| **Judge B** | `judge_b@dogfood.test` | `Cookie: session=demo:judge_b` |
| **Judge C** | `judge_c@dogfood.test` | `Cookie: session=demo:judge_c` |
| **Participant** | `participant@dogfood.test` | `Cookie: session=demo:participant` |
| **Participant 2**| `participant_2@dogfood.test` | `Cookie: session=demo:participant_2` |

Fixture accounts (e.g. `judge01@example.com` through `judge30@example.com` or team contacts) use password `fixture-demo-2026`.

Demo sessions are pre-seeded with expiration timestamps set to `2099-01-01T00:00:00Z` to simplify offline testing and verification.

## Seeding & persistence

* **Idempotent Boot:** On initial startup, if the database contains no events, `app/boot.py` seeds `fixtures.json` (the 41-project official fixture), creates the `evt_01` Sample Hack 2026 event, the `evt_practice` Autumn Practice Sprint sandbox and the `evt_zero_dep` Zero Dependency 2026 demo event, records event ownership in `event_organizers`, establishes duplicate tracking (`prj_41` superseding `prj_07`), and signs evaluations. On subsequent boots, existing data is preserved untouched.
* **Migrations, not rewrites:** `app/schema.sql` describes a new database and `app/migrations.py` upgrades an existing one. Event scoping is schema version 2: new defaulted columns are added with `ALTER TABLE ... ADD COLUMN` and `event_organizers` is created with `IF NOT EXISTS`, so a database from the single-event era keeps every project, review and publication and simply gains the new fields. Running it twice changes nothing.
* **Storage & WAL Mode:** The database resides in `data/portal.sqlite3`. With SQLite WAL (Write-Ahead Logging) mode enabled, concurrent reads execute without blocking writes.
* **Volume Persistence:** When running under Docker, the `portal-data` named volume ensures all submissions, reviews, and audit logs persist across container restarts.

## Event directory & isolation

| Route | What it shows |
| --- | --- |
| `GET /events` | every published hackathon in the install, each with its own cover |
| `GET /events/{slug}` | one hackathon's cover page: schedule, tracks, prizes count |
| `GET /events/{slug}/gallery` | that hackathon's projects only |
| `GET /events/{slug}/results` | that hackathon's published standings only |

Organizers work one hackathon at a time. `GET /organizer` is the shelf of events
the caller belongs to, and every `/organizer/events/{event_id}/...` route re-checks
`event_organizers` membership through `events.can_manage()` before it reads or writes
a row. An organizer of one event cannot open, mutate or borrow row ids from another.
`events.gallery_visible` / `events.results_visible` hide a hackathon's public pages
without deleting anything, and draft events never appear in the directory.

## Verification & testing

Both Tier 1 (T1) and Tier 2 (T2) requirements are verified:

```bash
# Run acceptance checker against running container
docker compose exec portal python3 run.py .dogfood.toml

# Or run locally against http://127.0.0.1:8081
python run.py .dogfood.toml
```

Multi-hackathon behavior has its own suites, which need no running server:

```bash
python -m unittest discover -s tests
```

## Known limitations

* **Offline Webhooks:** The `webhooks` and `webhook_deliveries` tables exist in the schema, but background dispatch is deliberately disabled to satisfy the strict offline zero-outbound-network constraint.
* **Rate Limiting:** The `rate_limits` table is defined, but request throttling middleware is currently inactive.
* **Cookie Flags:** Session cookies set `HttpOnly` and `SameSite=Lax`, but omit `Secure` to support running out-of-the-box over plain HTTP on LAN or loopback environments without requiring self-signed TLS certificates.
* **Pairwise Ranking:** The Bradley-Terry algorithm is implemented in `app/scoring.py` and comparison records are seeded, but official event rankings are computed strictly via rubric z-score normalization.
* **Event lifecycle, not deletion:** Hackathons move through `draft` → `published` → `archived`; there is deliberately no hard delete. Archiving removes an event from the public directory while leaving its projects, reviews and publications intact, and only the event's own tracks, prizes, stages and membership rows can be edited or removed.

