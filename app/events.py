"""Event domain logic: stages, windows, and the rules that read from them.

The stage pipeline is derived from the event's dates rather than stored as
free-floating state, which means the portal can never show "submission open"
while the API refuses a submission for another reason: both read
`submission_window()`.

  registration -> team formation -> submission -> judge assignment
               -> review & scoring -> results publication
"""

from __future__ import annotations

from . import db, http, timeutil, util

STAGE_SEQUENCE = (
    ("registration", "Registration", "Accounts open. Teams may be created.",
     "registration_open", "registration_close"),
    ("team_formation", "Team formation", "Invite links fill the rosters.",
     "registration_close", "team_formation_close"),
    ("submission", "Submission", "Draft, edit and finalise the project.",
     "submissions_open", "submissions_close"),
    ("judge_assignment", "Judge assignment", "Organizers invite judges and hand out work.",
     "submissions_close", "judging_open"),
    ("review", "Review and scoring", "Judges score assigned submissions.",
     "judging_open", "judging_close"),
    ("results", "Results publication", "Rankings are frozen and published.",
     "judging_close", "results_publish_at"),
)


def primary_event():
    """The official fixture event: lowest seq, published, seeded first."""
    return db.one("""SELECT * FROM events WHERE status != 'draft'
                      ORDER BY seq ASC, created_at ASC LIMIT 1""")


def get_event(reference: str):
    if not reference:
        return None
    return db.one("SELECT * FROM events WHERE id = ? OR slug = ?", (reference, reference))


def require_event(reference: str):
    event = get_event(reference)
    if event is None:
        raise http.Problem(404, "event_not_found", "No such event.")
    return event


def list_events(*, include_drafts: bool = False, limit: int = 50):
    clause = "" if include_drafts else "WHERE status != 'draft'"
    return db.query("SELECT * FROM events %s ORDER BY seq ASC, created_at ASC LIMIT ?"
                    % clause, (limit,))


# --- event membership: who may manage which hackathon --------------------
#
# `events.created_by` records the founder. `event_organizers` records everyone
# trusted with the event afterwards. Admin bypasses both. Nothing in the
# frontend decides this: every organizer handler calls `require_manage` before
# it reads or writes an event-scoped row, so a hand-edited URL or a forged
# `event=` parameter cannot reach another hackathon's data.

COVER_TONES = ("ink", "red", "blue", "green", "amber")


def organizers_of(event_id: str) -> list[dict]:
    return db.dicts(db.query(
        """SELECT eo.*, u.name, u.email, u.role AS user_role
             FROM event_organizers eo
             JOIN users u ON u.id = eo.user_id
            WHERE eo.event_id = ? ORDER BY eo.role DESC, u.name ASC""", (event_id,)))


def add_organizer(event_id: str, user_id: str, *, role: str = "organizer",
                  added_by: str | None = None) -> bool:
    """Idempotent: re-adding the same person is not an error."""
    if not user_id:
        return False
    if db.exists("SELECT id FROM event_organizers WHERE event_id = ? AND user_id = ?",
                 (event_id, user_id)):
        return False
    db.insert("event_organizers", {
        "id": util.new_id("evo"), "event_id": event_id, "user_id": user_id,
        "role": role if role in ("owner", "organizer") else "organizer",
        "added_by": added_by, "added_at": timeutil.now_iso()})
    return True


def member_role(user, event):
    """'owner' | 'organizer' | '' for this user in this event."""
    if not user or event is None:
        return ""
    row = db.one("SELECT role FROM event_organizers WHERE event_id = ? AND user_id = ?",
                 (event["id"], user["id"]))
    if row is not None:
        return row["role"]
    if event["created_by"] and event["created_by"] == user["id"]:
        return "owner"
    return ""


def can_manage(user, event) -> bool:
    """Admin manages everything; an organizer manages the events they belong to."""
    if user is None or event is None:
        return False
    if user["role"] == "admin":
        return True
    if user["role"] != "organizer":
        return False
    return bool(member_role(user, event))


