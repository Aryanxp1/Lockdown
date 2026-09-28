# Lockdown — data model

All persistent state in Lockdown is stored in a single SQLite database
(`data/portal.sqlite3`) managed through `app/schema.sql` and `app/db.py`.
There is no ORM; queries use explicit parameterised SQL.

This document describes the schema conventions, the 30 tables, seed mappings,
revision tracking, and snapshot publication formats.

---

## 1. Schema conventions

* **Identifiers:** Text primary keys with a short domain prefix (e.g. `usr_`,
  `prj_`, `rev_`, `asg_`, `evt_`, `trk_`, `rsc_`, `pub_`).
* **Timestamps:** ISO-8601 UTC text formatted as `YYYY-MM-DDTHH:MM:SSZ`
  (`app/timeutil.py:17`). Timestamps sort lexicographically.
* **Booleans:** `INTEGER` columns storing `0` or `1`.
* **JSON columns:** Stored as `TEXT` with JSON payloads (`project_versions.snapshot`,
  `review_revisions.scores_json`, `result_publications.rows_json`).
* **Constraints:** `PRAGMA foreign_keys = ON` is applied on every database
  connection (`app/db.py:24`). Cascade deletes clean up child records when
  parent entities are removed.

---

## 2. Table inventory & live volume counts

The production database contains 30 tables. The row counts below were
verified directly from the Docker container volume (`lockdown-portal_portal-data`):

| Domain | Table | Rows | Purpose |
| --- | --- | ---: | --- |
| **Identity** | `users` | 123 | Accounts across participant, judge, organizer, and admin roles |
| | `sessions` | 7 | Active user sessions (including non-expiring demo tokens) |
| | `settings` | 1 | Global configuration key-values (stores `portal_secret`) |
| **Events** | `events` | 2 | Event definitions (`evt_01` official, `evt_practice` practice) |
| | `event_stages` | 12 | Timeline stages per event (draft, registration, submission, judging, etc.) |
| | `tracks` | 11 | Competition tracks (8 official fixtures + 3 practice) |
| | `prizes` | 6 | Event award categories |
| | `judge_invitations` | 0 | Pending judge email invitations |
| **Projects** | `teams` | 43 | Participant teams (40 official + 3 practice) |
| | `team_members` | 96 | Team membership and roles |
| | `projects` | 44 | Project submissions (41 official + 3 practice) |
| | `project_versions` | 44 | Append-only submission history snapshots |
| **Judging** | `rubrics` | 2 | Active rubrics per event |
| | `rubric_criteria` | 6 | Scoring criteria definitions with weights and score ranges |
| | `assignments` | 138 | Judge-to-project assignment pairings |
| | `reviews` | 127 | Submitted evaluations and active drafts |
| | `review_scores` | 380 | Individual criterion score entries |
| | `review_revisions` | 127 | Append-only evaluation score history |
| | `pairwise_comparisons`| 6 | Head-to-head project comparisons |
| **Results** | `result_publications`| 1 | Frozen public score snapshots with checksums |
| | `advancements` | 40 | Advancement decisions (8 advanced, 32 eliminated) |
| | `certificates` | 40 | Cryptographic credential records (37 participation, 3 winner) |
| **Community** | `comments` | 14 | Project feedback and discussion comments |
| | `votes` | 117 | Community upvotes |
| | `vote_ballots` | 0 | Structured community voting ballots |
| **Operations** | `audit_log` | 19 | Synchronous immutable security audit events |
| | `rate_limits` | 0 | IP and token request throttles |
| | `webhooks` | 1 | Outbound event notification hooks |
| | `webhook_deliveries`| 0 | Webhook dispatch attempts |
| | `schema_meta` | 1 | Schema version tracking |

---

## 3. Core tables & relationships

### Identity & authentication
* **`users`:** Accounts identified by `id` (e.g. `usr_admin_01`, `usr_jdg_01`). Stores `role` (`admin`, `organizer`, `judge`, `participant`), `email` (unique), `password_hash` (scrypt or PBKDF2), and `is_active`.
* **`sessions`:** Authenticated user sessions. Stores `token_hash` (SHA-256 of the cleartext cookie token), `user_id` (FK to `users`), `expires_at`, and `last_seen_at`.
* **`settings`:** Key-value table. Stores `portal_secret`, the HMAC signing key generated during initial boot (`app/security.py:75`).

