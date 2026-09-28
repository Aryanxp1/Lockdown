"""Result publication, stage advancement, certificates and review receipts.

Everything here is append-only on purpose:

  * publishing again adds a new numbered revision instead of editing the old
    one, so a published ranking can always be reproduced and compared;
  * advancement decisions are rows, not flags, so a later decision cannot erase
    an earlier one;
  * a certificate or a review receipt is a signed statement that can be checked
    offline with the portal's own secret.
"""

from __future__ import annotations

import hashlib

from . import audit, db, scoring, security, timeutil, util

MAX_CERTIFICATES = 500


def _row_from_project(project) -> dict:
    return {
        "rank": project.get("published_rank"),
        "project_id": project["project_id"],
        "title": project["title"],
        "team": project["team_name"],
        "track": project["track_name"],
        "score": project["normalized_mean"],
        "raw_score": project["raw_mean"],
        "reviews": project["review_count"],
        "coverage": project["coverage"],
        "votes": project.get("votes", 0),
        "flags": project["flags"],
    }


def public_rows(event, *, board=None, limit: int = 0) -> list[dict]:
    """The published shape of a result row: no judge identities, only counts."""
    board = board or scoring.scoreboard(event)
    rows = [_row_from_project(project) for project in board["ranked"]
            if project["project_status"] == "submitted"]
    rows.sort(key=lambda item: (item["score"] is None, -(item["score"] or 0), item["title"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows[:limit] if limit else rows


def publish(event, *, actor=None, note: str = "", board=None) -> dict:
    """Freeze the current standings as a new, immutable revision."""
    board = board or scoring.scoreboard(event)
    rows = public_rows(event, board=board)
    revision = db.scalar("""SELECT COALESCE(MAX(revision_no), 0) FROM result_publications
                             WHERE event_id = ?""", (event["id"],), 0) + 1
    payload = db.json_text(rows)
    checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    publication_id = util.new_id("pub")
    with db.tx():
        db.update("result_publications", {"is_current": 0}, "event_id = ?", (event["id"],))
        db.insert("result_publications", {
            "id": publication_id, "event_id": event["id"], "revision_no": revision,
            "published_by": actor["id"] if actor else None,
            "published_at": timeutil.now_iso(), "methodology": board["formula"],
            "rows_json": payload, "checksum": checksum, "note": note, "is_current": 1})
        db.update("event_stages", {"status": "published", "published_at": timeutil.now_iso()},
                  "event_id = ? AND key = 'results'", (event["id"],))
    audit.record(action="results.published", entity_type="event", entity_id=event["id"],
                 summary="Published results revision %d (%d rows)" % (revision, len(rows)),
                 actor=actor,
                 after={"revision": revision, "checksum": checksum, "rows": len(rows)},
                 meta={"note": note})
    return {"revision": revision, "checksum": checksum, "rows": rows,
            "publication_id": publication_id, "published_at": timeutil.now_iso()}


def current_publication(event_id: str):
    row = db.one("""SELECT * FROM result_publications WHERE event_id = ?
                     ORDER BY revision_no DESC LIMIT 1""", (event_id,))
    return dict(row) if row else None


def publication_rows(publication) -> list[dict]:
    if not publication:
        return []
    return db.json_load(publication.get("rows_json"), []) or []


def publications(event_id: str):
    return db.query("""SELECT * FROM result_publications WHERE event_id = ?
                        ORDER BY revision_no DESC""", (event_id,))



def advance(event, decisions, *, actor=None, note: str = "",
            to_stage: str = "final") -> list[dict]:
    """Record advancement decisions. `decisions` is (project_id, decision, rank, score)."""
    recorded = []
    with db.tx():
        for project_id, decision, rank, score in decisions:
            if decision not in ("advanced", "eliminated", "waitlisted", "restored"):
                continue
            record = {
                "id": util.new_id("adv"), "event_id": event["id"], "project_id": project_id,
                "from_stage": "review", "to_stage": to_stage, "decision": decision,
                "rank_at_decision": rank, "score_at_decision": score, "note": note,
                "decided_by": actor["id"] if actor else None,
                "decided_at": timeutil.now_iso()}
            db.insert("advancements", record)
            recorded.append(record)
    if recorded:
        audit.record(action="stage.advancement", entity_type="event", entity_id=event["id"],
                     summary="Recorded %d advancement decisions into %s" % (len(recorded), to_stage),
                     actor=actor, after={"decisions": len(recorded), "to_stage": to_stage,
                                         "note": note})
    return recorded


def advancements(event_id: str, limit: int = 200):
    return db.query("""SELECT a.*, p.title, t.name AS team_name
                         FROM advancements a JOIN projects p ON p.id = a.project_id
                         JOIN teams t ON t.id = p.team_id
                        WHERE a.event_id = ? ORDER BY a.decided_at DESC LIMIT ?""",
                    (event_id, limit))


def project_decisions(event_id: str, project_id: str):
    return db.query("""SELECT * FROM advancements WHERE event_id = ? AND project_id = ?
                        ORDER BY decided_at DESC""", (event_id, project_id))


def certificate_payload(event, project, kind: str, rank) -> dict:
    return {"event": event["name"], "event_id": event["id"], "kind": kind,
            "project": project["title"], "project_id": project["project_id"],
            "team": project["team_name"], "track": project["track_name"],
            "rank": rank, "issued_at": timeutil.now_iso()[:10],
            "organizer": "Lockdown portal"}


def issue_certificates(event, *, actor=None, kinds=("participation", "winner")) -> list[dict]:
    """Issue one certificate per canonical submitted project. Idempotent."""
    board = scoring.scoreboard(event)
    issued = []
    with db.tx():
        for project in board["ranked"][:MAX_CERTIFICATES]:
            if project["project_status"] != "submitted":
                continue
            if project["published_rank"] <= 3 and "winner" in kinds:
                kind = "winner"
            elif "participation" in kinds:
                kind = "participation"
            else:
                continue
            if db.one("""SELECT id FROM certificates WHERE event_id = ? AND project_id = ?
                          AND kind = ?""", (event["id"], project["project_id"], kind)):
                continue
            rank = project["published_rank"] if kind == "winner" else None
            payload = certificate_payload(event, project, kind, rank)
            code = security.short_code("cert|%s|%s|%s" % (
                event["id"], project["project_id"], kind), 20)
            record = {"id": util.new_id("cert"), "event_id": event["id"],
                      "project_id": project["project_id"], "team_id": project["team_id"],
                      "kind": kind, "code": code,
                      "title": "%s certificate" % kind.capitalize(),
                      "payload_json": db.json_text(payload),
                      "issued_by": actor["id"] if actor else None,
                      "issued_at": timeutil.now_iso()}
            db.insert("certificates", record)
            issued.append(record)
    if issued:
        audit.record(action="certificates.issued", entity_type="event", entity_id=event["id"],
                     summary="Issued %d certificates" % len(issued), actor=actor,
                     after={"count": len(issued)})
    return issued


def certificate_by_code(code: str):
    return db.one("""SELECT c.*, p.title AS project_title, t.name AS team_name,
                            e.name AS event_name, e.slug AS event_slug
                       FROM certificates c LEFT JOIN projects p ON p.id = c.project_id
                       LEFT JOIN teams t ON t.id = c.team_id
                       JOIN events e ON e.id = c.event_id
                      WHERE c.code = ?""", ((code or "").strip().upper(),))


def certificate_signature(certificate) -> str:
    return security.sign("cert|%s|%s|%s" % (
        certificate["event_id"], certificate["project_id"], certificate["code"]))


def review_receipt(review_row) -> dict:
    """A verifiable, offline-checkable statement about one review."""
    message = "review|%s|%s|%s|%s" % (review_row["id"], review_row["project_id"],
                                      review_row["judge_user_id"], review_row["weighted_raw"])
    signature = review_row["signature"] or security.sign(message)
    return {"review_id": review_row["id"], "project_id": review_row["project_id"],
            "judge_user_id": review_row["judge_user_id"], "raw": review_row["weighted_raw"],
            "normalized": review_row["normalized"], "method": review_row["norm_method"],
            "signature": signature, "message": message,
            "verified": security.constant_time_eq(signature, security.sign(message)),
            "status": review_row["status"]}
