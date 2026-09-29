# Lockdown — features & route inventory

This document is the complete inventory of what Lockdown does, endpoint by
endpoint: the guard on each route, the scope it reads or writes, and the feature
it implements.

It is generated from and checked against the running code — `build_routes()` in
`app/routes.py` is the source of truth. Where this document and the code
disagree, the code wins.

**Counts: 58 route registrations — 37 GET and 21 POST.**

---

## 1. Feature summary

| Area | Delivered |
| --- | --- |
| **Authentication** | Email + password sign-in, scrypt hashing with PBKDF2 fallback, server-side session table, SHA-256 token hashes, `HttpOnly` `SameSite=Lax` cookies, 30-day lifetime, audited failure. |
| **Authorization** | Four roles (`participant`, `judge`, `organizer`, `admin`), declared per route, plus a second per-event membership check (`event_organizers`) on every organizer route. |
| **Events** | Create, configure, schedule, publish and archive hackathons. Per-event stages, tracks, prizes and rubric. Three lifecycle states, no hard delete. |
| **Multi-tenancy** | One install hosts many hackathons. Explicit `event_id` scoping on every competition table; public pages, galleries, results and CSVs are all per event. |
| **Teams** | Self-service team creation inside the registration window, invite codes, membership rows, one submission per team per event. |
| **Submissions** | Drafts, submit/finalize, edit until the deadline, per-save append-only version history, supersede/duplicate handling. |
| **Judging** | Judge invitations, per-project assignments, rubric scoring, private drafts, draft autosave, submit, revoke. |
| **Scoring** | Weighted rubric criteria normalized to 1.0, raw 0–100 mapping, cross-judge z-score normalization, explicit fallback flags, coverage tracking. |
| **Results** | Frozen publication snapshots with SHA-256 checksums and monotonic revisions, per-event visibility switches, CSV export of frozen or live standings. |
| **Certificates** | Winner and participation credentials derived from `SHA-256(recipient + kind + secret)`. |
| **Community** | Public comments on project dossiers, upvote toggling with self-vote refusal. |
| **Audit** | Immutable append-only ledger of sign-ins, refusals, assignments, scores, publications, exports and organizer changes — filterable per event. |
| **Front end** | Server-rendered HTML, no framework, no build step, strict `default-src 'self'` CSP, progressive-enhancement JavaScript only. |
| **Deployment** | One command, one process, one SQLite file, an unprivileged read-only container, and a verified offline mode. |

---

## 2. Complete route inventory

Legend:

- **Guard** — `public` = no session needed; otherwise the roles allowed.
- **CSRF** — whether a token is required for the request to be accepted.
- **Scope** — what the handler is allowed to read or write.

### 2.1 Public pages

| Method | Path | Guard | CSRF | Scope |
| --- | --- | --- | :---: | --- |
| `GET` | `/` | public | — | primary event landing page |
| `GET` | `/gallery` | public | — | primary event gallery |
| `GET` | `/projects` | public | — | alias of `/gallery` (DOGFOOD spec route) |
| `GET` | `/gallery/{project_id}` | public | — | one project dossier |
| `GET` | `/results` | public | — | published standings, embargoed before release |

### 2.2 The hackathon archive

| Method | Path | Guard | CSRF | Scope |
| --- | --- | --- | :---: | --- |
| `GET` | `/events` | public | — | every published hackathon (drafts excluded) |
| `GET` | `/events/{slug}` | public | — | one hackathon's cover page |
| `GET` | `/events/{slug}/gallery` | public | — | that hackathon's projects only |
| `GET` | `/events/{slug}/results` | public | — | that hackathon's ledger only |

A draft event returns `404` for anyone who does not manage it, so an unfinished
hackathon is not merely unlinked — it is unreachable.

### 2.3 Sessions

| Method | Path | Guard | CSRF | Notes |
| --- | --- | --- | :---: | --- |
| `GET` | `/signin` | public | — | sign-in form |
| `GET` | `/login` | public | — | alias of `/signin` |
| `POST` | `/signin` | public | **bypassed** | no session exists yet, so there is no token to compare |
| `POST` | `/signout` | public | required | revokes the session token in the database |
| `GET` | `/fast-login` | public | — | one-click demo sign-in; `404` unless `PORTAL_FAST_LOGIN=1` |
| `POST` | `/fast-login` | public | — | same, POST form |

> **Why `/fast-login` is off by default.** It mints a real session for a seeded
> fixture account with no password and no CSRF token. It is an exhibition
> convenience, not an authentication mechanism, so it is opt-in and the header
> link that advertises it only renders when the flag is on.

