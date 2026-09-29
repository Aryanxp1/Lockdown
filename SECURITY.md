# Lockdown — security model

This is the threat model for the Lockdown portal. It states what is defended,
where each control lives in the code, and what is deliberately out of scope.
Every claim names its mechanism, and every gap is listed rather than left for a
reader to discover by probing.

The deployment Lockdown is built for is a **trusted operator running one portal
on loopback or a private LAN**, with the database file on storage only that
operator can read. It is competition infrastructure, not a public SaaS: there is
no self-signup, no password reset, no email and no outbound network access.

---

## 1. Trust boundaries

| Boundary | Other side | What enforces it |
| --- | --- | --- |
| Client → HTTP handler | an unauthenticated, untrusted client | Every route declares `public=True`, `roles=(…)` and `csrf=True` explicitly, and `guard_roles()` / `guard_csrf()` run **before** the handler (`app/server.py:194`, `app/server.py:215`). |
| Handler → database | application code | Parameterised SQL only; no value is ever interpolated into a statement (`app/db.py:87`, `app/db.py:123`). |
| Organizer of hackathon A → hackathon B | an authenticated user with the wrong scope | `events.can_manage()` re-checks membership inside every event-scoped handler. |
| Template → browser | attacker-supplied text | `views.ui.esc()` (`html.escape(…, quote=True)`) on every interpolated value, with `default-src 'self'` CSP as a second line. |
| Container → host | the portal process | Unprivileged `portal` user, `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`, exactly one writable volume. |

---

## 2. Controls at a glance

