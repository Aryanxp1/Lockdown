# Lockdown — tier evidence matrix

The DOGFOOD 2026 brief defines four tiers. This document states, without
embellishment, which ones Lockdown claims, what the official harness actually
verified, where in the code each verified behaviour lives, and which later-tier
capabilities exist outside the harness's reach.

**Claim: T1 and T2.**
**Verified by the official harness: T1 and T2 — 7 of 7 probes pass.**

```
claimed T1 T2, verified T1 T2
```

---

## 1. Official harness results

The harness is `run.py`, driven by [`.dogfood.toml`](.dogfood.toml). It talks
HTTP only and never logs in — it attaches the session cookie it is given. The
output is committed verbatim to [`acceptance-report.txt`](acceptance-report.txt).

| Tier | Check | Route probed | Expected | Actual | Code |
| :---: | --- | --- | --- | :---: | --- |
| **T1** | gallery is public | `GET /gallery`, no auth | `200` | **PASS** | `handle_gallery`, `app/routes.py` |
| **T1** | project from fixtures shown | `GET /gallery` | a fixture title in the body | **PASS** | `_decorate_projects`, `PROJECT_SELECT` |
| **T1** | closed event refuses submissions | `POST /participant/project/new` as participant | `4xx` | **PASS** | `events.submission_window()`, `app/events.py` |
| **T2** | judge sees own scores | `GET /api/judge/scores` as judge A | `200` | **PASS** | `handle_api_judge_scores` |
| **T2** | judge cannot see peer scores | `GET /api/judge/scores?judge=…` as judge B | `401`/`403` | **PASS** | `handle_api_judge_scores` |
| **T2** | participant blocked | `GET /api/judge/scores` as participant | `401`/`403` | **PASS** | role guard + handler |
| **T2** | csv export works | `GET /api/export.csv` as organizer | `200` + CSV | **PASS** | `handle_api_export_csv` |

### 1.1 Route mapping

`.dogfood.toml` points the harness at Lockdown's own route names — the brief
explicitly leaves route naming to the implementer:

| Harness key | Lockdown route |
| --- | --- |
| `gallery` | `/gallery` |
| `submit` | `/participant/project/new` |
| `judge_scores` | `/api/judge/scores` |
| `peer_scores` | `/api/judge/scores?judge=tomas.varga@example.org` |
| `csv_export` | `/api/export.csv` |

`submit` is registered under both `/participant/project/new` and the spec alias
`/projects/new`; `csv_export` under both `/api/export.csv` and
`/organizer/export`.

### 1.2 Why the T1 submission probe passes without manipulating a clock

The fixture event's `submissions_close` is a date in the past, so a portal that
seeded the fixture honestly is already closed. The probe therefore does not touch
a clock or inspect *why* the POST was refused — it only requires that the
refusal happened. Lockdown enforces the window inside the handler
(`_require_window` and `events.submission_window`), not in the template, so the
refusal is identical whether the request came from a browser or from `curl`.

### 1.3 Why the T2 peer-scores probe passes

This is the check that decides most of T2, and the one where hiding a table is
most often mistaken for isolation. The refusal lives in the handler:

```
caller is a judge
  → requested judge is not the caller  →  403 peer_scores_forbidden
                                          + audit_log('scores.refused')
```

A judge may pass their **own** id or fixture id and get `200`. Anything else is
refused, and the refusal is recorded. An organizer may read any judge, but only
inside an event they manage (`events.can_manage`); a participant is refused
outright.

---

## 2. Why only T1 and T2 are claimed

The brief is explicit that over-claiming is the one thing that costs points:
*"Saying you got further than you did is the one thing that actually costs you
points, so do not."* The harness verifies seven behaviours, all of them in T1
and T2.

T3 and T4 capabilities are therefore reported below as **self-reported**, with
the code location for each one, and are deliberately excluded from the claim
line. A clean `claimed T1 T2, verified T1 T2` is worth more than a longer claim
the harness cannot confirm.

---

## 3. T3 — self-reported status, not harness-verified

The brief describes T3 as: community voting, comments, results hidden until the
window closes, ballots in random order, and an answer to people trying to cheat
the public vote.

