# Lockdown — operations manual

How to run Lockdown for real: configuration, seeding, persistence, backups,
upgrades, resets, TLS termination and troubleshooting. Every default in this
document is the value in [`app/config.py`](app/config.py) or the commit-time
[`docker-compose.yml`](docker-compose.yml).

**The short version:** one container, one writable volume, one SQLite file, no
external services. `docker compose up -d` is a complete deployment, and the only
state worth protecting is the volume.

---

## 1. Deployment shapes

| Shape | Command | Notes |
| --- | --- | --- |
| **Laptop demo, Docker** | `docker compose up` | Binds `127.0.0.1:8081`, seeds on first boot, prints demo cookies. The default. |
| **Laptop demo, no container** | `python -m app` | Needs Python 3.12 only. Data lands in `./data`. |
| **LAN demo** | `LOCKDOWN_BIND=0.0.0.0 docker compose up -d` | Reachable from other machines. Plain HTTP: see §8 before doing this on an untrusted network. |
| **Air-gapped proof** | `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d` | No gateway, no DNS, no published port; reached with `docker compose exec`. |
| **Behind a reverse proxy** | §8 | Keep the portal on loopback and let the proxy hold the certificate. |

`docker compose ps` is the health view: the image defines a `HEALTHCHECK` that
probes `GET /gallery` every 15 s (5 s timeout, 30 s start period, 4 retries), so
`healthy` means the socket, the router, the seeded database and the template
layer are all alive. `restart: unless-stopped` means the container comes back
after a host reboot.

---

## 2. Configuration reference

Nothing is required. Every value below has a working default, so the same image
runs on a laptop, in Compose and in an isolated test box.

### 2.1 Portal process

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORTAL_HOST` | `0.0.0.0` | Interface to bind. Inside a container `0.0.0.0` is correct; the published port is what limits exposure. |
| `PORTAL_PORT` | `8081` | Port to serve on. |
| `PORTAL_BASE_URL` | `http://localhost:$PORTAL_PORT` | Absolute base URL used in printed links and boot messages. |
| `PORTAL_PRIMARY_EVENT` | `sample-hack-2026` | Which hackathon the unqualified public pages (`/`, `/gallery`, `/results`) show. |

### 2.2 Storage

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORTAL_DATA_DIR` | `./data` locally, `/data` in the image | Directory holding `portal.sqlite3`. Created on demand. |
| `PORTAL_FIXTURES` | `./fixtures.json`, `/app/fixtures.json` in the image | Fixture file used when seeding an empty database. |
| `PORTAL_SEED` | `1` | Seed automatically when the database has no events. |
| `PORTAL_RESET` | `0` | Set `1` to wipe and re-seed on boot. Destructive; see §6. |

### 2.3 Sessions, crypto and judging

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORTAL_SESSION_DAYS` | `30` | Session lifetime; also the cookie `Max-Age`. |
| `PORTAL_PBKDF2_ITERATIONS` | `120000` | Cost of the PBKDF2 fallback when scrypt is unavailable. |
| `PORTAL_TARGET_REVIEWS` | `3` | Target completed reviews per project; affects which assignments are generated. |
| `PORTAL_FAST_LOGIN` | `0` | One-click demo sign-in. **Off** unless an operator opts in; see §8. |
| `PORTAL_DEMO_PASSWORD` | `dogfood-demo-2026` | Password seeded for the demo accounts. |
| `PORTAL_FIXTURE_PASSWORD` | `fixture-demo-2026` | Password seeded for fixture accounts (`judge01@example.com` … and team contacts). |

Set the two password variables **before the first boot** if you want different
ones; seeding writes the hashes once and later changes to the variables do not
rewrite existing rows.

### 2.4 Compose-only variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOCKDOWN_PORT` | `8081` | Host port published by Compose (and passed to the container). |
| `LOCKDOWN_BIND` | `127.0.0.1` | Host interface Compose binds. Set `0.0.0.0` to expose on the LAN. |