def manageable_events(user, *, include_archived: bool = True) -> list[dict]:
    """The hackathons this user may operate, oldest first. Empty for everyone else."""
    if user is None:
        return []
    if user["role"] == "admin":
        rows = list_events(include_drafts=True, limit=200)
    elif user["role"] == "organizer":
        rows = db.query(
            """SELECT e.* FROM events e
                LEFT JOIN event_organizers eo
                       ON eo.event_id = e.id AND eo.user_id = ?
               WHERE e.created_by = ? OR eo.user_id = ?
               ORDER BY e.seq ASC, e.created_at ASC""",
            (user["id"], user["id"], user["id"]))
    else:
        return []
    events = [dict(row) for row in rows]
    if not include_archived:
        events = [item for item in events if item["status"] != "archived"]
    return events


def visible_events(*, include_drafts: bool = False, limit: int = 100) -> list[dict]:
    """Events the public may see: published (or archived once something is final)."""
    clause = "" if include_drafts else "WHERE status IN ('published','archived')"
    return db.dicts(db.query(
        "SELECT * FROM events %s ORDER BY seq ASC, created_at ASC LIMIT ?" % clause,
        (limit,)))


def event_metrics(event) -> dict:
    """One event's headline numbers, for the directory and the management board.

    Every count is filtered by `event_id`, so two hackathons never share a row.
    """
    counts = event_counts(event["id"])
    submissions = counts["projects_submitted"]
    reviews = counts["reviews_submitted"]
    required = db.scalar(
        "SELECT COALESCE(SUM(COALESCE(e.target_reviews, 3)), 0) FROM events e WHERE e.id = ?",
        (event["id"],), 0) or 0
    # Judging progress is measured against the work actually handed out, which is
    # the number the organizer can act on.
    judging_total = counts["assignments"] or 0
    publication = results_published(event)
    stage = current_stage(event)
    return {
        **counts,
        "projects": submissions,
        "stage": stage["name"] if stage else "",
        "stage_key": stage["key"] if stage else "",
        "stage_state": stage["state"] if stage else "",
        "judging_total": judging_total,
        "judging_done": reviews,
        "judging_percent": round(100.0 * reviews / judging_total, 1) if judging_total else 0.0,
        "target_reviews": required,
        "results_published": publication is not None,
        "results_revision": (publication or {}).get("revision_no") or 0,
        "results_at": (publication or {}).get("published_at") or event["results_publish_at"],
        "organizers": db.scalar(
            "SELECT COUNT(*) FROM event_organizers WHERE event_id = ?", (event["id"],), 0),
    }


def cover_tone(event) -> str:
    tone = (event.get("cover_tone") or "ink").strip().lower()
    return tone if tone in COVER_TONES else "ink"


def gallery_is_visible(event) -> bool:
    return bool(event) and event["status"] in ("published", "archived") \
        and bool(event.get("gallery_visible", 1))


def results_are_visible(event) -> bool:
    return bool(event) and event["status"] in ("published", "archived") \
        and bool(event.get("results_visible", 1))


def default_event_for(user=None, requested: str = ""):
    """Which event does an unqualified action apply to?

    An explicit request wins. Otherwise the primary (official, fixture-seeded)
    event, which is the *closed* one, so a bare POST can never quietly land in a
    practice event that happens to be open.
    """
    if requested:
        return require_event(requested)
    event = primary_event()
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    return event


def stages(event) -> list[dict]:
    rows = db.query("SELECT * FROM event_stages WHERE event_id = ? ORDER BY seq", (event["id"],))
    return [dict(row) for row in rows]


def stage_definitions() -> tuple:
    return STAGE_SEQUENCE


def _window_bounds(event, key: str):
    for stage_key, _name, _desc, opens_field, closes_field in STAGE_SEQUENCE:
        if stage_key == key:
            return event[opens_field], event[closes_field]
    return None, None


def window_state(event, key: str, now: str | None = None) -> str:
    """'not_configured' | 'upcoming' | 'open' | 'closed' for one stage window."""
    if key == "results":
        opens_at, closes_at = None, event["results_publish_at"]
    else:
        opens_at, closes_at = _window_bounds(event, key)
    stamp = now or timeutil.now_iso()
    if not opens_at and not closes_at:
        return "not_configured"
    if opens_at and stamp < opens_at:
        return "upcoming"
    if closes_at and stamp > closes_at:
        return "closed"
    return "open"



