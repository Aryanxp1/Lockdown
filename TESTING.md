# Lockdown — testing & verification

This document explains how to verify Lockdown, what each verification layer
proves, and what none of them prove. It is written so that a reviewer with no
prior context can reproduce every claim in the [README](README.md) in a few
minutes, without reading the source first.

**Evidence summary**

| Layer | Command | Result |
| --- | --- | --- |
| Official DOGFOOD acceptance harness | `python3 run.py .dogfood.toml` | **7 of 7 probes pass**, `T1` and `T2` verified |
| Unit suites (no server needed) | `python -m unittest discover -s tests` | **20 tests, OK** in ≈4 s |
| Air-gap proof | `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d` | Harness still passes with no route off the host |
| Manual probes | `curl`, see §5 | Each guard demonstrated individually |

---

## 1. What "verified" means here

Three properties, checked separately, and none of them assumed:

1. **The public surface works** — a stranger can browse the gallery and see real
   fixture projects.
2. **The refusals are real** — a closed event rejects a submission, a judge
   cannot read a peer's scores, a participant cannot reach judge data, and an
   organizer can export standings.
3. **It runs with no network** — the whole portal works with the container's
   gateway removed.

The first two are what `run.py` probes over HTTP; the third is the offline
overlay. Everything else in this document exists so that a reader does not have to
take a summary table on trust.

---

## 2. Layer 1 — the official acceptance harness

`run.py` is the DOGFOOD 2026 checker, committed verbatim in this repository, and
[`.dogfood.toml`](.dogfood.toml) is the routing it reads.

| Property | Detail |
| --- | --- |
| Transport | `urllib.request` over HTTP only — it never imports the application |
| Authentication | It never logs in. It attaches the session cookies given in `.dogfood.toml` |
| Configuration | `[portal].base_url`, `[tiers].claimed`, `[routes]`, `[auth]` |
| TOML parsing | `tomllib` on Python 3.11+, plus a small built-in fallback parser so older interpreters run it too |
| Fixture check | Loads `fixtures.json` beside itself and looks for the first fixture project titles in the gallery HTML; `--fixtures <path>` overrides |
| Timeout | 10 s per request |
| Output | A human-readable report, committed to [`acceptance-report.txt`](acceptance-report.txt) |

### 2.1 Run it

Against the container (recommended — no host Python needed):

```bash
docker compose up -d
docker compose exec portal python3 run.py .dogfood.toml
```

Against a local `python -m app` on the default port:

```bash
python run.py .dogfood.toml        # py -3 run.py .dogfood.toml on Windows
```

Regenerate the committed report:

```bash
docker compose exec portal python3 run.py .dogfood.toml > acceptance-report.txt
```

> **Read the report, not the exit code.** `run.py` always exits `0`; a failure is
> reported in the text (`... FAIL`, plus indented detail lines naming the request
> that was sent and the status that came back). Do not wire it into CI as a
> pass/fail gate without checking the output.

### 2.2 The seven probes

| # | Tier | Probe | Request | Expected | What it proves |
| --- | :---: | --- | --- | :---: | --- |
| 1 | T1 | `gallery is public` | `GET /gallery`, no cookie | `200` | The gallery is reachable anonymously |
| 2 | T1 | `project from fixtures shown` | the body of probe 1 | a fixture title in the HTML | The portal renders real seeded data, not an empty shell |
| 3 | T1 | `closed event refuses submissions` | `POST /participant/project/new` as participant | any `4xx` | A late submission is refused in the API |
| 4 | T2 | `judge sees own scores` | `GET /api/judge/scores` as judge A | `200` | A judge can read their own evaluations |
| 5 | T2 | `judge cannot see peer scores` | `GET /api/judge/scores?judge=tomas.varga@example.org` as judge B | `401`/`403` | Judge isolation is enforced, not merely hidden in a page |
| 6 | T2 | `participant blocked` | `GET /api/judge/scores` as participant | `401`/`403` | Role separation holds |
| 7 | T2 | `csv export works` | `GET /api/export.csv` as organizer | `200`, first line contains a comma | Standings are exportable by the organizer |