```bash
LOCKDOWN_PORT=9000 LOCKDOWN_BIND=0.0.0.0 docker compose up -d
```

### 2.5 Command-line flags

`python -m app` accepts flags that override the environment:

| Flag | Effect |
| --- | --- |
| `--host <addr>` / `--port <n>` | Override `PORTAL_HOST` / `PORTAL_PORT` |
| `--reset` | Wipe and re-seed, then serve |
| `--seed-only` | Seed, print the summary, exit without binding a port (used for fixture inspection) |
| `--quiet` | Do not print the login banner |

The container's `CMD` is `python -m app` with no flags, so Compose behaviour is
driven entirely by environment variables.

---

## 3. First boot and seeding

Seeding is deterministic and happens exactly once per empty database:

1. `db.init_db()` applies `app/schema.sql`, then runs `migrations.migrate()` and
   reports anything it had to bring forward.
2. `boot.seed()` runs when the database contains **zero events**, loading
   `fixtures.json`, the Autumn Practice Sprint, the Zero Dependency 2026 demo
   event and the deterministic demo sessions.
3. The boot banner prints the demo logins and session cookies, which is where the
   values in [`.dogfood.toml`](.dogfood.toml) come from.

```
[boot] seeded in 1.4s from /app/fixtures.json        # example output; the seconds vary
lockdown portal listening on 0.0.0.0:8081
```

On every later boot the portal says so and changes nothing:

```
[boot] database already seeded (already seeded). Use --reset to rebuild.
```

A fresh seed produces roughly 0.75 MB of database with 3 hackathons, 48 projects
and 129 evaluations. Seeding is idempotent, so it is safe to start the container
twice with the same volume.

---

## 4. Storage, persistence and the volume

Everything the portal knows lives in one SQLite database plus its journal files.

| Path (container) | Path (local run) | What it is |
| --- | --- | --- |
| `/data/portal.sqlite3` | `./data/portal.sqlite3` | Every table and every row |
| `/data/portal.sqlite3-wal` | `./data/portal.sqlite3-wal` | Write-ahead log; exists while the portal runs |
| `/data/portal.sqlite3-shm` | `./data/portal.sqlite3-shm` | Shared-memory index for the WAL |

The database is opened with `journal_mode=WAL`, `synchronous=NORMAL`,
`foreign_keys=ON` and `busy_timeout=10000` on every connection (`app/db.py:32`).
WAL gives concurrent readers alongside a single serialised writer, and that is the
whole concurrency model: one process, one thread per request, writes taken under a
process-wide lock inside `BEGIN IMMEDIATE`.

### 4.1 Why a named volume, not a bind mount

`docker-compose.yml` mounts the named volume `portal-data` at `/data`. The comment
in that file states the reason, and it is worth repeating: SQLite in WAL mode on a
**Windows- or network-mounted directory** (OneDrive, SMB, a shared folder) is a
well-known way to corrupt a database, because the WAL protocol assumes the file
system gives it the locking and `fsync` semantics it asks for. Keep the database
on a real volume, or on a local ext4/APFS filesystem for a host run.

The service is also deliberately constrained:

```yaml
read_only: true          # nothing outside /data and /tmp is writable
tmpfs: [/tmp]
cap_drop: [ALL]
security_opt: [no-new-privileges:true]
init: true
user: portal:portal      # unprivileged, created in the Dockerfile
```

If `PORTAL_DATA_DIR` is pointed outside `/data` on this configuration, the portal
will fail to create its database. That is the read-only root filesystem doing its
job, not a bug.

### 4.2 What is in the volume

The volume holds the competition data **and** the install secret
(`settings.portal_secret`). Anyone who can read that file can verify *and forge*
review signatures and recompute certificate codes, so the volume is the sensitive
artifact of the whole install. See [SECURITY.md](SECURITY.md) §9.

---

## 5. Backup and restore

There is no bespoke backup command. Use SQLite's own online-backup API inside the
running container and then copy the file out: that produces one transactionally
consistent file with no WAL companion to worry about.

### 5.1 Online backup (recommended)