### 2.4 Community actions

| Method | Path | Guard | CSRF | Scope |
| --- | --- | --- | :---: | --- |
| `POST` | `/gallery/{project_id}/vote` | any role | required | toggles the caller's vote; own-team vote refused |
| `POST` | `/gallery/{project_id}/comment` | any role | required | body 1–4000 characters |

### 2.5 Participant

| Method | Path | Guard | CSRF | Scope |
| --- | --- | --- | :---: | --- |
| `GET` | `/participant` | `participant`, `admin` | — | caller's team, submission and certificates |
| `POST` | `/participant/team/create` | `participant`, `admin` | required | registration window enforced |
| `GET` | `/participant/project/new` | `participant`, `admin` | — | empty submission editor |
| `GET` | `/projects/new` | `participant`, `admin` | — | DOGFOOD spec alias |
| `POST` | `/participant/project/new` | `participant`, `admin` | required | **submission window enforced** |
| `POST` | `/projects/new` | `participant`, `admin` | required | DOGFOOD spec alias |
| `GET` | `/participant/project/edit` | `participant`, `admin` | — | editor pre-filled from the current version |
| `POST` | `/participant/project/edit` | `participant`, `admin` | required | **submission window enforced** |

Every save or submit writes a new `project_versions` row, so the editor is
additive: nothing an entrant wrote is ever silently replaced.

### 2.6 Judge

| Method | Path | Guard | CSRF | Scope |
| --- | --- | --- | :---: | --- |
| `GET` | `/judge` | `judge`, `admin` | — | the caller's assignment queue |
| `GET` | `/judge/assignments` | `judge`, `admin` | — | alias of `/judge` |
| `GET` | `/judge/evaluate/{project_id}` | `judge`, `admin` | — | rubric form; **assignment required** |
| `POST` | `/judge/evaluate/{project_id}` | `judge`, `admin` | required | assignment + review window enforced |

A judge opening a project they were not assigned receives `403 not_assigned`,
and the refusal is written to `audit_log`.

### 2.7 Organizer — the shelf

| Method | Path | Guard | CSRF | Scope |
| --- | --- | --- | :---: | --- |
| `GET` | `/organizer` | staff | — | exactly the hackathons the caller belongs to |
| `GET` | `/organizer/events/new` | staff | — | blank hackathon form with a default schedule |
| `POST` | `/organizer/events/new` | staff | required | creates the event and its owner membership atomically |

### 2.8 Organizer — one hackathon

Every route below resolves `{event_id}` and then calls `events.can_manage()`
before it reads or writes a row. The URL alone grants nothing.

| Method | Path | CSRF | Purpose |
| --- | --- | --- | :---: |
| `GET` | `/organizer/events/{event_id}` | — | overview: state, numbers, people |
| `GET` | `/organizer/events/{event_id}/stages` | — | stage table |
| `POST` | `/organizer/events/{event_id}/stages` | required | add a stage |
| `POST` | `/organizer/events/{event_id}/stages/remove` | required | remove a stage |
| `GET` | `/organizer/events/{event_id}/teams` | — | team roster with members |
| `GET` | `/organizer/events/{event_id}/submissions` | — | every submission, duplicates included |
| `GET` | `/organizer/events/{event_id}/judges` | — | judge roster and invitations |
| `POST` | `/organizer/events/{event_id}/judges` | required | invite a judge (creates the account if needed) |
| `GET` | `/organizer/events/{event_id}/assignments` | — | who has what, and what is unscored |
| `POST` | `/organizer/events/{event_id}/assignments` | required | assign one project to one judge |
| `POST` | `/organizer/events/{event_id}/assignments/revoke` | required | revoke without deleting the row |
| `GET` | `/organizer/events/{event_id}/reviews` | — | every review with its normalized score |
| `GET` | `/organizer/events/{event_id}/results` | — | standings, live or frozen, plus the publish switch |
| `POST` | `/organizer/events/{event_id}/results` | required | **publish** a frozen revision and issue certificates |
| `GET` | `/organizer/events/{event_id}/audit` | — | that hackathon's slice of the ledger |
| `GET` | `/organizer/events/{event_id}/settings` | — | identity, schedule, tracks, prizes, rubric, visibility |
| `POST` | `/organizer/events/{event_id}/settings` | required | validate and apply a settings edit |
| `POST` | `/organizer/events/{event_id}/organizers` | required | add an organizer |
| `POST` | `/organizer/events/{event_id}/organizers/remove` | required | remove an organizer; never the last one |