def stage_pipeline(event, now: str | None = None) -> list[dict]:
    """The six stages with dates, state and a human label for each."""
    stamp = now or timeutil.now_iso()
    published = results_published(event)
    pipeline, current_set = [], False
    for index, (key, name, description, _o, _c) in enumerate(STAGE_SEQUENCE, start=1):
        opens_at, closes_at = _window_bounds(event, key)
        if key == "results":
            if published:
                state = "published"
            else:
                state = "upcoming" if (closes_at or "") > stamp else "closed"
        else:
            state = window_state(event, key, stamp)
        pipeline.append({
            "seq": index, "key": key, "name": name, "description": description,
            "opens_at": opens_at, "closes_at": closes_at, "state": state,
            "is_current": False,
        })
    for stage in pipeline:
        if stage["state"] == "open":
            stage["is_current"] = True
            current_set = True
            break
    if not current_set:
        for stage in reversed(pipeline):
            if stage["state"] in ("closed", "published"):
                stage["is_current"] = True
                break
    return pipeline


def current_stage(event, now: str | None = None) -> dict:
    pipeline = stage_pipeline(event, now)
    for stage in pipeline:
        if stage["is_current"]:
            return stage
    return pipeline[-1]


def next_stage(event, now: str | None = None) -> dict | None:
    pipeline = stage_pipeline(event, now)
    for index, stage in enumerate(pipeline):
        if stage["state"] == "upcoming":
            return stage
        if stage["is_current"] and index + 1 < len(pipeline):
            following = pipeline[index + 1]
            if following["state"] == "upcoming":
                return following
    return None


def current_deadline(event, now: str | None = None):
    """The next date that matters, with the thing it is a deadline for."""
    stamp = now or timeutil.now_iso()
    candidates = [
        (event["submissions_close"], "Submissions close", "submission"),
        (event["judging_close"], "Judging closes", "review"),
        (event["results_publish_at"], "Results published", "results"),
        (event["team_formation_close"], "Team formation closes", "team_formation"),
        (event["registration_close"], "Registration closes", "registration"),
    ]
    future = sorted((w, label, key) for w, label, key in candidates if w and w >= stamp)
    if future:
        when, label, key = future[0]
        return {"at": when, "label": label, "key": key, "passed": False,
                "relative": timeutil.relative(when)}
    past = sorted(((w, label, key) for w, label, key in candidates if w), reverse=True)
    if past:
        when, label, key = past[0]
        return {"at": when, "label": label + " (passed)", "key": key, "passed": True,
                "relative": timeutil.relative(when)}
    return None


def results_published(event) -> dict | None:
    row = db.one("""SELECT * FROM result_publications
                     WHERE event_id = ? ORDER BY revision_no DESC LIMIT 1""", (event["id"],))
    return dict(row) if row else None


def submission_window(event):
    """(allowed, code, message, status) — the single answer to 'can we submit?'"""
    stamp = timeutil.now_iso()
    if event["status"] == "draft":
        return (False, "event_not_published",
                "This event is still a draft, so submissions are not open.", 403)
    if not event["submissions_open"] and not event["submissions_close"]:
        return (False, "submissions_not_configured",
                "The organizers have not set a submission window for this event.", 403)
    if event["submissions_open"] and stamp < event["submissions_open"]:
        return (False, "submissions_not_open",
                "Submissions for %s open on %s." % (
                    event["name"], timeutil.human(event["submissions_open"])), 403)
    if event["submissions_close"] and stamp > event["submissions_close"]:
        return (False, "submissions_closed",
                "Submissions for %s closed at %s. Editing and final submission are locked." % (
                    event["name"], timeutil.human(event["submissions_close"])), 403)
    return (True, "open", "Submissions are open.", 200)


def require_submission_window(event):
    allowed, code, message, status = submission_window(event)
    if not allowed:
        raise http.Problem(status, code, message,
                           "Deadline enforcement is checked in the API, not in the page.")
    return True


def registration_window(event):
    stamp = timeutil.now_iso()
    if event["status"] == "draft":
        return (False, "event_not_published", "This event is not published yet.", 403)
    if event["registration_close"] and stamp > event["registration_close"]:
        return (False, "registration_closed",
                "Registration closed on %s." % timeutil.human(event["registration_close"]), 403)
    return (True, "open", "Registration is open.", 200)


