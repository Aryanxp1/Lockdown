"""Append-only audit trail.

Everything that changes a competition record or that a participant might later
dispute gets a row: event edits, team changes, submission and finalisation,
judge assignment, review submission, score edits, stage advancement, result
publication, exports and refused attempts.

Nothing in the portal updates or deletes rows in this table.
"""

from __future__ import annotations

from . import db, timeutil, util


def record(*, action: str, entity_type: str = "", entity_id: str = "",
           summary: str = "", outcome: str = "ok", before=None, after=None,
           request=None, actor=None, meta=None) -> str:
    user = actor
    if user is None and request is not None:
        user = getattr(request, "user", None)
    actor_id = user["id"] if user else None
    actor_label = user["email"] if user else "anonymous"
    actor_role = user["role"] if user else "visitor"
    if user and user.get("name"):
        actor_label = "%s <%s>" % (user["name"], user["email"])
    entry_id = util.new_id("aud")
    db.insert("audit_log", {
        "id": entry_id,
        "at": timeutil.now_iso(),
        "actor_id": actor_id,
        "actor_label": actor_label,
        "actor_role": actor_role,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id or "",
        "outcome": outcome,
        "summary": summary,
        "before_json": db.json_text(before) if before is not None else "",
        "after_json": db.json_text(after) if after is not None else "",
        "ip": (request.client_ip if request is not None else "") or "",
        "user_agent": ((request.headers.get("User-Agent") if request is not None else "") or "")[:180],
        "meta_json": db.json_text(meta or {}),
    })
    return entry_id


def refused(request, action: str, reason: str, entity_type: str = "", entity_id: str = "") -> None:
    """Audit a denied or rejected request. Never raises."""
    try:
        record(action=action, entity_type=entity_type, entity_id=entity_id,
               summary=reason, outcome="refused", request=request)
    except Exception:  # pragma: no cover - auditing must never break a response
        pass


def entries(limit: int = 100, *, action: str = "", entity_id: str = "",
            actor_id: str = "", outcome: str = "", since: str = ""):
    clauses, params = [], []
    if action:
        clauses.append("action LIKE ?")
        params.append(action + "%")
    if entity_id:
        clauses.append("entity_id = ?")
        params.append(entity_id)
    if actor_id:
        clauses.append("actor_id = ?")
        params.append(actor_id)
    if outcome:
        clauses.append("outcome = ?")
        params.append(outcome)
    if since:
        clauses.append("at >= ?")
        params.append(since)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(int(limit))
    return db.query("SELECT * FROM audit_log%s ORDER BY at DESC, rowid DESC LIMIT ?" % where,
                    params)


def stats():
    return {
        "total": db.scalar("SELECT COUNT(*) FROM audit_log", (), 0),
        "refused": db.scalar("SELECT COUNT(*) FROM audit_log WHERE outcome = 'refused'", (), 0),
        "last_at": db.scalar("SELECT MAX(at) FROM audit_log", (), ""),
    }


def to_csv(rows) -> str:
    lines = ["at,actor,role,action,entity_type,entity_id,outcome,summary,ip"]
    for row in rows:
        lines.append(util.csv_row([row["at"], row["actor_label"], row["actor_role"],
                                   row["action"], row["entity_type"], row["entity_id"],
                                   row["outcome"], row["summary"], row["ip"]]))
    return "\n".join(lines) + "\n"