### 2.9 Organizer — shortcuts

These act on whichever hackathon the caller is working in, and refuse it when the
caller does not manage it.

| Method | Path | CSRF | Purpose |
| --- | --- | --- | :---: |
| `GET` | `/organizer/submissions` | — | submissions of the active event |
| `GET` | `/organizer/judges` | — | judge roster with calibration statistics |
| `GET` | `/organizer/audit` | — | audit trail of the active event |
| `POST` | `/organizer/publish` | required | publish the active event |

### 2.10 APIs and acceptance endpoints

| Method | Path | Guard | Scope |
| --- | --- | --- | --- |
| `GET` | `/api/judge/scores` | `judge`, `organizer`, `admin` | a judge's own rows only; a peer identifier is refused with `403 peer_scores_forbidden` |
| `GET` | `/api/export.csv` | staff | frozen snapshot when published, live standings otherwise, for an event the caller manages |
| `GET` | `/organizer/export` | staff | alias of `/api/export.csv` |

The `judge` parameter on `/api/judge/scores` is deliberately a **request**, not a
capability: it is accepted from an organizer (who may read any judge in their own
event) and refused from a judge who names anybody but themselves. This is the
route the DOGFOOD checker probes with judge B's cookie while asking for judge A.

---

## 3. Feature detail

### 3.1 Sessions and authentication

- Passwords are hashed with `hashlib.scrypt` (N=16384, r=8, p=1) and verified
  with `hmac.compare_digest`; PBKDF2-SHA256 at 120,000 iterations is the fallback
  when scrypt is unavailable on the platform.
- Session tokens are 32 random bytes from `secrets.token_hex(32)`. Only the
  **SHA-256 hash** of a token is stored, so a database leak does not yield usable
  sessions.
- A session is a token and a CSRF secret. There is no server-side flash queue;
  confirmations travel as `?done=<key>&what=<detail>` on the redirect.
- Failed sign-ins are recorded as `auth.signin` with `outcome='refused'`. The
  response is a `401` with the form re-rendered — no user enumeration, because the
  message is identical for an unknown email and a wrong password.

### 3.2 Events and scheduling

- A hackathon carries six canonical stages (registration, submission, review,
  judging, deliberation, results) plus any stages an organizer invents.
- `events.window_state(event, stage)` is the single decision point. The HTML form
  and the POST handler both call it, so a page and its API twin cannot disagree
  about whether an action is allowed.
- Lifecycle: `draft` → `published` → `archived`. `draft` is invisible to the
  public; `archived` leaves the directory but keeps every row.
- `gallery_visible` and `results_visible` are independent switches that hide a
  public surface without deleting data. Organizers keep full access either way.
- Creating a hackathon writes the `events` row, its stages, tracks, prizes,
  rubric, criteria **and** the creator's `owner` membership row in one
  transaction. A half-existent hackathon is therefore not reachable.

### 3.3 Multi-hackathon isolation

Ownership is explicit rather than inferred. `events.id` is the scope key and is
carried as an `event_id` foreign key on every table that describes a competition:

`event_stages` · `tracks` · `prizes` · `teams` · `projects` · `assignments` ·
`reviews` · `rubrics` · `advancements` · `event_organizers`

`review_scores` and `team_members` reach their event through their parent row and
therefore carry no column of their own.

Three checks implement the boundary:

| Check | Where | What it answers |
| --- | --- | --- |
| `events.can_manage(user, event)` | `app/events.py` | may this caller operate this hackathon? |
| `events.manageable_events(user)` | `app/events.py` | the shelf on `GET /organizer` |
| `events.visible_events()` | `app/events.py` | the public directory on `GET /events` |

### 3.4 Submissions

- One submission per team per event; a second attempt redirects to the editor.
- `status` is `draft` or `submitted`; `submission_state` is separate, so
  "submitted but still editable" is representable.
- Titles stop at 140 characters, summaries at 280, and a track must belong to the
  event — an entrant cannot invent a track or borrow one from another hackathon.
- Duplicate handling is data, not code: `prj_41.duplicate_of = 'prj_07'` and
  `prj_07.superseded_by = 'prj_41'`. The gallery filters out `duplicate_of IS NOT
  NULL`, and `scoring.scoreboard()` filters out `superseded_by IS NOT NULL`, so
  the canonical entry is the only one ranked.