| Property | Control | Where |
| --- | --- | --- |
| Passwords are never stored or logged in clear text | scrypt (`n = 2^14`, `r = 8`, `p = 1`), per-user 16-byte salt; PBKDF2-HMAC-SHA256 (120 000 iterations) only where scrypt is unavailable | `app/security.py:22`–`62` |
| A stolen database does not yield usable sessions | only `SHA-256(token)` is stored; the raw token exists in the cookie alone | `app/security.py:71`, `app/auth.py:64` |
| Cross-site form posts are refused | per-session CSRF token, compared with `hmac.compare_digest` | `app/auth.py:160`, `app/server.py:215` |
| Roles and per-event membership are both enforced | route-declared roles, then `events.can_manage()` inside the handler | `app/auth.py:145`, `app/events.py:104` |
| Two hackathons never share a row | `event_id` on every competition table, checked on read and write | `app/schema.sql`, `tests/test_event_isolation.py` |
| Scripts cannot be injected | all output escaped; no inline `<script>` or event handler exists anywhere | `app/views/ui.py:12`, `app/server.py:25` |
| A submitted score cannot be edited off the record | each submitted review carries an HMAC-SHA256 signature | `app/security.py:88`, `app/results.py:190` |
| Published results cannot be rewritten silently | immutable snapshot + SHA-256 checksum + monotonic revision | `app/results.py:49` |
| Every refusal is recorded | `audit.record()` writes synchronously inside the caller's transaction | `app/audit.py:16` |
| Nothing leaves the host | no HTTP client is imported anywhere in `app/` | [README](README.md#-offline-by-default) |

---

## 3. Authentication

### 3.1 Password storage

`app/security.py` implements both schemes and chooses at runtime:

```
stored = "scrypt$16384$<salt_hex>$<digest_hex>"            # preferred
stored = "pbkdf2-sha256$120000$<salt_hex>$<digest_hex>"    # fallback
```

* The salt is 16 random bytes from `secrets.token_bytes` per user, so identical
  passwords produce different digests.
* `hashlib.scrypt` is used when the interpreter's OpenSSL exposes it; a
  `ValueError`, `AttributeError` or `TypeError` falls back to PBKDF2-HMAC-SHA256
  at `PORTAL_PBKDF2_ITERATIONS` (default 120 000).
* Verification re-derives the digest and compares with `hmac.compare_digest`, so
  a wrong password cannot be found by timing (`app/security.py:62`).
* The scheme and its cost are stored **inside** the digest string, which is why
  an older PBKDF2 hash keeps verifying after the code moves to scrypt.
* Nothing in the portal writes a password, a password hash or a raw session
  token to a log, an audit row or an error page.

### 3.2 Sessions

| Property | Value |
| --- | --- |
| Token generation | `secrets.token_urlsafe(24)` — 192 bits of entropy (`app/auth.py:59`) |
| What the database stores | `SHA-256(token)` in hex, unique per row (`app/auth.py:64`) |
| CSRF token | `secrets.token_urlsafe(16)`, stored beside the session |
| Lifetime | `PORTAL_SESSION_DAYS` days (default 30), recorded as `expires_at` |
| Revocation | `revoked_at` written by `POST /signout`; a revoked row resolves to "no user" |
| Account switch-off | `users.is_active = 0` invalidates every session for that account |
| Cookie | `session=…; Path=/; Max-Age=…; HttpOnly; SameSite=Lax` |
| Alternative credential | `Authorization: Bearer <token>` is accepted as well as the cookie (`app/auth.py:80`) |

Every resolution step fails closed: an unknown token, a revoked session, an
expired session and an inactive account all return without attaching a user
(`app/auth.py:78`–`104`). `last_seen_at` is bumped on each request, which is the
only write a read-only request performs.

**Not set: `Secure`.** The portal ships for plain HTTP on loopback and private
LANs so it runs out of the box with no self-signed certificate. A public
deployment is expected to terminate TLS at a reverse proxy; nothing in the
application prevents the flag being added there (`app/server.py:189`).

### 3.3 Sign-in, sign-out and failures

* `POST /signin` looks the user up by email (`COLLATE NOCASE`), requires
  `is_active`, and verifies the password before issuing a session.
* A rejected sign-in is **audited** (`action="auth.signin"`,
  `outcome="refused"`) and answered with `401` plus one generic message for every
  failure mode — unknown email, wrong password and disabled account are
  indistinguishable (`handle_signin`, `app/routes.py`).
* A successful sign-in records the actor, sets `last_login_at`, and issues the
  cookie.
* `POST /signout` requires a CSRF token, revokes the session row, clears the
  cookie with `Max-Age=0`, and audits `auth.signout`.

---

## 4. CSRF

Every state-changing route opts in with `csrf=True`, and the guard only applies
to `POST`, `PUT`, `PATCH` and `DELETE`: `POST /signout`, the gallery vote and
comment routes, every participant write, `POST /judge/evaluate/{project_id}` and
every organizer write.

The token is read from `X-CSRF-Token` or `X-CSRFToken`, or from `_csrf` or
`csrf_token` in the form body or JSON body, and compared with the session's token
using `hmac.compare_digest`. A mismatch raises `403 csrf_failed`, closes the
request **before** the handler runs, and appends `csrf.rejected` to the audit
ledger (`app/server.py:215`).

Two routes are deliberately exempt, and for the same reason: the caller has no
session yet, and the CSRF token lives in the session row, so there is nothing to
compare against.

| Route | Why it is exempt |
| --- | --- |
| `POST /signin` | The client is unauthenticated by definition. The password check still runs, and every rejection is audited and returns `401`. |
| `POST /fast-login` | Demonstration affordance. It is **disabled by default** and returns `404` unless `PORTAL_FAST_LOGIN=1`, so on a normal deployment the route behaves as if it does not exist. |

---

## 5. Authorization

### 5.1 The role gate

Roles are ordered `participant < judge < organizer < admin` (`app/auth.py:14`).
A route declares the roles it accepts; `admin` passes every check, and **no other
role is implied** — an organizer does not inherit judge access, and a judge does
not inherit participant access.

| Outcome | Web route | API route (`/api/…`, or `Accept: application/json`) |
| --- | --- | --- |
| No session | `303` to `/login?next=<path>` | `401 authentication_required` |
| Wrong role | `403 forbidden` | `403 forbidden` |
| Either case | `access.denied` appended to `audit_log` naming the attempted route | same |

### 5.2 A resource check, not a row id

Passing the role gate is not enough to reach another hackathon. Every
event-scoped handler resolves `{event_id}` or `{slug}` and then calls
`events.can_manage(user, event)` before it reads or writes a row. A user who
guesses `evt_02` while managing only `evt_01` gets:

* the refusal itself — `403 not_your_event` on a management page, `403` on a
  write;
* an `event.manage_refused` audit entry naming the user and the event;
* no partial write, because the transaction is never opened.

This is why the ten isolation tests in `tests/test_event_isolation.py` can assert
that an outsider cannot "borrow row ids from another event": there is no code
path in which a foreign `project_id`, `team_id` or `review_id` is accepted merely
because the caller holds the right role.

### 5.3 Admin is not hidden, and that is deliberate

An `admin` sees every hackathon, including ones they were never added to. The
role exists so a deployment whose only organizer account is lost can be
recovered; it does not model least privilege. On a shared install, treat admin
access as equivalent to database access.

---

## 6. Request hardening

### 6.1 Response headers, on every response

Applied in `PortalHandler.write()`, so they are also present on `4xx` and `5xx`
responses and on error pages (`app/server.py:167`):

| Header | Value |
| --- | --- |
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `same-origin` |
| `X-Frame-Options` | `DENY` |
| `Cache-Control` | `no-store` |

The CSP has no `'unsafe-inline'` and no `'unsafe-eval'`. That is affordable
because the codebase contains no inline `<style>` attribute, no inline `<script>`
and no inline event handler; the only script and stylesheet are `/static/app.js`
and `/static/app.css`.

### 6.2 Body size, method confusion and error disclosure

* A `Content-Length` above 2 MiB is refused with `413 payload_too_large` before
  the body is read (`MAX_BODY`, `app/server.py:23`).
* A path that exists only under a different verb is answered with `405` **and an
  `Allow` header**, never with a silent fallback (`app/http.py:330`).
* `Problem` exceptions become the status they carry. An unexpected exception
  becomes a generic `500 internal_error`: the traceback goes to `stderr` and to
  `audit_log` (`request.error`), never into the response body
  (`app/server.py:106`).
* `HEAD` is supported and its body is stripped before sending
  (`app/server.py:118`).

### 6.3 Static files

`serve_static()` runs before route matching, so an asset can never be shadowed by
a page route. It refuses, in this order (`app/server.py:240`):

1. any name containing `/`, `\` or `..`;
2. any resolved path that is not inside `app/views/static/` (containment check,
   not a prefix match on user input);
3. anything that is not a regular file — `404 not_found`, with no hint about what
   exists.

Served types come from a fixed extension allow-list (`.css`, `.js`, `.svg`,
`.png`, `.ico`, `.txt`, `.json`, `.woff2`); everything else is
`application/octet-stream` and is cached for 300 seconds.

### 6.4 Redirects

`util.safe_next()` accepts only same-origin relative targets: a value must start
with a single `/`, must not start with `//`, and must not contain a backslash.
Anything else falls back to `/`. This is what keeps `/login?next=…` and the
`/fast-login` redirect from becoming an open redirect (`app/util.py:105`).

---

## 7. Injection and output encoding

### 7.1 SQL

There is no ORM and no query builder. Every statement is written at the call site
it belongs to, and every value travels as a parameter tuple:

```python
db.insert("certificates", {...})          # becomes "INSERT INTO … VALUES (?, ?, …)"
db.update("sessions", {"last_seen_at": …}, "token_hash = ?", (hash,))
```

`db.insert()`, `db.update()` and `db.execute()` never interpolate a **value**
(`app/db.py:87`–`138`). The only string formatting into SQL anywhere in `app/` is
a table name in `boot.wipe()` and a column list in `db.update()`, both of which
take literals from the code and never from a request.

`PRAGMA foreign_keys = ON` is set on every connection, so a delete cascades
instead of leaving a dangling child row (`app/db.py:34`).

### 7.2 HTML

Views are string builders in `app/views/`. `views.ui.esc()` is
`html.escape(str(value), quote=True)`, with `None` becoming `""`
(`app/views/ui.py:12`). Project titles, team names, comments, email addresses and
audit summaries all pass through it, and attribute values are quoted.

There is no script sink either: `app/views/static/app.js` reads with
`textContent` and writes with `textContent`, so a hostile project title cannot
become markup even on the progressive-enhancement path.

### 7.3 CSV

`util.csv_cell()` quotes a cell only when it contains `,`, `"`, CR or LF, and
doubles embedded quotes (`app/util.py:57`). Standings exports are therefore
parseable by any RFC 4180 reader.

**Known gap — spreadsheet formula injection is not neutralised.** A cell that
starts with `=`, `+`, `-` or `@` is exported verbatim, so a participant-supplied
project title such as `=HYPERLINK(...)` would be treated as a formula if the file
is opened in Excel or LibreOffice. The mitigation is to prefix such cells or
import the CSV as text; it is not implemented here, and it is written down here
rather than left unstated.

---

## 8. Integrity: signatures, checksums, audit

### 8.1 Review signatures

When a review is submitted, its score is signed with HMAC-SHA256 over a canonical
message keyed by the install secret:

```
message   = "review|<review_id>|<project_id>|<judge_user_id>|<weighted_raw>"
signature = HMAC-SHA256(portal_secret, message)
```

`results.review_receipt()` re-derives the signature and reports
`verified: true|false`, so a score edited directly in the database can be shown to
disagree with its signature (`app/security.py:88`, `app/results.py:190`). This is
tamper evidence for the operator of that install — verification needs the same
`portal_secret`, and there is no public key, so it is not third-party
verification.

### 8.2 Published results

Publishing writes a JSON snapshot of the standings, computes
`SHA-256(rows_json)`, stores it with an incremented `revision_no`, and marks every
earlier publication `is_current = 0`. The public results page renders the snapshot
and never a live query, so a later database edit cannot silently change a
published leaderboard — it produces a new revision instead (`app/results.py:49`).

### 8.3 Certificates

A certificate `code` is the first 20 characters, upper-cased, of
`SHA-256("cert|<event_id>|<project_id>|<kind>" + portal_secret)`. It is unique in
the schema and recomputable by an organizer holding the same secret
(`app/results.py:158`).

### 8.4 Audit ledger

`audit.record()` inserts one row per event with `action`, `actor_id`, `event_id`,
`outcome`, a JSON `metadata` payload and a UTC timestamp — **inside the caller's
transaction**, so a crash after a write cannot lose the audit row for it
(`app/audit.py:16`). Refusals go through `audit.refused()`, which never raises, so
logging a refusal can never change the outcome of the refusal itself.

No route, form or UI updates or deletes an audit row: the application only ever
inserts and selects (`app/audit.py`). The single exception is `boot.wipe()`, which
deletes every competition row — including `audit_log` — when an operator
explicitly runs `--reset` or `PORTAL_RESET=1` (`app/boot.py:645`). Treat a reset
as the end of that install's evidence trail.

---

## 9. The install secret

| Property | Detail |
| --- | --- |
| Generation | `secrets.token_hex(32)` on first use — 256 bits |
| Storage | row `settings.key = 'portal_secret'`, generated once and reused (`app/security.py:79`) |
| Survives | container restarts, `docker compose down`, and `--reset` (`boot.wipe()` keeps `settings`) |
| Loss | the ability to verify old signatures and to recompute old certificate codes goes with it |
| Exposure | any process that can read the database can forge signatures and recompute certificate codes |

The secret lives in the same file as the data, on purpose. The alternative — an
environment variable — is easier to leak through `docker compose config` and easy
to lose when a container is rebuilt, which would silently invalidate every
signature. The consequence is stated plainly: **database read access equals
signature-forging access.** Backups therefore deserve the same care as the portal
itself; see [OPERATIONS.md](OPERATIONS.md).

There is no supported secret-rotation command. Rewriting the `settings` row
invalidates every existing review signature and certificate code at once, which is
why it is not offered as a one-click action.

---

## 10. Threat table

| Threat | Control | Residual risk |
| --- | --- | --- |
| Password-database theft | scrypt or PBKDF2 with per-user salts; sessions stored only as hashes | Offline cracking of a weak *demo* password is possible — demo passwords are published on purpose |
| Session theft from the database | tokens stored hashed, never raw | A stolen **browser cookie** is a valid session until it expires; there is no device binding |
| Session interception on the wire | none — plain HTTP by default, no `Secure` flag | Real. Any LAN observer can replay a cookie. Terminate TLS at a proxy before using this on an untrusted network |
| Cross-site request forgery | per-session token, `hmac.compare_digest`, audited refusal, no query-string writes | None known |
| Cross-site scripting | full output escaping, `default-src 'self'`, no inline script or handler to relax | None known |
| SQL injection | parameterised statements only | None known |
| Path traversal on `/static/` | `..`, separator and containment checks | None known |
| Privilege escalation between roles | explicit role sets; `admin` is the only bypass; per-event membership | By design, an admin is omnipotent |
| Cross-tenant data access | `event_id` scoping, `can_manage()`, audited refusals | None known; covered by ten tests |
| Score tampering after the fact | HMAC signatures, append-only `review_revisions`, append-only audit | An operator with database access can rewrite the rows **and** re-sign them |
| Result tampering after publication | frozen snapshot, SHA-256 checksum, monotonic revisions | Same operator caveat |
| Forged audit attribution | actor comes from the resolved session, never from the request body | Client IP is the socket peer; behind a reverse proxy it is the proxy's address, because `X-Forwarded-For` is not read |
| Denial of service | 2 MiB body cap, fixed-size responses, one request per thread | No rate limiting, no connection cap, no queue: a flood is a flood |
| Credential stuffing | every failure audited, one generic error message | No lockout and no throttling |

---

## 11. Explicitly out of scope

Nothing in this list is a surprise discovered by a reviewer; each item is a scope
decision with its reason.

| Not defended | Why, and what to do about it |
| --- | --- |
| Transport encryption | The portal is designed to run on loopback or a private LAN without a certificate. Put TLS in front of it for anything else. Without that, cookies travel in clear text. |
| `Secure` / `__Host-` cookie prefixes | Omitted for the same reason (`app/server.py:189` supports the flag; nothing sets it). |
| Request rate limiting | `security.rate_limit()` is implemented against the `rate_limits` table but **has no caller**, so no route is throttled. Sign-in, voting and comments are the places a deployment would want it. |
| Account lockout, MFA, SSO | No such features exist. Accounts are seeded by the operator; there is no self-service anything. |
| Password reset / email | No mail is sent and no outbound connection is opened, so there is no reset flow. Recover an account by editing the row or re-seeding. |
| Multi-factor or device binding | Not implemented. |
| Encryption at rest | The SQLite file is plaintext, including the `settings.portal_secret` row. Use filesystem or volume encryption if the host is shared. |
| Hardening against a hostile administrator | `admin` is omnipotent and the operator owns the database. There is no separation of duties inside one install. |
| Malicious, *authorised* organizer behaviour | An organizer can legitimately change their event's rubric, settings, assignments and publications. The audit ledger records what changed, but it does not prevent it. |
| Denial of service, load shedding | No throttling, no queue, one unbounded thread per connection. |
| File uploads | Out of scope by design: submissions carry URLs (`repo_url`, `demo_url`), so there is no upload path to secure. |
| Third-party verification of results | Signatures and certificate codes need the install's own secret. There is no public key and no published verification endpoint. |
| Webhook delivery | The tables exist; dispatch is disabled to honour the zero-outbound-network constraint. |
| Renaming or hardening the base image further | Up to the operator. The image is `python:3.12-alpine`, runs as `portal`, is `read_only` with `cap_drop: [ALL]` and `no-new-privileges`. |

---

## 12. Pre-deployment checklist

For a demonstration on a laptop, the defaults are the intent. For anything with a
real audience:

1. **Leave `PORTAL_FAST_LOGIN` unset.** It mints a session for a fixture account
   without a password. On a demo box it is a convenience; anywhere else it is an
   authentication bypass, and the route 404s when the flag is off.
2. **Change the demo passwords** or re-seed with `PORTAL_DEMO_PASSWORD` and
   `PORTAL_FIXTURE_PASSWORD` set before the first boot.
3. **Terminate TLS at a reverse proxy** and keep the portal bound to
   `127.0.0.1` (`LOCKDOWN_BIND`) behind it.
4. **Treat the volume as the crown jewels.** It holds the data *and* the signing
   secret; see [OPERATIONS.md](OPERATIONS.md) for backup and restore.
5. **Keep the container read-only.** `read_only: true`, `cap_drop: [ALL]`,
   `no-new-privileges` and a single writable volume are already in
   `docker-compose.yml`.
6. **Plan for resets.** `--reset` and `down -v` delete the audit ledger, and the
   delete is not reversible.
7. **Do not proxy the portal through a path prefix.** The application generates
   absolute paths (`PORTAL_BASE_URL`, `/static/…`) and does not read
   `X-Forwarded-Prefix`.

---

## 13. Related documents

| Document | Why it is relevant here |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The request lifecycle and the guards, module by module |
| [FEATURES.md](FEATURES.md) | The guard and CSRF flag declared on every one of the 58 routes |
| [DATA-MODEL.md](DATA-MODEL.md) | Where `sessions`, `audit_log`, `settings` and `result_publications` live |
| [JUDGING.md](JUDGING.md) | What the signed numbers mean, before they are signed |
| [TESTING.md](TESTING.md) | The probes that demonstrate the refusals described above |
| [TIER-MATRIX.md](TIER-MATRIX.md) | Which security-relevant behaviours the official harness verified |
| [OPERATIONS.md](OPERATIONS.md) | Backups, resets, TLS termination and the volume |




