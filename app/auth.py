"""Sessions, login, and role checks.

Authorization lives here and in the per-handler resource checks. The frontend
never decides anything: templates only hide what the API would already refuse,
and every guard in this file raises `Problem(403, ...)` when it says no.
"""

from __future__ import annotations

import datetime as _dt

from . import config, db, http, security, timeutil

ROLE_ORDER = {"participant": 1, "judge": 2, "organizer": 3, "admin": 4}
ROLE_LABEL = {
    "participant": "Participant",
    "judge": "Judge",
    "organizer": "Organizer",
    "admin": "Administrator",
    "visitor": "Visitor",
}


def role_allows(role: str, allowed) -> bool:
    """Admin passes every check; nobody else is implied by another role."""
    if role == "admin":
        return True
    return role in allowed


def user_by_id(user_id: str):
    return db.one("SELECT * FROM users WHERE id = ?", (user_id,))


def user_by_email(email: str):
    return db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", ((email or "").strip(),))


def create_user(email: str, name: str, role: str, password: str | None, **extra) -> str:
    user_id = extra.pop("id", None) or ("usr_%s" % security.token_hash(email)[:10])
    values = {
        "id": user_id,
        "email": (email or "").strip(),
        "name": (name or email or "Unnamed").strip(),
        "role": role if role in ROLE_ORDER else "participant",
        "password_hash": security.hash_password(password) if password else None,
        "created_at": timeutil.now_iso(),
        "is_active": 1,
    }
    values.update(extra)
    db.insert("users", values)
    return user_id


def issue_session(user_row, *, label: str = "", token: str | None = None,
                  is_demo: bool = False, request: "http.Request | None" = None,
                  expires_at: str | None = None) -> tuple[str, str]:
    """Create a session row. Returns (raw_token, csrf_token)."""
    raw = token or security.random_token(24)
    csrf = security.random_token(16)
    expiry = expires_at or timeutil.iso(
        timeutil.now() + _dt.timedelta(days=config.SESSION_TTL_DAYS))
    db.insert("sessions", {
        "token_hash": security.token_hash(raw),
        "user_id": user_row["id"],
        "csrf_token": csrf,
        "label": label,
        "is_demo": 1 if is_demo else 0,
        "created_at": timeutil.now_iso(),
        "expires_at": expiry,
        "last_seen_at": timeutil.now_iso(),
        "ip": (request.client_ip if request else "") or "",
        "user_agent": ((request.headers.get("User-Agent") if request else "") or "")[:180],
    })
    return raw, csrf


def resolve(request: "http.Request") -> None:
    """Attach request.session and request.user when the request is signed in."""
    token = request.cookies.get(config.SESSION_COOKIE) or request.bearer_token()
    if not token:
        return
    row = db.one(
        """SELECT s.*, u.email, u.name, u.role, u.is_active, u.fixture_id
             FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?""", (security.token_hash(token),))
    if row is None or row["revoked_at"]:
        return
    if (row["expires_at"] or "") < timeutil.now_iso():
        return
    if not row["is_active"]:
        return
    request.session = dict(row)
    request.session["user_id"] = row["user_id"]
    request.user = {
        "id": row["user_id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "fixture_id": row["fixture_id"],
        "is_demo": bool(row["is_demo"]),
    }
    db.update("sessions", {"last_seen_at": timeutil.now_iso()},
              "token_hash = ?", (row["token_hash"],))


def start(request: "http.Request", response: "http.Response", user_row, *,
          label: str = "web", is_demo: bool = False) -> str:
    raw, _csrf = issue_session(user_row, label=label, is_demo=is_demo, request=request)
    response.set_cookie(config.SESSION_COOKIE, raw, httponly=True, samesite="Lax",
                        path="/", max_age=config.SESSION_TTL_DAYS * 86400)
    db.update("users", {"last_login_at": timeutil.now_iso()}, "id = ?", (user_row["id"],))
    return raw


def end(request: "http.Request", response: "http.Response") -> None:
    if request.session:
        db.update("sessions", {"revoked_at": timeutil.now_iso()},
                  "token_hash = ?", (request.session["token_hash"],))
    response.set_cookie(config.SESSION_COOKIE, "", httponly=True, samesite="Lax",
                        path="/", max_age=0)



def rotate_csrf(request: "http.Request") -> str:
    if not request.session:
        return ""
    token = security.random_token(16)
    db.update("sessions", {"csrf_token": token},
              "token_hash = ?", (request.session["token_hash"],))
    request.session["csrf_token"] = token
    return token


# --- guards -------------------------------------------------------------

def current_user(request: "http.Request"):
    if not request.user:
        raise http.Problem(401, "authentication_required",
                           "Sign in to continue.",
                           "This endpoint needs a session cookie or a bearer token.")
    return request.user


def require_role(request: "http.Request", *roles: str):
    user = current_user(request)
    if not role_allows(user["role"], frozenset(roles)):
        raise http.Problem(403, "forbidden",
                           "Your account does not have access to this.",
                           "Required role: %s. Your role: %s." % (
                               ", ".join(sorted(roles)),
                               ROLE_LABEL.get(user["role"], user["role"])))
    return user


def require_admin(request: "http.Request"):
    return require_role(request, "admin")


def csrf_ok(request: "http.Request") -> bool:
    if not request.session:
        return False
    return security.constant_time_eq(request.csrf_candidate(),
                                     request.session.get("csrf_token", ""))


def check_password(user_row, password: str) -> bool:
    return bool(user_row) and bool(user_row["is_active"]) and security.verify_password(
        user_row["password_hash"], password)


def is_staff(user) -> bool:
    return bool(user) and user["role"] in ("organizer", "admin")