### 3.5 Judging

- Assignment is an explicit row (`assignments`) scoped by `event_id`, with
  `status` in `assigned | accepted | declined | completed | revoked`.
- A draft review is saved and auto-resaved; an **unsubmitted draft never counts**
  toward standings, because `scoring.load_reviews()` reads only submitted and
  finalized rows.
- Submitting a review that was already submitted does not overwrite it: the
  previous numbers are appended to `review_revisions`, then `revision_no` is
  incremented. An announced score can always be reproduced.
- A finalized review is signed with an HMAC-SHA256 digest over `review_id`,
  `project_id`, `judge_user_id`, `weighted_raw` and the per-install
  `portal_secret`.

### 3.6 Scoring and publication

- Rubrics are per event (`rubrics.event_id`), with criteria weights normalized to
  sum to 1.0. Two hackathons in one database can be scored on entirely different
  criteria — Sample Hack 2026 uses `functionality 0.40 / quality 0.30 /
  innovation 0.30`, and Zero Dependency 2026 uses `correctness 0.45 / simplicity
  0.30 / documentation 0.25`.
- `scoring.scoreboard(event)` is the **only** ranking calculator. The organizer
  dashboard, the CSV exporter, the public results page and the publication
  pipeline all consume it, so standings cannot diverge between pages.
- Publishing writes a frozen JSON snapshot with a SHA-256 checksum and a
  monotonic `revision_no`, marks earlier revisions `is_current = 0`, then issues
  certificates.
- The public results page reads the snapshot, never the live query. Before
  publication it receives an **empty** table, so an embargo cannot be lifted by
  editing HTML.

The mathematics is in **[JUDGING.md](JUDGING.md)**.

### 3.7 Certificates

- Two kinds: `winner` (top three ranked projects) and `participation`.
- `code` is the first 20 characters, upper-cased, of
  `SHA-256("cert|<event_id>|<project_id>|<kind>" + portal_secret)`, so a code can
  be recomputed by an organizer holding the same secret and cannot be guessed from
  public data.

### 3.8 Audit ledger

`app/audit.py` records synchronously **inside the caller's transaction**, so an
audit row cannot be lost by a crash immediately after a write. Each entry carries
`action`, `actor_id`, `event_id`, `outcome`, a JSON `metadata` payload and a UTC
timestamp.

Namespaced actions include:

`auth.signin` · `auth.signout` · `access.denied` · `csrf.rejected` ·
`event.created` · `event.updated` · `event.manage_refused` ·
`team.created` · `submission.created` · `submission.saved` ·
`submission.submitted` · `submission.refused` · `assignment.created` ·
`assignment.revoked` · `review.drafted` · `review.submitted` ·
`review.refused` · `scores.refused` · `vote.cast` · `vote.withdrawn` ·
`vote.refused` · `comment.posted` · `results.published` · `results.exported` ·
`certificates.issued` · `organizer.added` · `organizer.removed`

`audit.refused()` is a wrapper for rejected actions. It never raises, so logging a
refusal can never change the outcome of the refusal itself.

### 3.9 Front end

- Views are pure Python string builders in `app/views/`. Nothing in `app/routes.py`
  writes HTML.
- Every interpolated value passes through `views.ui.esc()`, which is
  `html.escape(..., quote=True)`.
- There is **no inline `<script>`** and **no inline event handler** anywhere,
  which is what allows `Content-Security-Policy: default-src 'self'` with no
  exceptions.
- `app/views/static/app.js` adds countdowns, auto-submitting filters, 1–5
  keyboard shortcuts, draft autosave and confirm dialogs. With JavaScript
  disabled, every page and every form still works.

---

## 4. Deliberate non-features

These are stated so that a reader does not have to discover them by probing:

| Not implemented | Reason |
| --- | --- |
| Webhook delivery | The tables exist; dispatch is disabled to honour the zero-outbound-network constraint. |
| Request rate limiting | The `rate_limits` table exists; no middleware enforces it. |
| `Secure` cookie flag | The portal runs over plain HTTP on loopback and LAN by default; TLS is expected to terminate at a reverse proxy. |
| Pairwise/Bradley-Terry ranking | Implemented and seeded, but not used for official standings. |
| Hard event deletion | Lifecycle is `draft → published → archived`; nothing is ever destroyed. |
| Uploaded files | Submissions carry URLs (`repo_url`, `demo_url`), not binaries, so there is no upload path to secure. |

See also the [Known limitations](README.md#-known-limitations) section of the
README.