def editing_allowed(event, project=None) -> tuple[bool, str]:
    allowed, _code, _message, _status = submission_window(event)
    if allowed:
        return True, "open"
    if project is not None and project["status"] == "submitted":
        return False, "locked"
    return False, "closed"



def event_counts(event_id: str) -> dict:
    return {
        "teams": db.scalar("SELECT COUNT(*) FROM teams WHERE event_id = ?", (event_id,), 0),
        "participants": db.scalar(
            """SELECT COUNT(DISTINCT tm.user_id) FROM team_members tm
                 JOIN teams t ON t.id = tm.team_id WHERE t.event_id = ?""", (event_id,), 0),
        "projects_submitted": db.scalar(
            "SELECT COUNT(*) FROM projects WHERE event_id = ? AND status = 'submitted'",
            (event_id,), 0),
        "projects_draft": db.scalar(
            "SELECT COUNT(*) FROM projects WHERE event_id = ? AND status = 'draft'",
            (event_id,), 0),
        "judges": db.scalar(
            "SELECT COUNT(DISTINCT judge_user_id) FROM assignments WHERE event_id = ?",
            (event_id,), 0),
        "assignments": db.scalar(
            "SELECT COUNT(*) FROM assignments WHERE event_id = ? AND status != 'revoked'",
            (event_id,), 0),
        "reviews_submitted": db.scalar(
            "SELECT COUNT(*) FROM reviews WHERE event_id = ? AND status IN ('submitted','finalized')",
            (event_id,), 0),
        "reviews_draft": db.scalar(
            "SELECT COUNT(*) FROM reviews WHERE event_id = ? AND status = 'draft'",
            (event_id,), 0),
        "tracks": db.scalar("SELECT COUNT(*) FROM tracks WHERE event_id = ?", (event_id,), 0),
        "prizes": db.scalar("SELECT COUNT(*) FROM prizes WHERE event_id = ?", (event_id,), 0),
        "votes": db.scalar("SELECT COUNT(*) FROM votes WHERE event_id = ?", (event_id,), 0),
        "comments": db.scalar(
            """SELECT COUNT(*) FROM comments c JOIN projects p ON p.id = c.project_id
                WHERE p.event_id = ? AND c.is_hidden = 0""", (event_id,), 0),
    }


def assignments_for_judge(event_id: str, judge_user_id: str):
    return db.query(
        """SELECT a.*, p.title, p.status AS project_status, p.track_id AS project_track,
                  t.name AS team_name, t.id AS team_id,
                  r.id AS review_id, r.status AS review_status,
                  r.submitted_at, r.finalized_at, r.weighted_raw
             FROM assignments a
             JOIN projects p ON p.id = a.project_id
             JOIN teams t ON t.id = p.team_id
             LEFT JOIN reviews r ON r.project_id = a.project_id
                                AND r.judge_user_id = a.judge_user_id
            WHERE a.event_id = ? AND a.judge_user_id = ? AND a.status != 'revoked'
            ORDER BY (r.status IN ('submitted','finalized')) ASC, p.title ASC""",
        (event_id, judge_user_id))


def judge_progress(event_id: str, judge_user_id: str) -> dict:
    assigned = db.scalar(
        "SELECT COUNT(*) FROM assignments WHERE event_id = ? AND judge_user_id = ? "
        "AND status != 'revoked'", (event_id, judge_user_id), 0)
    completed = db.scalar(
        """SELECT COUNT(*) FROM reviews r JOIN assignments a
                ON a.project_id = r.project_id AND a.judge_user_id = r.judge_user_id
            WHERE r.event_id = ? AND r.judge_user_id = ? AND r.status IN ('submitted','finalized')
              AND a.status != 'revoked'""", (event_id, judge_user_id), 0)
    drafts = db.scalar(
        "SELECT COUNT(*) FROM reviews WHERE event_id = ? AND judge_user_id = ? "
        "AND status = 'draft'", (event_id, judge_user_id), 0)
    return {"assigned": assigned, "completed": completed, "drafts": drafts,
            "pending": max(0, assigned - completed),
            "percent": round(100.0 * completed / assigned, 1) if assigned else 0.0}