| T3 capability | Status | Evidence |
| --- | :---: | --- |
| Community voting | **Implemented** | `POST /gallery/{project_id}/vote`, `handle_vote` — toggle semantics, one vote per user per project |
| Vote brigading answer | **Implemented** | A team member voting for their own submission is refused with `403 own_project` and audited as `vote.refused` |
| Comments | **Implemented** | `POST /gallery/{project_id}/comment`, `handle_comment` — 1–4000 characters, author attributed, `is_hidden` supported |
| Results hidden until release | **Implemented** | The public results page reads only a `result_publications` snapshot. Before publication the handler passes the template an **empty** row set plus an embargo panel, so the embargo cannot be lifted by editing HTML |
| Per-event publication scope | **Implemented** | Publishing writes a snapshot carrying its own `event_id`; it cannot touch another hackathon's frozen standings |
| Ballots in random order | **Not implemented** | `vote_ballots` exists in the schema (0 rows) but is unused. Lockdown's public vote is a per-project upvote toggle, not a randomized ballot, so there is no ballot order to randomize |
| Structured community ballot rounds | **Not implemented** | See above — no ballot model beyond individual votes |

**T3 verdict: partially implemented.** The pieces that exist are real and
enforced in the backend, but the ballot model is absent, so a T3 claim would not
be honest.

---

## 4. T4 — self-reported status, not harness-verified

The brief describes T4 as: REST API, webhooks, certificates, verifiable judge
records, an embeddable gallery, bulk import and export.

| T4 capability | Status | Evidence |
| --- | :---: | --- |
| HTTP JSON API | **Partial** | `GET /api/judge/scores` returns structured JSON; `GET /api/export.csv` returns CSV. There is no general `/api/v1` surface — the portal is HTML-first by design |
| CSV export (bulk out) | **Implemented** | `handle_api_export_csv` — frozen snapshot when published, live standings otherwise, always scoped to an event the caller manages |
| Bulk import | **Partial** | `fixtures.json` is loaded through `app/seed.py` on an empty database. There is no operator-facing import endpoint |
| Certificates | **Implemented** | `results.issue_certificates()` — `winner` for the top three, `participation` for the rest, each with a recomputable verification code |
| Verifiable judge records | **Partial** | Finalized reviews carry an HMAC-SHA256 signature over `review_id`, `project_id`, `judge_user_id` and `weighted_raw` (`app/security.py`). Verification needs the per-install `portal_secret`, so this is tamper-evidence for the operator, not public third-party verification — there is no asymmetric signature and no published public key |
| Webhooks | **Not implemented** | `webhooks` and `webhook_deliveries` exist in the schema, but no daemon delivers them. This is deliberate: dispatch would violate the zero-outbound-network constraint |
| Embeddable gallery | **Not implemented** | No widget, iframe or embed route exists |

**T4 verdict: partially implemented.** Certificates and CSV export are real;
webhooks, the embeddable gallery, a public-key verifiable record and a general
REST surface are not.

---

## 5. Bonus challenges

The brief lists four optional challenges and states plainly that they do not
change the weighted score. Honest status:

| Bonus challenge | Status | Where |
| --- | :---: | --- |
| **Normalization proof** | **Partially answered** | [`JUDGING.md`](JUDGING.md) documents the model, both rubrics, every parameter, the fallback conditions, and a fully worked example for review `rev_fx_016` with the exact intermediate values. This is a documented, reproducible derivation — not a simulation study |
| **Pairwise judging mode** | **Not answered as a mode** | Bradley-Terry is implemented in `app/scoring.py` and six `pairwise_comparisons` rows are seeded, but no route exposes pairwise judging and it does not affect standings |
| **Threat model** | **Answered** | [`SECURITY.md`](SECURITY.md) states what is defended, what is explicitly out of scope, and where each control lives |
| **API-first design** | **Not answered** | Lockdown is HTML-first. Routes render pages and enforce their own guards; only two routes return machine-readable payloads |

---

## 6. Anti-claims — things Lockdown does *not* claim

Recorded here so nobody has to discover them by probing:

- **No webhook delivery.** Rows exist, no sender exists.
- **No request rate limiting.** The table exists, no middleware reads it.
- **No `Secure` cookie flag.** Plain HTTP on loopback and LAN is the supported
  default; TLS belongs at a reverse proxy.
- **No pairwise ranking in official results.** Standings come from rubric
  z-score normalization only.
- **No hard deletion of events.** Lifecycle only.
- **No file uploads.** Submissions carry URLs, not binaries.
- **No public-key certificate verification.** Codes are HMAC-derived and
  recomputable by the install that issued them.

---

## 7. Reproducing this report

```bash
# 1. bring up a seeded portal
docker compose up -d

# 2. wait for the health check, then run the official harness
docker compose exec portal python3 run.py .dogfood.toml

# 3. overwrite the committed report with fresh output
docker compose exec portal python3 run.py .dogfood.toml > acceptance-report.txt

# 4. teardown
docker compose down
```

Or, against a local `python -m app` on the default port:

```bash
python run.py .dogfood.toml
```

The unit suites that cover multi-hackathon isolation and the schema upgrade path
need no running server:

```bash
python -m unittest discover -s tests
```

Full verification instructions: **[TESTING.md](TESTING.md)**.