```bash
# 1. ask SQLite for a consistent copy, written by the portal user into /data
docker compose exec -T portal python3 -c "import sqlite3; s=sqlite3.connect('/data/portal.sqlite3'); d=sqlite3.connect('/data/portal-backup.sqlite3'); s.backup(d); d.close(); s.close()"

# 2. pull it out of the container (Windows: use a real path, e.g. .\backups\)
docker compose cp portal:/data/portal-backup.sqlite3 ./backups/portal-$(date +%F).sqlite3

# 3. tidy up inside the container
docker compose exec portal rm -f /data/portal-backup.sqlite3
```

Verify the copy without starting anything:

```bash
python -c "import sqlite3; print(sqlite3.connect('backups/portal-2026-09-29.sqlite3').execute('PRAGMA integrity_check').fetchone())"
```

### 5.2 Cold copy (when the portal is stopped)

```bash
docker compose stop
docker compose cp portal:/data/portal.sqlite3 ./backups/portal.sqlite3
# copy the journal files as well if they exist: a WAL that has not been
# checkpointed holds committed transactions the main file does not contain yet
docker compose cp portal:/data/portal.sqlite3-wal ./backups/portal.sqlite3-wal  # if present
docker compose cp portal:/data/portal.sqlite3-shm ./backups/portal.sqlite3-shm  # if present
docker compose start
```

A copy missing a non-empty `-wal` file is an **older** database than the one being
served. §5.1 avoids the whole question.

### 5.3 Restore

```bash
# 1. stop the portal
docker compose stop

# 2. put the backup in place
docker compose cp ./backups/portal-2026-09-29.sqlite3 portal:/data/portal.sqlite3

# 3. delete any stale journal files BEFORE the portal opens the database again:
#    a -wal written against the previous main file must never be paired with a
#    replaced one
docker compose run --rm --entrypoint sh portal -c \
  "rm -f /data/portal.sqlite3-wal /data/portal.sqlite3-shm"

# 4. start
docker compose up -d
```

Then confirm: `docker compose ps` reaches `healthy`, `/gallery` lists projects, and
`/results` shows the same standings that were published when the backup was taken.

### 5.4 What to keep

| To keep | Frequency | Why |
| --- | --- | --- |
| A database copy | Before any upgrade, reset or bulk edit; otherwise daily during a live event | It is the competition |
| `acceptance-report.txt` | Whenever it is regenerated | The committed evidence for the claimed tiers |
| `fixtures.json` | It is in git | Seeding an empty database reproduces the demo install |
| The volume itself | Do not share it | It contains the signing secret |

---

## 6. Resets, and exactly what they destroy

| Action | Competition rows | `settings` (and the secret) | Audit ledger | Volume |
| --- | --- | --- | --- | --- |
| `python -m app --reset` / `PORTAL_RESET=1` | Deleted, then re-seeded from `fixtures.json` | Kept | **Deleted** | Same volume, new data |
| `docker compose down` | Kept | Kept | Kept | Kept |
| `docker compose down -v` | Gone | Gone | Gone | **Deleted** |
| Deleting `data/portal.sqlite3` by hand | Gone | Gone | Gone | n/a |

`--reset` calls `boot.wipe()`, which deletes the contents of 29 tables
(`WIPE_TABLES`, `app/boot.py:635`) and leaves `settings` alone, so the install
secret — and with it the ability to verify signatures — survives a reseed. There
is no undo: the audit ledger is one of the tables it empties, so a reset ends that
install's evidence trail.

`docker compose down -v` is the clean-slate option. The next boot creates a brand
new database **and a new secret**, which means certificates and review receipts
issued by the old install can no longer be verified. For a repeatable demo
install, prefer `--reset` over deleting the volume.

---

## 7. Upgrades

Upgrading means replacing the code (or the image) and keeping the volume:

```bash
git pull                       # or build the new image
docker compose build
docker compose up -d
docker compose logs portal | head -20
```

Schema handling is designed so that this is safe:

* `app/schema.sql` describes a **new** database; `app/migrations.py` upgrades an
  **existing** one. `db.init_db()` runs the script and then the migration pass on
  every boot, so boot order never matters (`app/db.py:154`).
* Migrations are additive and idempotent: defaulted columns arrive through
  `ALTER TABLE … ADD COLUMN` only when absent, and tables or indexes are created
  with `IF NOT EXISTS`.
* A table missing from an old database is **skipped, not invented** — the upgrade
  never fabricates data.
* A missing *indexed* table raises loudly, because `schema.sql` runs first on every
  boot and its absence is a real fault.

When a migration runs, the boot log says so:

```
[boot] schema migrated 1 -> 2 (event_id, status)
[boot] ensured: judge_invitations
```

Downgrades are not supported. To roll back, restore the pre-upgrade backup (§5.3)
and run the older code against it.

---

## 8. TLS, reverse proxies and exposure

The portal speaks plain HTTP and sets no `Secure` cookie flag. That is a
deliberate default for loopback and LAN demos, and it means the transport is
**not** protected. For anything else:

1. Keep the portal on loopback: `LOCKDOWN_BIND=127.0.0.1` (the default).
2. Terminate TLS in a proxy (Caddy, nginx, Traefik, a cloud load balancer) and
   forward to `http://127.0.0.1:8081`.
3. Set `PORTAL_BASE_URL` to the external URL if the portal's own printed links
   need to match it.

Two behaviours to plan around:

* **`X-Forwarded-For` is not read.** `request.client_ip` is the socket peer, so
  behind a proxy the `ip` recorded in sessions and audit rows is the proxy's
  address. [SECURITY.md](SECURITY.md) §10 states this rather than pretending the
  original client is known.
* **No path-prefix support.** The application generates absolute paths
  (`/static/…`, `/login`, `/gallery`) and does not read `X-Forwarded-Prefix`, so
  mount it at the root of a hostname, not under `/portal/`.

`PORTAL_FAST_LOGIN` belongs in this section because it is an exposure decision: it
makes `GET|POST /fast-login` mint a session for a seeded fixture account with no
password and no CSRF token. It is off unless an operator sets it, and the header
link that advertises it only renders when the flag is on. Use it on a demo box,
nowhere else.

---

## 9. Logs and observability

| Source | What you get |
| --- | --- |
| Container stdout | Boot banner (demo logins, seed summary), the migration report, the `listening on …` line |
| Container stderr | Tracebacks for unexpected exceptions, prefixed `[http]` by `log_error()` |
| `docker compose logs -f` | Both streams, live |
| `audit_log` | The real record of what happened: sign-ins, refusals, assignments, scores, publications, exports. `GET /organizer/events/{event_id}/audit` paginates one hackathon's slice |
| `docker compose ps` | Health, from the `/gallery` probe |

**There is no access log.** `PortalHandler.log_message()` returns immediately
(`app/server.py:161`), so the portal does not write one line per request. The audit
ledger is the observability surface instead: structured, queryable, per event — not
a wall of request lines. Count what happened:

```bash
docker compose exec portal python3 -c "import sqlite3; print(sqlite3.connect('/data/portal.sqlite3').execute('SELECT action, COUNT(*) FROM audit_log GROUP BY action ORDER BY 2 DESC').fetchall())"
```

There is no log rotation, no metrics endpoint and no alerting: nothing runs in the
background and nothing sends anything anywhere. Retention is the size of
`audit_log`. Trimming it is a deliberate manual decision, because deleting audit
rows destroys evidence.

---

## 10. Capacity and concurrency

| Property | Value |
| --- | --- |
| Processes | 1 (`python -m app`), plus threads per request |
| External services | 0 — no database server, queue, cache or object store |
| Database size, fresh seed | ≈ 0.75 MB (3 hackathons, 48 projects, 129 evaluations) |
| Storage growth | Dominated by `audit_log`, `review_scores` and `project_versions`; text rows, so growth is linear and slow |
| Writer model | One writer at a time, under a process lock, inside `BEGIN IMMEDIATE` |
| Reader model | Concurrent reads under WAL |
| Lock wait | `busy_timeout=10000` — a blocked write waits up to 10 s before failing |
| Body limit | 2 MiB per request (`413` above it) |
| Background work | None: no scheduler, cron, queue consumer or webhook sender exists |