Two honest notes about probe 3, because they matter to a reviewer:

* The probe accepts **any** `4xx`. A portal that refused the POST for a reason
  other than the deadline would still pass. Lockdown's POST route requires a CSRF
  token and the probe sends none, so the first refusal a token-less client meets
  is `403 csrf_failed` — which is a `4xx`. §5.3 is the check that isolates the
  deadline itself.
* It does not manipulate a clock. The fixture event's submission window closed in
  the past, so a faithfully seeded portal is already closed.

### 2.3 How the tier verdict is computed

`run.py` marks a tier verified only when **every** probe in that tier passed, and
credits a tier only if every tier below it passed too — `T2` does not count unless
`T1` did. The final line is:

```
claimed T1 T2, verified T1 T2
```

If the configuration claimed a tier whose probes failed, the report adds
`note: claimed but not verified: …`. The probe-by-probe mapping, including which
code implements each verified behaviour, is in [TIER-MATRIX.md](TIER-MATRIX.md).

---

## 3. Layer 2 — the unit suites

Two `unittest` suites cover what an HTTP probe cannot see. Neither needs a running
server, a container or the network:

```bash
python -m unittest discover -s tests         # py -3 -m unittest discover -s tests
```

```
Ran 20 tests in 3.7s
OK
```

*Wall time varies by machine and by whether the operating system has already
warmed its filesystem cache; the count and the verdict are the parts that matter.*

### 3.1 `tests/test_event_isolation.py` — 10 tests

The multi-hackathon boundary, exercised through the real router and the real
database:

| Test | What it asserts |
| --- | --- |
| `test_shelf_lists_only_the_events_the_caller_manages` | `/organizer` shows exactly the caller's hackathons |
| `test_an_outsider_cannot_open_any_management_page` | Every management URL of a foreign event is refused |
| `test_an_outsider_cannot_use_the_shortcuts` | The non-event-scoped organizer shortcuts refuse too |
| `test_the_organizer_who_does_manage_them_still_gets_in` | The control case: a legitimate organizer is not blocked |
| `test_an_outsider_cannot_write_to_someone_elses_event` | POSTs to a foreign event are refused and nothing is written |
| `test_an_organizer_cannot_borrow_row_ids_from_another_event` | Foreign `project_id`, `team_id` and `review_id` values are not accepted |
| `test_public_pages_never_mix_two_hackathons` | Per-event public pages contain only their own projects |
| `test_a_hidden_gallery_is_hidden_from_the_public_only` | Visibility switches hide from visitors, not from the organizer |
| `test_a_draft_hackathon_is_invisible_to_everyone_else` | Drafts appear in no directory and on no public page |
| `test_every_refusal_lands_in_the_audit_log` | Each refusal above leaves an audit row |

### 3.2 `tests/test_migrations.py` — 10 tests

The schema `v1 → v2` upgrade path, including its failure modes:

| Test | What it asserts |
| --- | --- |
| `test_a_version_one_database_gains_exactly_what_is_missing` | The upgrade is additive and touches nothing else |
| `test_the_report_names_the_objects_it_had_to_ensure` | The migration report names objects that exist |
| `test_every_existing_row_survives_with_a_default` | Existing rows keep their values and gain defaults |
| `test_running_it_twice_changes_nothing` | Idempotency |
| `test_an_event_organizer_gets_one_row_per_event` | The backfill produces exactly one membership row per event |
| `test_a_missing_table_is_skipped_not_invented` | An absent table is not fabricated |
| `test_a_broken_database_is_reported_loudly` | A missing *indexed* table raises rather than limping on |
| `test_an_unrelated_table_is_never_touched` | No collateral changes |
| `test_the_real_version_one_schema_upgrades_with_every_row_intact` | The genuine v1 schema, upgraded with its data intact |
| `test_schema_sql_already_describes_the_current_version` | A brand-new database needs no migration at all |

Both suites work on a throwaway database directory, so running them does not touch
`./data`. They are copied into the image as well, so the same command works there:

```bash
docker compose exec portal python3 -m unittest discover -s tests
```

---

## 4. Layer 3 — the offline (air-gap) proof

The strongest single claim in this project is "no outbound network", and it is
verified by removing the network rather than by reading the imports.

`docker-compose.offline.yml` is an overlay that puts the service on a network with
`internal: true`. That removes the gateway, so DNS resolution fails and TCP to any
public address fails. Published ports are reset, because an internal network has
no NAT to publish through — so the container is reached with `exec` instead.

```bash
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
docker compose -f docker-compose.yml -f docker-compose.offline.yml \
    exec -T portal python3 run.py .dogfood.toml
docker compose -f docker-compose.yml -f docker-compose.offline.yml down
```

Expected: the same `7 of 7` report. The database comes from the same named volume,
so running the offline proof does not throw away state.

What this proves: the portal serves pages, seeds, computes standings and answers
the checker with no route off the host. What it does not prove: that a *future*
change will stay offline. The structural argument for that is in
[README.md](README.md#-offline-by-default) — no HTTP client is imported anywhere
in `app/`, and no rendered page references an external asset.

---

## 5. Layer 4 — manual probes

The harness runs seven checks; these are the ones it cannot state precisely. Each
is one `curl` against a running portal, and the expected status is exact. All of
them use the deterministic demo sessions from [`app/config.py`](app/config.py),
which are printed in the boot banner — they are demo credentials for synthetic
fixture data, not secrets.

> On Windows, use `curl.exe` (PowerShell aliases `curl` to `Invoke-WebRequest`),
> and single-quote any URL that contains `?` or `&`.

### 5.1 The public surface

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/gallery   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/results   # 200
curl -s        http://127.0.0.1:8081/gallery | grep -c 'prj_'           # >= 1
```

### 5.2 Judge isolation, one status at a time

```bash
# judge A reads their own scores
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'Cookie: session=sess_jdg_a_91bc4730' \
  http://127.0.0.1:8081/api/judge/scores                                  # 200

# judge B asks for the URL that returns judge A's scores
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'Cookie: session=sess_jdg_b_44de8a12' \
  'http://127.0.0.1:8081/api/judge/scores?judge=tomas.varga@example.org'  # 403

# a participant is not a judge
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'Cookie: session=sess_prt_2e8877ab' \
  http://127.0.0.1:8081/api/judge/scores                                  # 403

# no session at all
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8081/api/judge/scores                                  # 401

# the refusal names its reason
curl -s -H 'Cookie: session=sess_jdg_b_44de8a12' \
  'http://127.0.0.1:8081/api/judge/scores?judge=tomas.varga@example.org'
# {"error": "peer_scores_forbidden", ...}

# the organizer exports standings
curl -s -H 'Cookie: session=sess_org_3f9a21c4' \
  http://127.0.0.1:8081/api/export.csv | head -2
```

### 5.3 Isolating the deadline from the CSRF guard

The official probe 3 accepts any `4xx`, so it cannot distinguish "the window is
closed" from "you had no CSRF token". This sequence can. Sign in for real, take
the token the form renders, and watch the reason change:

```bash
# 1. sign in as the demo participant and keep the cookie
curl -s -c jar.txt -o /dev/null -X POST \
  -d 'email=priya1@example.org&password=dogfood-demo-2026' \
  http://127.0.0.1:8081/signin

# 2. read the CSRF token out of the submission form
TOKEN=$(curl -s -b jar.txt http://127.0.0.1:8081/participant/project/new \
        | grep -o 'name="csrf_token" value="[^"]*"' | head -1 \
        | sed 's/.*value="//; s/"$//')

# 3. with a session but no token, the refusal is the CSRF guard
curl -s -b jar.txt -o /dev/null -w '%{http_code}\n' \
  -d 'title=late&summary=probe' \
  http://127.0.0.1:8081/participant/project/new                           # 403

# 4. with a valid token, the refusal is the deadline itself
curl -s -b jar.txt -H "X-CSRF-Token: $TOKEN" \
  -d 'title=late&summary=probe' \
  http://127.0.0.1:8081/participant/project/new
# {"error": "submissions_closed", "message": "Submissions for ... closed at ..."}
```

The fixture event's window is in the past, so step 4 is the deadline refusal, and
`audit_log` gains a `submission.refused` row. To see that row without the UI:

```bash
docker compose exec portal python3 -c "import sqlite3; print(*sqlite3.connect('/data/portal.sqlite3').execute('SELECT action, outcome, summary FROM audit_log ORDER BY rowid DESC LIMIT 5'), sep='\n')"
```

### 5.4 Hardening spot checks

```bash
# path traversal never leaves the static directory
curl -s -o /dev/null -w '%{http_code}\n' --path-as-is \
  'http://127.0.0.1:8081/static/../server.py'                            # 404

# the wrong verb is a 405 with an Allow header, not a 404 and not a crash
curl -s -o /dev/null -D - -X DELETE http://127.0.0.1:8081/gallery | grep -iE '^(HTTP|allow)'

# every response carries the security headers, including an error page
curl -s -o /dev/null -D - http://127.0.0.1:8081/does-not-exist | grep -iE 'content-security-policy|x-frame-options|x-content-type-options'

# a state-changing POST with no session is refused; a browser instead gets a 303
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8081/signout   # 303
```

---

## 6. What is not tested

Stating this plainly is more useful than a longer list of green ticks.

| Not covered | Why it matters to a reviewer |
| --- | --- |
| Browser automation | No committed Playwright/Selenium suite. The progressive-enhancement layer (`app/views/static/app.js`: countdowns, autosubmitting filters, 1–5 shortcuts, draft autosave, confirm dialogs) was verified by hand; local capture output under `.playwright-mcp/` is gitignored. |
| T3 / T4 harness coverage | The official brief ships T1 and T2 probes. T3/T4 behaviour that exists is documented as a capability in [TIER-MATRIX.md](TIER-MATRIX.md), not as a harness-verified pass. |
| Load, concurrency, soak | Nothing is measured. The design is one thread per request against a single SQLite writer with a 10 s busy timeout, so no throughput claim is made anywhere in these documents. |
| TLS, reverse proxies, path prefixes | Not exercised. The portal is verified over plain HTTP on loopback. |
| Windows and macOS specifics | Developed on Windows and run in Linux containers; this repository contains **no CI configuration**, so no platform matrix runs automatically. |
| Fuzzing / static analysis | No fuzzer output, no linter config and no scanner report is committed. |
| Restore-from-backup | The procedure in [OPERATIONS.md](OPERATIONS.md) is documented and reasoned, not covered by an automated test. |

### 6.1 About `tmp/`

`tmp/` holds scratch scripts written while building the portal. It is gitignored
and excluded from the Docker build context (`.dockerignore`), several early probes
assert copy that has since changed, and **nothing in it is quoted as evidence
anywhere in these documents**. If a script in `tmp/` fails when you run it, that is
expected for the older ones; the four layers above are the supported verification
path.

---

## 7. Where the evidence lives

| Artifact | What it is |
| --- | --- |
| [`run.py`](run.py) | The official checker |
| [`.dogfood.toml`](.dogfood.toml) | Routes, claimed tiers and the demo cookies the checker uses |
| [`acceptance-report.txt`](acceptance-report.txt) | The committed output of the last run |
| [`tests/test_event_isolation.py`](tests/test_event_isolation.py), [`tests/test_migrations.py`](tests/test_migrations.py) | The 20 unit tests |
| [`docker-compose.offline.yml`](docker-compose.offline.yml) | The air-gap overlay |
| [`TIER-MATRIX.md`](TIER-MATRIX.md) | Which tier each probe belongs to, and where each behaviour lives |
| [`FEATURES.md`](FEATURES.md) | Guard, CSRF flag and scope for all 58 routes — the list to probe against |
| [`SCREENSHOTS.md`](SCREENSHOTS.md) | The manual, visual pass and its capture checklist |

If a claim in the [README](README.md) is not backed by one of these, treat the
claim as unverified and the code as the authority.