### Events, stages & assignments
* **`events`:** Competition metadata (`evt_01`, `evt_practice`). Defines `slug`, `status` (`draft`, `published`), `target_reviews` (default 3), and deadline timestamps (`submissions_open`, `submissions_close`, `judging_open`, `judging_close`, `results_publish_at`).
* **`event_stages`:** Tracks linear timeline states (`upcoming`, `active`, `past`).
* **`assignments`:** Links `project_id` and `judge_user_id` with `status` (`assigned`, `accepted`, `declined`, `completed`). Fixture plan assignments have `origin='fixture_plan'`; scores-loaded assignments have `origin='fixture_scores'`.

### Projects & submissions
* **`projects`:** Core project submissions. Contains `event_id`, `team_id`, `track_id`, `title`, `summary`, `repo_url`, `status` (`draft`, `submitted`), and `submission_state` (`open`, `locked`).
  * *Duplicate handling:* Project `prj_41` has `duplicate_of='prj_07'`. The original duplicate `prj_07` has `superseded_by='prj_41'`. `scoring.scoreboard()` filters out records where `superseded_by IS NOT NULL`, ensuring only canonical entries are ranked.
* **`project_versions`:** Append-only history table. Every update or status change writes a new record with `version_no`, `snapshot` JSON, and `reason`.

### Rubrics, evaluations & scoring
* **`rubrics` & `rubric_criteria`:** Rubric configurations. Official fixtures use 3 criteria:
  * `functionality` (weight 0.40, range 1..5)
  * `quality` (weight 0.30, range 1..5)
  * `innovation` (weight 0.30, range 1..5)
* **`reviews`:** Evaluation submissions. Stores `weighted_raw` (0–100 scale), `normalized` score, `norm_method` (`zscore_judge` or `raw_fallback`), `norm_flags` (e.g. `insufficient_sample`, `zero_variance`), and `signature` (HMAC-SHA256).
* **`review_scores`:** Breakdown of criterion score values per review (`criterion_key`, `value`, `weight`).
* **`review_revisions`:** Append-only record of review score changes and autosave drafts.


---

## 4. Results publication & snapshots

### `result_publications`
Published results are frozen in `result_publications`. When an organizer publishes via `POST /organizer/publish`, the application:
1. Calculates the current ranking via `scoring.scoreboard(event)`.
2. Marks prior publications `is_current = 0`.
3. Serializes the project ranking list to `rows_json`.
4. Computes a SHA-256 checksum over the JSON text (`app/results.py:46`).
5. Inserts the snapshot with incremented `revision_no` and `is_current = 1`.

#### Snapshot JSON format (`rows_json`):
```json
[
  {
    "project_id": "prj_01",
    "title": "Iron Switch",
    "team_name": "Switchboard Labs",
    "track_name": "Systems",
    "published_rank": 1,
    "raw_mean": 84.17,
    "normalized_mean": 90.36,
    "review_count": 3,
    "coverage": 1.0,
    "flags": []
  }
]
```

### `certificates`
Cryptographic credentials issued to participants (`app/results.py:100`):
* `kind`: `winner` (top 3 ranked projects) or `participation`.
* `verification_code`: First 20 uppercase characters of `SHA-256(recipient + kind + secret)`.

### `advancements`
Progression tracking for multi-stage events. Stores `decision` (`advanced` for ranks 1–8, `eliminated` for lower ranks).

---

## 5. Audit log (`audit_log`)

The `audit_log` is an immutable append-only ledger (`app/audit.py:34`). Every entry records:
* `action`: Namespaced action string (e.g. `access.denied`, `csrf.rejected`, `results.published`, `scores.refused`, `certificates.issued`).
* `actor_id`: User ID initiating the operation, or `system` during boot.
* `event_id`: Event context, if applicable.
* `outcome`: Result status (`ok`, `denied`, `error`).
* `metadata`: JSON object containing operation details and parameters.
* `created_at`: UTC ISO-8601 timestamp.

---

## 6. Seed fixture mapping

When initialized from `data/fixtures.json`:
1. **Users & Teams:** Team participant emails are extracted and registered as `users` (`role='participant'`). 30 judges are created as `usr_jdg_01` through `usr_jdg_30`.
2. **Duplicate Project Pairing:** Fixture project `prj_41` is wired as a replacement for `prj_07` (`prj_41.duplicate_of = 'prj_07'`, `prj_07.superseded_by = 'prj_41'`).
3. **Practice Workspace:** Injects 3 practice projects (`prj_practice_field` as draft; `prj_practice_carto` and `prj_practice_kiln` as submitted) along with an active evaluation draft for demo judge testing.
4. **Demo Sessions:** Pre-authorizes 7 demo logins (`demo:admin`, `demo:organizer`, `demo:judge_a`, `demo:judge_b`, `demo:judge_c`, `demo:participant`, `demo:participant_2`) with expiration timestamp set to `2099-01-01T00:00:00Z`.