In practice the portal is I/O-trivial for a hackathon: a few hundred participants
and judges produce, at most, hundreds of thousands of audit rows, which SQLite
handles comfortably on a laptop. The limit worth knowing is that an external
process holding a write transaction — an open `sqlite3` shell, a GUI database
browser, a second copy of the portal on the same file — will block the portal's
writes until it commits or the timeout expires. Keep one writer.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Bind for 127.0.0.1:8081 failed: port is already allocated` | Something already holds 8081 | `LOCKDOWN_PORT=9000 docker compose up -d` |
| `[boot] cannot bind port 8081` on a host run | A local process holds the port | `python -m app --port 9000`, or free the port |
| `docker compose ps` shows `unhealthy` | `/gallery` is not returning `200` | `docker compose logs portal`. The check has a 30 s start period, so give a first boot a moment |
| Container exits immediately, log mentions a read-only file system | `PORTAL_DATA_DIR` points outside `/data` | Keep `PORTAL_DATA_DIR=/data`, or drop `read_only: true` |
| `database is locked` | Another process holds a write transaction | Close the other client; the portal serialises its own writes and waits 10 s |
| `Permission denied` creating `portal.sqlite3` | A bind-mounted directory is not writable by the container user | Use the named volume, or fix ownership on the host directory |
| `python3` opens the Microsoft Store | Windows Store stub is first on `PATH` | Use `py -3 -m app` or `python -m app` |
| Harness reports the fixture check failing | `fixtures.json` was not found from the working directory | Run from the repository root, or pass `--fixtures <path>` |
| Harness reports `claimed but not verified` | A probe failed | Read the indented detail lines under the failing probe: they name the request and the status returned |
| The browser shows a stale stylesheet | Static assets are cached for 300 s | Hard-reload. Pages themselves are `Cache-Control: no-store` |
| Sign-in works but every form post fails with `csrf_failed` | A non-browser client is not sending the token | Send `X-CSRF-Token`, or `_csrf` / `csrf_token` in the body. Browsers do this automatically |
| The demo sign-in dropdown is missing | `PORTAL_FAST_LOGIN` is unset — the default | Set `PORTAL_FAST_LOGIN=1` **only** on a demo box |
| The seed banner never appears | The database is already populated | That is the intended behaviour; `--reset` rebuilds it |
| Data disappeared after a restart | A reset ran, or the volume was removed | `docker volume ls` — confirm `lockdown-portal_portal-data` still exists |

---

## 12. Routine operations checklist

| When | Do this |
| --- | --- |
| Before an event | `docker compose up -d`, confirm `healthy`, run the acceptance checker, and take a first backup |
| During an event | Watch `docker compose ps` and the per-event audit page; back up before bulk assignments or rubric changes |
| Before publishing results | Publish to freeze a revision, then confirm `/results` and the CSV export agree |
| Before an upgrade | Take a backup (§5.1), upgrade (§7), then re-run `python3 -m unittest discover -s tests` and the checker |
| After an event | Move it to `archived` (there is no delete), take a final backup and keep it with the publications |
| Before destroying data | Confirm you accept losing the audit ledger: `--reset` and `down -v` both end it |

---

## 13. Related documents

| Document | Why it is relevant here |
| --- | --- |
| [README.md](README.md) | The 60-second evaluation, configuration table and known limitations |
| [SECURITY.md](SECURITY.md) | The threat model behind the defaults chosen here |
| [TESTING.md](TESTING.md) | The verification layers to re-run after any change |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The request lifecycle, guards and persistence behaviour |
| [DATA-MODEL.md](DATA-MODEL.md) | What is inside the file you are backing up |
| [TIER-MATRIX.md](TIER-MATRIX.md) | The evidence behind the tier claims |




