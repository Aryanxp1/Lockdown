"""All HTTP route definitions and handlers for Lockdown.

Two rules keep this file honest:

  * every route declares its own guard (`public=`, `roles=`, `csrf=`) and the
    server enforces it before the handler runs, so a new endpoint cannot forget
    authorization;
  * handlers delegate every decision to the module the rest of the portal uses
    (`events.submission_window`, `scoring.scoreboard`, `results.publish`), so a
    page and its API twin can never disagree about whether something is allowed.

Views are pure string builders in `app/views/`; nothing here writes HTML.
"""

from __future__ import annotations

import urllib.parse

from . import (audit, auth, config, db, eventadmin, events as events_mod, http,
               results as results_mod, scoring, seed as fixtures_seed, security,
               timeutil, util)
from .views import (
    audit_trail,
    evaluation_form,
    event_assignments_page,
    event_directory,
    event_form,
    event_judges_page,
    event_overview,
    event_page,
    event_results_page,
    event_reviews_page,
    event_roster_page,
    event_settings_page,
    event_stages_page,
    gallery as gallery_view,
    judge_dashboard,
    judges_roster,
    landing,
    manage_home,
    participant_dashboard,
    project_detail as project_detail_view,
    project_form,
    render_shell,
    results_directory,
    results_leaderboard,
    results_scope_note,
    signin_form,
    submissions_list,
)

# The official fixture event holds 41 projects. A page size that fits them all
# keeps the exhibition browsable (and checkable) without pagination arithmetic.
GALLERY_PAGE_SIZE = 48
STAFF_ROLES = ["organizer", "admin"]
ANY_ROLE = ["participant", "judge", "organizer", "admin"]


def build_routes() -> http.Router:
    r = http.Router()

    # --- public pages ---------------------------------------------------
    r.get("/", handle_landing, public=True)
    r.get("/gallery", handle_gallery, public=True)
    r.get("/projects", handle_gallery, public=True)  # spec alias for the gallery
    r.get("/gallery/{project_id}", handle_project_detail, public=True)
    r.get("/results", handle_results, public=True)

    # --- the hackathon archive ------------------------------------------
    # An install is a shelf of competitions: the directory lists them, and each
    # one has its own cover, gallery and ledger. Nothing here needs an account.
    r.get("/events", handle_events_directory, public=True)
    r.get("/events/{slug}", handle_event_page, public=True)
    r.get("/events/{slug}/gallery", handle_event_gallery, public=True)
    r.get("/events/{slug}/results", handle_event_results, public=True)

    # --- sessions -------------------------------------------------------
    r.get("/signin", handle_signin_page, public=True)
    r.get("/login", handle_signin_page, public=True)
    # The sign-in POST cannot require a CSRF token: the visitor has no session
    # yet, so there is nothing to compare a token against.
    r.post("/signin", handle_signin, public=True)
    r.post("/signout", handle_signout, public=True, csrf=True)
    r.post("/fast-login", handle_fast_login, public=True)
    r.get("/fast-login", handle_fast_login, public=True)

    # --- community actions ----------------------------------------------
    r.post("/gallery/{project_id}/vote", handle_vote, roles=ANY_ROLE, csrf=True)
    r.post("/gallery/{project_id}/comment", handle_comment, roles=ANY_ROLE, csrf=True)

    # --- participant ----------------------------------------------------
    r.get("/participant", handle_participant_dashboard, roles=["participant", "admin"])
    r.post("/participant/team/create", handle_participant_team_create,
           roles=["participant", "admin"], csrf=True)
    r.get("/participant/project/new", handle_participant_project_new,
          roles=["participant", "admin"])
    r.get("/projects/new", handle_participant_project_new,
          roles=["participant", "admin"])  # spec alias
    r.post("/participant/project/new", handle_participant_project_save,
           roles=["participant", "admin"], csrf=True)
    r.post("/projects/new", handle_participant_project_save,
           roles=["participant", "admin"], csrf=True)  # spec alias
    r.get("/participant/project/edit", handle_participant_project_edit,
          roles=["participant", "admin"])
    r.post("/participant/project/edit", handle_participant_project_save,
           roles=["participant", "admin"], csrf=True)

    # --- judge ----------------------------------------------------------
    r.get("/judge", handle_judge_dashboard, roles=["judge", "admin"])
    r.get("/judge/assignments", handle_judge_dashboard, roles=["judge", "admin"])
    r.get("/judge/evaluate/{project_id}", handle_judge_evaluate_page,
          roles=["judge", "admin"])
    r.post("/judge/evaluate/{project_id}", handle_judge_evaluate_save,
           roles=["judge", "admin"], csrf=True)

    # --- organizer ------------------------------------------------------
    # `/organizer` is the shelf: the hackathons this caller may operate.
    r.get("/organizer", handle_manage_home, roles=STAFF_ROLES)
    r.get("/organizer/events/new", handle_event_new, roles=STAFF_ROLES)
    r.post("/organizer/events/new", handle_event_create, roles=STAFF_ROLES, csrf=True)

    # One hackathon at a time. Every handler below resolves `{event_id}` and
    # checks `events.can_manage` before it reads or writes a row, so the URL
    # alone never grants access to somebody else's event.
    r.get("/organizer/events/{event_id}", handle_event_manage, roles=STAFF_ROLES)
    r.get("/organizer/events/{event_id}/stages", handle_event_stages, roles=STAFF_ROLES)
    r.post("/organizer/events/{event_id}/stages", handle_event_stage_add,
           roles=STAFF_ROLES, csrf=True)
    r.post("/organizer/events/{event_id}/stages/remove", handle_event_stage_remove,
           roles=STAFF_ROLES, csrf=True)
    r.get("/organizer/events/{event_id}/teams", handle_event_teams, roles=STAFF_ROLES)
    r.get("/organizer/events/{event_id}/submissions", handle_event_submissions,
          roles=STAFF_ROLES)
    r.get("/organizer/events/{event_id}/judges", handle_event_judges, roles=STAFF_ROLES)
    r.post("/organizer/events/{event_id}/judges", handle_event_judge_invite,
           roles=STAFF_ROLES, csrf=True)
    r.get("/organizer/events/{event_id}/assignments", handle_event_assignments,
          roles=STAFF_ROLES)
    r.post("/organizer/events/{event_id}/assignments", handle_event_assign,
           roles=STAFF_ROLES, csrf=True)
    r.post("/organizer/events/{event_id}/assignments/revoke", handle_event_unassign,
           roles=STAFF_ROLES, csrf=True)
    r.get("/organizer/events/{event_id}/reviews", handle_event_reviews, roles=STAFF_ROLES)
    r.get("/organizer/events/{event_id}/results", handle_event_results_page,
          roles=STAFF_ROLES)
    r.post("/organizer/events/{event_id}/results", handle_event_publish,
           roles=STAFF_ROLES, csrf=True)
    r.get("/organizer/events/{event_id}/audit", handle_event_audit, roles=STAFF_ROLES)
    r.get("/organizer/events/{event_id}/settings", handle_event_settings,
          roles=STAFF_ROLES)
    r.post("/organizer/events/{event_id}/settings", handle_event_settings_save,
           roles=STAFF_ROLES, csrf=True)
    r.post("/organizer/events/{event_id}/organizers", handle_event_organizer_add,
           roles=STAFF_ROLES, csrf=True)
    r.post("/organizer/events/{event_id}/organizers/remove",
           handle_event_organizer_remove, roles=STAFF_ROLES, csrf=True)

    # The shortcuts organizers already had. They act on the hackathon the caller
    # is working in, and refuse that event when the caller does not manage it.
    r.get("/organizer/submissions", handle_organizer_submissions, roles=STAFF_ROLES)
    r.get("/organizer/judges", handle_organizer_judges, roles=STAFF_ROLES)
    r.get("/organizer/audit", handle_organizer_audit, roles=STAFF_ROLES)
    r.post("/organizer/publish", handle_organizer_publish, roles=STAFF_ROLES, csrf=True)

    # --- APIs and the endpoints the DOGFOOD acceptance suite reads -------
    # A judge may read this, but only ever their own rows (see the handler).
    r.get("/api/judge/scores", handle_api_judge_scores,
          roles=["judge", "organizer", "admin"])
    r.get("/api/export.csv", handle_api_export_csv, roles=STAFF_ROLES)
    r.get("/organizer/export", handle_api_export_csv, roles=STAFF_ROLES)

    return r


# --- shared helpers ---------------------------------------------------------

def _csrf(req: http.Request) -> str:
    return (req.session or {}).get("csrf_token", "")


def _event_row(row):
    """sqlite3.Row has no .get(); views and audit payloads want plain dicts."""
    return dict(row) if row is not None else None


def _page_number(req: http.Request, name: str = "page") -> int:
    return max(1, util.as_int(req.q(name, "1"), 1) or 1)


def _actor(user) -> dict | None:
    """`audit.record` wants a plain mapping it can index and call .get() on."""
    return dict(user) if user else None


def _decorate_projects(rows) -> list[dict]:
    """Add the display-only fields the templates read (tags list, track name)."""
    projects = [dict(row) for row in rows]
    for project in projects:
        project["tags"] = util.tags_to_list(project.get("tags"))
        project["track"] = project.get("track_name") or "General"
        project["review_count"] = project.get("review_count") or 0
        project["vote_count"] = project.get("vote_count") or 0
    return projects


PROJECT_SELECT = """
SELECT p.*, t.name AS team_name, tr.name AS track_name,
       (SELECT COUNT(*) FROM votes v WHERE v.project_id = p.id) AS vote_count,
       (SELECT COUNT(*) FROM reviews r
         WHERE r.project_id = p.id AND r.status IN ('submitted','finalized')) AS review_count
  FROM projects p
  JOIN teams t ON t.id = p.team_id
  LEFT JOIN tracks tr ON tr.id = p.track_id
"""


def _stage_row(stage: dict) -> dict:
    """The shape `ui.stage_rail` renders."""
    return {
        "name": stage.get("name", ""),
        "code": stage.get("key", ""),
        "is_current": bool(stage.get("is_current")),
        "is_past": stage.get("state") in ("closed", "published"),
        "date_range": (stage.get("closes_at") or stage.get("opens_at") or "")[:10],
    }


def _audit_rows(rows, limit: int = 0) -> list[dict]:
    """Map `audit_log` columns onto the names the organizer templates use."""
    records = []
    for row in (rows[:limit] if limit else rows):
        entry = dict(row)
        entry["created_at"] = entry.get("at", "")
        entry["actor_name"] = entry.get("actor_label", "")
        entry["actor_email"] = entry.get("actor_label", "")
        entry["metadata"] = entry.get("meta_json", "")
        records.append(entry)
    return records


def _require_window(event, stage_key: str, req: http.Request, action: str) -> None:
    """Refuse work outside a stage window, and say so in the audit trail."""
    state = events_mod.window_state(event, stage_key)
    if state == "open":
        return
    message = "%s is not open for %s (%s)." % (stage_key, event["name"], state)
    audit.refused(req, action, message, entity_type="event", entity_id=event["id"])
    raise http.Problem(403, "window_closed", message,
                       "Stage windows are enforced in the API, not just hidden "
                       "in the page.")


def _requested_event_ref(req: http.Request) -> str:
    """An explicit `event` reference from the form, the JSON body or the query."""
    return (req.field("event", "") or req.q("event", "")).strip()


def _ref_query(req: http.Request) -> str:
    """`?event=slug` when the request names an event, else an empty string."""
    reference = _requested_event_ref(req)
    return "?event=" + urllib.parse.quote(reference, safe="") if reference else ""


def _active_event(req: http.Request) -> dict:
    """Which event is this user working in?

    An explicit `event` wins, so a link can point at the open practice sprint.
    Otherwise: the event where the caller already belongs to a team, then the
    primary (official, fixture-seeded) event, which is the closed one, so an
    unqualified action cannot quietly land somewhere unexpected.
    """
    reference = _requested_event_ref(req)
    if reference:
        return _event_row(events_mod.require_event(reference))
    if req.user:
        row = db.one("""SELECT e.* FROM teams t
                          JOIN team_members tm ON tm.team_id = t.id
                          JOIN events e ON e.id = t.event_id
                         WHERE tm.user_id = ? AND e.status != 'draft'
                         ORDER BY e.seq ASC LIMIT 1""", (req.user["id"],))
        if row is not None:
            return dict(row)
    return _require_primary_event()


def _require_primary_event() -> dict:
    event = _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    return event


def _other_events(active_event: dict, user) -> list[dict]:
    """Published events other than the active one, for the switcher."""
    events = []
    for row in db.query("""SELECT * FROM events WHERE status != 'draft' AND id != ?
                            ORDER BY seq ASC""", (active_event["id"],)):
        item = dict(row)
        item["accepting"] = events_mod.submission_window(item)[0]
        item["has_team"] = bool(user) and db.exists(
            """SELECT tm.id FROM team_members tm JOIN teams t ON t.id = tm.team_id
                WHERE tm.user_id = ? AND t.event_id = ?""", (user["id"], item["id"]))
        events.append(item)
    return events


def _event_cards(events) -> list[dict]:
    """Each event with the headline numbers its card prints."""
    return [{"event": event, "metrics": events_mod.event_metrics(event)}
            for event in events]


def _public_event(reference: str, user) -> dict:
    """Resolve an event for a public page, keeping drafts out of sight.

    A draft is invisible to visitors and participants; its own organizers may
    still look at it through the same URL while they build it.
    """
    event = _event_row(events_mod.require_event(reference))
    if event["status"] == "draft" and not events_mod.can_manage(user, event):
        raise http.Problem(404, "event_not_found", "No such event.",
                           "Draft hackathons are only visible to their organizers.")
    return event


def _managed_event(req: http.Request) -> dict:
    """The hackathon this organizer is working in, once authorization agrees.

    `?event=<id or slug>` picks one; otherwise the primary event is used. Either
    way the caller has to manage it, so an organizer cannot read another
    event's submissions by editing a query string.
    """
    event = _event_row(events_mod.default_event_for(
        req.user, _requested_event_ref(req)))
    if not events_mod.can_manage(req.user, event):
        audit.refused(req, "event.manage_refused",
                      "%s asked to operate %s" % (req.user["email"], event["id"]),
                      entity_type="event", entity_id=event["id"])
        raise http.Problem(403, "not_your_event",
                           "You do not manage that hackathon.",
                           "Only its organizers, or an administrator, may open it.")
    return event


def _event_scope(req: http.Request) -> dict:
    """Resolve `{event_id}` from the URL and prove the caller may manage it."""
    event = _event_row(events_mod.require_event(req.params.get("event_id", "")))
    if not events_mod.can_manage(req.user, event):
        audit.refused(req, "event.manage_refused",
                      "%s asked to manage %s" % (req.user["email"], event["id"]),
                      entity_type="event", entity_id=event["id"])
        raise http.Problem(403, "not_your_event",
                           "You do not manage that hackathon.",
                           "Adding yourself as an organizer is the only way in.")
    return event


# --- one event's rows -------------------------------------------------------
#
# These read only what belongs to `event["id"]`. Two hackathons on one install
# never share a team, a submission, an assignment or a review, so "show the
# event I manage" is a filter, not a convention.

def _event_tracks(event) -> list[dict]:
    return db.dicts(db.query("SELECT * FROM tracks WHERE event_id = ? ORDER BY seq",
                             (event["id"],)))


def _event_prizes(event) -> list[dict]:
    return db.dicts(db.query("SELECT * FROM prizes WHERE event_id = ? ORDER BY rank",
                             (event["id"],)))


def _gallery_count(event) -> int:
    """Submissions on exhibition: canonical rows only, drafts stay hidden."""
    return db.scalar("""SELECT COUNT(*) FROM projects
                         WHERE event_id = ? AND duplicate_of IS NULL
                           AND status = 'submitted'""", (event["id"],), 0)


def _timeline_rows(event) -> list[dict]:
    """The dates an entrant meets, in stage order, with where each one stands."""
    stamp = timeutil.now_iso()
    rows = []
    for _key, name, _description, opens_field, closes_field in events_mod.STAGE_SEQUENCE:
        closes_at, opens_at = event[closes_field], event[opens_field]
        at = closes_at or opens_at
        if not at:
            continue
        if closes_at and closes_at < stamp:
            state, label = "past", "closed"
        elif opens_at and opens_at > stamp:
            state, label = "next", "upcoming"
        else:
            state, label = "open", "open now"
        rows.append({"at": at, "label": name, "state": state, "state_label": label})
    return rows


def _event_judges(event) -> list[dict]:
    """The judges of this hackathon: invited, or already holding work here."""
    return db.dicts(db.query("""
        SELECT u.id, u.name, u.email,
               (SELECT COUNT(*) FROM assignments a
                 WHERE a.event_id = ? AND a.judge_user_id = u.id
                   AND a.status != 'revoked') AS assignments,
               (SELECT COUNT(*) FROM reviews r
                 WHERE r.event_id = ? AND r.judge_user_id = u.id
                   AND r.status IN ('submitted', 'finalized')) AS reviews
          FROM users u
         WHERE u.id IN (SELECT user_id FROM judge_invitations
                         WHERE event_id = ? AND user_id IS NOT NULL
                        UNION
                        SELECT judge_user_id FROM assignments WHERE event_id = ?)
         ORDER BY u.name ASC""", (event["id"],) * 4))


def _event_teams(event) -> tuple[list[dict], dict]:
    """(teams, members-by-team) for one hackathon."""
    teams = db.dicts(db.query("""
        SELECT t.*, (SELECT p.title FROM projects p
                      WHERE p.team_id = t.id AND p.event_id = t.event_id
                      ORDER BY p.created_at DESC LIMIT 1) AS project_title
          FROM teams t WHERE t.event_id = ? ORDER BY t.name ASC""", (event["id"],)))
    members: dict[str, list[dict]] = {}
    for row in db.query("""
            SELECT tm.team_id, u.name, tm.role FROM team_members tm
              JOIN users u ON u.id = tm.user_id
              JOIN teams t ON t.id = tm.team_id
             WHERE t.event_id = ? ORDER BY tm.joined_at ASC""", (event["id"],)):
        members.setdefault(row["team_id"], []).append(
            {"name": row["name"], "role": row["role"]})
    return teams, members


def _event_assignments(event) -> list[dict]:
    """Who has which submission here, with the judge's latest review status."""
    return db.dicts(db.query("""
        SELECT a.*, p.title AS project_title, u.name AS judge_name,
               u.email AS judge_email, r.status AS review_status
          FROM assignments a
          JOIN projects p ON p.id = a.project_id
          JOIN users u ON u.id = a.judge_user_id
          LEFT JOIN reviews r ON r.id = (SELECT id FROM reviews
                                          WHERE project_id = a.project_id
                                            AND judge_user_id = a.judge_user_id
                                          ORDER BY revision_no DESC LIMIT 1)
         WHERE a.event_id = ? AND a.status != 'revoked'
         ORDER BY p.title ASC, u.name ASC""", (event["id"],)))


def _event_reviews(event, limit: int = 200) -> list[dict]:
    return db.dicts(db.query("""
        SELECT r.*, p.title AS project_title, u.name AS judge_name
          FROM reviews r
          JOIN projects p ON p.id = r.project_id
          JOIN users u ON u.id = r.judge_user_id
         WHERE r.event_id = ?
         ORDER BY r.updated_at DESC, r.id ASC LIMIT ?""", (event["id"], limit)))


def _event_audit_scope() -> str:
    """The WHERE clause that keeps an audit page inside one hackathon.

    `audit_log` records what changed and which row changed, so an event's slice
    is its own row plus every project, team, assignment and review it owns.
    """
    return """entity_id = ?
           OR entity_id IN (SELECT id FROM projects WHERE event_id = ?)
           OR entity_id IN (SELECT id FROM teams WHERE event_id = ?)
           OR entity_id IN (SELECT id FROM assignments WHERE event_id = ?)
           OR entity_id IN (SELECT id FROM reviews WHERE event_id = ?)"""


def _event_audit(event, *, page: int, per_page: int = 50) -> tuple[list[dict], int]:
    """(records, total_pages) for this hackathon's slice of the audit trail."""
    scope = _event_audit_scope()
    params = (event["id"],) * 5
    total = db.scalar("SELECT COUNT(*) FROM audit_log WHERE " + scope, params, 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = _audit_rows(db.query(
        "SELECT * FROM audit_log WHERE " + scope +
        " ORDER BY at DESC, rowid DESC LIMIT ? OFFSET ?",
        params + (per_page, (page - 1) * per_page)))
    return records, total_pages


# --- confirmations ----------------------------------------------------------
#
# There is no server-side flash queue in this portal (a session is a token and a
# CSRF secret, nothing more). A write therefore redirects with
# `?done=<key>&what=<detail>`, and the page it lands on renders the sentence.

DONE_MESSAGES = {
    "created": "Hackathon created.",
    "saved": "Changes saved.",
    "stage-added": "Stage added.",
    "stage-removed": "Stage removed.",
    "judge-invited": "Judge added to this hackathon: %s.",
    "assigned": "Assignment recorded: %s.",
    "revoked": "Assignment revoked: %s.",
    "organizer-added": "Organizer added: %s.",
    "organizer-removed": "Organizer removed: %s.",
    "published": "Results published as revision %s.",
}


def _done_note(req: http.Request) -> str:
    """The one-line confirmation a redirect carries back."""
    message = DONE_MESSAGES.get(req.q("done", "").strip())
    if not message:
        return ""
    if "%s" not in message:
        return message
    detail = req.q("what", "").strip()
    return message % detail if detail else message.replace("%s", "").strip()


def _redirect_done(path: str, done: str, what: str = "") -> http.Response:
    query = "?done=" + urllib.parse.quote(done, safe="")
    if what:
        query += "&what=" + urllib.parse.quote(what, safe="")
    return http.Response.redirect(path + query)


# --- public handlers --------------------------------------------------------

def handle_landing(req: http.Request) -> http.Response:
    """The homepage: what the event is, where it is, and what is on the table."""
    event = _event_row(events_mod.primary_event())
    stats, recent, stages, current_code = {}, [], [], ""
    if event:
        counts = events_mod.event_counts(event["id"])
        stats = {"projects": counts["projects_submitted"], "teams": counts["teams"],
                 "reviews": counts["reviews_submitted"], "votes": counts["votes"]}
        recent = _decorate_projects(db.query(
            PROJECT_SELECT + """
            WHERE p.event_id = ? AND p.duplicate_of IS NULL AND p.status = 'submitted'
            ORDER BY p.submitted_at DESC, p.created_at DESC LIMIT 6""",
            (event["id"],)))
        stages = [_stage_row(stage) for stage in events_mod.stage_pipeline(event)]
        current = events_mod.current_stage(event)
        current_code = current["key"] if current else ""
    body = landing(event=event, stats=stats, recent_projects=recent,
                   stages=stages, current_stage=current_code)
    return http.Response.html(render_shell(
        title=event["name"] if event else "Lockdown", content=body, user=req.user,
        current_path="/", csrf_token=_csrf(req), event=event))


def handle_gallery(req: http.Request) -> http.Response:
    """The public exhibition. No account, no session, no excuse needed.

    Defaults to the official event; `?event=<id or slug>` browses another one,
    which is how the practice sprint stays visible without replacing the
    fixture event in the acceptance report.
    """
    reference = req.q("event", "").strip()
    event = (_event_row(events_mod.require_event(reference)) if reference
             else _require_primary_event())
    if event is None:
        return http.Response.html(render_shell(
            title="Gallery", user=req.user, csrf_token=_csrf(req),
            content="<p>No event has been published in this portal yet.</p>"))
    return _gallery_response(req, event)


def handle_event_gallery(req: http.Request) -> http.Response:
    """`/events/{slug}/gallery`: the exhibition for one named hackathon."""
    return _gallery_response(req, _public_event(req.params.get("slug", ""), req.user))


def _gallery_response(req: http.Request, event: dict) -> http.Response:
    """Render one event's gallery, once the event may be looked at."""
    if not events_mod.gallery_is_visible(event) \
            and not events_mod.can_manage(req.user, event):
        raise http.Problem(403, "gallery_hidden",
                           "The gallery for %s is not public." % event["name"],
                           "Its organizers can still browse it while signed in.")

    track_filter = req.q("track", "").strip()
    query = req.q("q", "").strip()
    sort = req.q("sort", "title").strip()
    page = _page_number(req)

    clauses, params = ["p.event_id = ?", "p.duplicate_of IS NULL"], [event["id"]]
    if track_filter:
        clauses.append("tr.name = ?")
        params.append(track_filter)
    if query:
        like = "%" + query + "%"
        clauses.append("(p.title LIKE ? OR p.summary LIKE ? OR p.description LIKE ?"
                       " OR t.name LIKE ?)")
        params.extend([like, like, like, like])
    where = " AND ".join(clauses)

    total_count = db.scalar(
        """SELECT COUNT(*) FROM projects p
             JOIN teams t ON t.id = p.team_id
             LEFT JOIN tracks tr ON tr.id = p.track_id
            WHERE """ + where, tuple(params), 0)
    total_pages = max(1, (total_count + GALLERY_PAGE_SIZE - 1) // GALLERY_PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * GALLERY_PAGE_SIZE

    order = {"title": "p.title ASC",
             "newest": "p.submitted_at DESC, p.created_at DESC",
             "votes": "vote_count DESC, p.title ASC"}.get(sort, "p.title ASC")

    projects = _decorate_projects(db.query(
        PROJECT_SELECT + " WHERE " + where + " ORDER BY " + order +
        " LIMIT %d OFFSET %d" % (GALLERY_PAGE_SIZE, offset), tuple(params)))
    tracks = [row["name"] for row in db.query(
        "SELECT name FROM tracks WHERE event_id = ? ORDER BY seq", (event["id"],))]

    body = gallery_view(projects=projects, tracks=tracks, selected_track=track_filter,
                        query=query, page=page, total_pages=total_pages,
                        total_count=total_count, sort=sort)
    return http.Response.html(render_shell(
        title="Gallery", content=body, user=req.user, current_path="/gallery",
        csrf_token=_csrf(req), event=event))


def handle_events_directory(req: http.Request) -> http.Response:
    """The archive: every hackathon this install has run, described by its card.

    No active event here either: the archive is a shelf, not one competition.
    """
    body = event_directory(_event_cards(events_mod.visible_events()),
                           empty_action="/signin")
    return http.Response.html(render_shell(
        title="Hackathons", content=body, user=req.user, current_path="/events",
        csrf_token=_csrf(req)))


def handle_event_page(req: http.Request) -> http.Response:
    """One hackathon's public cover: identity, stage, dates, tracks and prizes."""
    event = _public_event(req.params.get("slug", ""), req.user)
    body = event_page(
        event=event, metrics=events_mod.event_metrics(event),
        stages=[_stage_row(stage) for stage in events_mod.stage_pipeline(event)],
        timeline_rows=_timeline_rows(event),
        tracks=_event_tracks(event), prizes=_event_prizes(event),
        can_manage=events_mod.can_manage(req.user, event),
        gallery_visible=events_mod.gallery_is_visible(event),
        results_visible=events_mod.results_are_visible(event),
        gallery_count=_gallery_count(event))
    return http.Response.html(render_shell(
        title=event["name"], content=body, user=req.user, current_path="/events",
        csrf_token=_csrf(req), event=event))


def handle_project_detail(req: http.Request) -> http.Response:
    """One submission in full: dossier, team, version history, discussion."""
    project_id = req.params.get("project_id", "")
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if row is None:
        raise http.Problem(404, "project_not_found", "No such project.",
                           "Nothing is published at that address.")
    project = _decorate_projects([row])[0]

    team = dict(db.one("SELECT * FROM teams WHERE id = ?", (project["team_id"],)) or {})
    members = db.dicts(db.query(
        """SELECT u.name, u.email, tm.role FROM team_members tm
             JOIN users u ON u.id = tm.user_id
            WHERE tm.team_id = ? ORDER BY tm.joined_at""", (project["team_id"],)))
    versions = db.dicts(db.query(
        "SELECT * FROM project_versions WHERE project_id = ? ORDER BY version_no DESC",
        (project_id,)))
    comments = db.dicts(db.query(
        """SELECT c.*, u.name AS author_name FROM comments c
             JOIN users u ON u.id = c.user_id
            WHERE c.project_id = ? AND c.is_hidden = 0 ORDER BY c.created_at ASC""",
        (project_id,)))

    link = "SELECT id, title FROM projects WHERE id = ?"
    superseded_by = db.one(link, (project["superseded_by"],)) if project.get("superseded_by") else None
    duplicate_of = db.one(link, (project["duplicate_of"],)) if project.get("duplicate_of") else None
    user_has_voted = bool(req.user) and db.exists(
        "SELECT id FROM votes WHERE project_id = ? AND user_id = ?",
        (project_id, req.user["id"]))

    body = project_detail_view(
        project=project, team=team, members=members, versions=versions,
        comments=comments, user_has_voted=user_has_voted, user=req.user,
        csrf_token=_csrf(req), superseded_by=superseded_by, duplicate_of=duplicate_of)
    return http.Response.html(render_shell(
        title=project["title"], content=body, user=req.user,
        current_path="/gallery", csrf_token=_csrf(req),
        event=_event_row(events_mod.get_event(project["event_id"]))))


def handle_results(req: http.Request) -> http.Response:
    """The results archive, and the ledger inside it.

    A standings table is only meaningful for one hackathon, so with more than
    one published event this page is the index that leads to them. On an install
    that ran a single event there is nothing to choose between, and the
    standings are rendered directly -- the page a one-event portal always had.
    """
    events = [event for event in events_mod.visible_events()
              if events_mod.results_are_visible(event)]
    if len(events) == 1:
        return _results_response(req, events[0])
    if not events:
        return http.Response.html(render_shell(
            title="Results", user=req.user, csrf_token=_csrf(req),
            content="<p>No event has been published in this portal yet.</p>"))

    body = results_directory(_event_cards(events),
                             user_role=req.user["role"] if req.user else None)
    return http.Response.html(render_shell(
        title="Results", content=body, user=req.user, current_path="/results",
        csrf_token=_csrf(req), event=_event_row(events_mod.primary_event())))


def handle_event_results(req: http.Request) -> http.Response:
    """`/events/{slug}/results`: one hackathon's published ledger."""
    event = _public_event(req.params.get("slug", ""), req.user)
    if not events_mod.results_are_visible(event) \
            and not events_mod.can_manage(req.user, event):
        raise http.Problem(403, "results_hidden",
                           "The results for %s are not public." % event["name"],
                           "Its organizers can still read them while signed in.")
    return _results_response(req, event)


def _results_response(req: http.Request, event: dict) -> http.Response:
    """Published standings, and nothing else.

    Before publication this page renders an embargo panel for everyone except
    organizers, and the handler hands the template an empty table rather than
    the live numbers, so an embargo cannot be undone by editing the HTML.
    """
    publication = events_mod.results_published(event)
    staff = bool(req.user) and req.user["role"] in ("organizer", "admin")

    ranked = []
    if publication is not None:
        ranked = [_published_row(item, index)
                  for index, item in enumerate(
                      results_mod.publication_rows(publication), start=1)]
    elif staff:
        ranked = [_live_row(project)
                  for project in scoring.scoreboard(event)["ranked"]]

    body = results_scope_note(event=event, publication=publication) + \
        results_leaderboard(event=event, ranked=ranked,
                            is_published=publication is not None,
                            user_role=req.user["role"] if req.user else None)
    return http.Response.html(render_shell(
        title="Results", content=body, user=req.user, current_path="/results",
        csrf_token=_csrf(req), event=event))



def _published_row(item: dict, index: int) -> dict:
    """One frozen row from a `result_publications` snapshot."""
    flags = item.get("flags") or []
    return {"published_rank": item.get("rank") or index,
            "project_id": item.get("project_id", ""), "title": item.get("title", ""),
            "team_name": item.get("team", ""), "track": item.get("track") or "General",
            "raw_mean": item.get("raw_score"), "normalized_mean": item.get("score"),
            "review_count": item.get("reviews", 0), "coverage": item.get("coverage"),
            "flags": flags, "flag_labels": scoring.flag_labels(flags)}


def _live_row(project: dict) -> dict:
    """The organizer's pre-publication preview of the same numbers."""
    row = dict(project)
    row["team_name"] = project.get("team_name", "")
    row["track"] = project.get("track_name") or "General"
    row["flag_labels"] = scoring.flag_labels(project.get("flags") or [])
    return row


# --- sessions ---------------------------------------------------------------

def handle_signin_page(req: http.Request) -> http.Response:
    """The sign-in form. Safe to open even when a session already exists."""
    body = signin_form(csrf_token=_csrf(req),
                       next_url=util.safe_next(req.q("next", ""), "/"))
    return http.Response.html(render_shell(
        title="Sign In", content=body, user=req.user, current_path="/signin",
        csrf_token=_csrf(req)))


def handle_signin(req: http.Request) -> http.Response:
    """Authenticate and open a session. Failure is audited, not just rendered."""
    email = req.field("email", "").strip().lower()
    password = req.field("password", "")
    next_url = util.safe_next(req.field("next", "") or req.q("next", ""), "/")

    user = auth.user_by_email(email)
    if not auth.check_password(user, password):
        audit.record(action="auth.signin", entity_type="user",
                     entity_id=email or "unknown",
                     summary="Rejected sign-in for %s" % (email or "an empty email"),
                     outcome="refused", request=req)
        body = signin_form(csrf_token=_csrf(req), next_url=next_url)
        return http.Response.html(render_shell(
            title="Sign In", content=body, user=None, current_path="/signin",
            error="That email and password combination was not accepted.",
            csrf_token=_csrf(req)), status=401)

    response = http.Response.redirect(next_url)
    auth.start(req, response, user, label="password")
    audit.record(action="auth.signin", entity_type="user", entity_id=user["id"],
                 summary="Signed in as %s" % user["email"], request=req,
                 actor=_actor(user))
    return response


def handle_signout(req: http.Request) -> http.Response:
    """Revoke the current session token and clear the cookie."""
    response = http.Response.redirect("/")
    if req.session:
        auth.end(req, response)
        audit.record(action="auth.signout", entity_type="user",
                     entity_id=req.session["user_id"],
                     summary="Signed out %s" % req.session.get("email", ""), request=req)
    return response


FAST_LOGIN_PROFILES = {
    "organizer": {
        "email": "organizer@dogfood.test",
        "redirect": "/organizer",
        "role_label": "Organizer",
    },
    "admin": {
        "email": "admin@dogfood.test",
        "redirect": "/organizer",
        "role_label": "Administrator",
    },
    "judge_sample": {
        "email": "tomas.varga@example.org",
        "redirect": "/judge",
        "role_label": "Judge (Sample Hack)",
    },
    "judge_dogfood": {
        "email": "wei.lindqvist@example.org",
        "redirect": "/judge",
        "role_label": "Judge (Dogfood)",
    },
    "builder_sample": {
        "email": "priya1@example.org",
        "redirect": "/participant",
        "role_label": "Builder (Sample Hack)",
    },
    "builder_dogfood": {
        "email": "member1_1@example.org",
        "redirect": "/participant",
        "role_label": "Builder (Dogfood)",
    },
}

FAST_LOGIN_ALIASES = {
    "judge_a": "judge_sample",
    "judge_b": "judge_dogfood",
    "judge": "judge_sample",
    "participant": "builder_sample",
    "participant_2": "builder_dogfood",
    "builder": "builder_sample",
    "staff": "organizer",
}


def handle_fast_login(req: http.Request) -> http.Response:
    """Instant sign-in for demo accounts during hackathon judging and presentations.

    Disabled unless `PORTAL_FAST_LOGIN=1`, because this endpoint mints a real
    session for a seeded fixture account without a password or a CSRF token. When
    the flag is off the route behaves as if it did not exist: a 404 and no
    session, so a deployment that forgets the flag cannot leak demo logins.
    """
    if not config.FAST_LOGIN_ENABLED:
        raise http.Problem(404, "not_found",
                           "One-click demo sign-in is disabled on this deployment.")

    account_key = (req.field("account", "") or req.q("user", "") or req.q("account", "")).strip().lower()
    if account_key in FAST_LOGIN_ALIASES:
        account_key = FAST_LOGIN_ALIASES[account_key]

    profile = FAST_LOGIN_PROFILES.get(account_key)
    target_email = profile["email"] if profile else account_key
    target_url = profile["redirect"] if profile else util.safe_next(req.field("next", "") or req.q("next", ""), "")

    # Fallback lookup in config demo accounts if not in profiles
    if not profile:
        for key, email, _name, role, _token in (config.DEMO_ACCOUNTS + config.EXTRA_DEMO_ACCOUNTS):
            if key.lower() == account_key:
                target_email = email
                if not target_url:
                    target_url = "/organizer" if role in ("organizer", "admin") else ("/judge" if role == "judge" else "/participant")
                break

    user = auth.user_by_email(target_email)
    if not user:
        # Fallback search by ID or name
        user = db.one("SELECT * FROM users WHERE id = ? OR name LIKE ? COLLATE NOCASE LIMIT 1",
                      (target_email, f"%{target_email}%"))

    if not user:
        raise http.Problem(404, "user_not_found", f"Demo account '{account_key}' was not found.")

    if not target_url:
        role = user.get("role")
        if role in ("organizer", "admin"):
            target_url = "/organizer"
        elif role == "judge":
            target_url = "/judge"
        elif role == "participant":
            target_url = "/participant"
        else:
            target_url = "/"

    response = http.Response.redirect(target_url)
    auth.start(req, response, user, label="fast-login", is_demo=True)
    audit.record(action="auth.signin", entity_type="user", entity_id=user["id"],
                 summary=f"Fast login as {user['name']} ({user['role']})", request=req,
                 actor=_actor(user))
    return response


# --- community actions ------------------------------------------------------

def _project_or_404(req: http.Request) -> dict:
    project_id = req.params.get("project_id", "")
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if row is None:
        raise http.Problem(404, "project_not_found", "No such project.")
    return dict(row)


def handle_vote(req: http.Request) -> http.Response:
    """Toggle the signed-in user's community vote on one project."""
    project = _project_or_404(req)
    event = _event_row(events_mod.require_event(project["event_id"]))
    user = req.user

    on_team = db.exists(
        "SELECT id FROM team_members WHERE team_id = ? AND user_id = ?",
        (project["team_id"], user["id"]))
    if on_team:
        audit.refused(req, "vote.refused", "team member tried to vote on own project",
                      entity_type="project", entity_id=project["id"])
        raise http.Problem(403, "own_project",
                           "Team members cannot vote for their own submission.")

    existing = db.one("SELECT id FROM votes WHERE project_id = ? AND user_id = ?",
                      (project["id"], user["id"]))
    with db.tx():
        if existing:
            db.execute("DELETE FROM votes WHERE id = ?", (existing["id"],))
            action, summary = "vote.withdrawn", "Withdrew a vote on %s" % project["title"]
        else:
            db.insert("votes", {"id": util.new_id("vot"), "event_id": event["id"],
                                "project_id": project["id"], "user_id": user["id"],
                                "weight": 1, "created_at": timeutil.now_iso()})
            action, summary = "vote.cast", "Voted for %s" % project["title"]
    audit.record(action=action, entity_type="project", entity_id=project["id"],
                 summary=summary, request=req)
    return http.Response.redirect("/gallery/" + project["id"])


def handle_comment(req: http.Request) -> http.Response:
    """Add a public comment to a submission dossier."""
    project = _project_or_404(req)
    body = req.field("body", "").strip()
    if not body:
        raise http.Problem(400, "empty_comment", "A comment needs some words in it.")
    if len(body) > 4000:
        raise http.Problem(400, "comment_too_long",
                           "Comments are limited to 4000 characters.",
                           "That one was %d." % len(body))

    now = timeutil.now_iso()
    comment_id = util.new_id("cmt")
    db.insert("comments", {"id": comment_id, "project_id": project["id"],
                           "user_id": req.user["id"], "body": body, "is_hidden": 0,
                           "created_at": now, "updated_at": now})
    audit.record(action="comment.posted", entity_type="project", entity_id=project["id"],
                 summary="Commented on %s" % project["title"], request=req,
                 after={"comment_id": comment_id})
    return http.Response.redirect("/gallery/" + project["id"])


# --- participant handlers ---------------------------------------------------

def _my_team(user_id: str, event_id: str):
    """The caller's team in this event, or None. Membership, not ownership."""
    return db.one("""SELECT t.* FROM teams t
                       JOIN team_members tm ON tm.team_id = t.id
                      WHERE tm.user_id = ? AND t.event_id = ?""", (user_id, event_id))


def _my_project(team_id: str, event_id: str):
    return db.one("""SELECT * FROM projects
                      WHERE event_id = ? AND team_id = ? AND status != 'withdrawn'
                      ORDER BY created_at DESC LIMIT 1""", (event_id, team_id))


def _certificate_row(row) -> dict:
    """Map a certificate onto the shape the participant template renders."""
    return {"award_tier": (row["kind"] or "participation").replace("_", " ").title(),
            "recipient_name": row["title"] or row["team_id"] or row["id"],
            "sha256": row["code"], "issued_at": row["issued_at"],
            "project_id": row["project_id"]}


def _invite_code() -> str:
    for _attempt in range(8):
        code = util.new_id("inv").split("_", 1)[-1].upper()
        if not db.exists("SELECT id FROM teams WHERE invite_code = ?", (code,)):
            return code
    return util.new_id("inv").upper()


def handle_participant_dashboard(req: http.Request) -> http.Response:
    """The participant's workspace: team, submission, certificates."""
    event = _active_event(req)
    user = req.user
    team = _my_team(user["id"], event["id"])
    project = _my_project(team["id"], event["id"]) if team else None
    certificates = []
    if project is not None:
        certificates = [_certificate_row(row) for row in db.query(
            "SELECT * FROM certificates WHERE project_id = ? ORDER BY issued_at DESC",
            (project["id"],))]

    body = participant_dashboard(
        user=_actor(user), team=dict(team) if team else None,
        project=_decorate_projects([project])[0] if project else None,
        event=event, certificates=certificates, csrf_token=_csrf(req),
        event_ref=_requested_event_ref(req),
        other_events=_other_events(event, user))
    return http.Response.html(render_shell(
        title="Participant Workspace", content=body, user=req.user,
        current_path="/participant", csrf_token=_csrf(req), event=event))


def handle_participant_team_create(req: http.Request) -> http.Response:
    """Register a team in the window that is open, and put the caller on it."""
    event = _active_event(req)
    user = req.user

    allowed, code, message, status = events_mod.registration_window(event)
    if not allowed:
        audit.refused(req, "team.refused", message, entity_type="event",
                      entity_id=event["id"])
        raise http.Problem(status, code, message)
    if _my_team(user["id"], event["id"]) is not None:
        raise http.Problem(409, "already_on_a_team",
                           "You are already on a team in this event.",
                           "Leave that team before creating another one.")

    name = req.field("name", "").strip()
    if not name:
        raise http.Problem(400, "team_name_required", "A team needs a name.")
    if len(name) > 80:
        raise http.Problem(400, "team_name_too_long", "Team names stop at 80 characters.")

    team_id = util.new_id("tem")
    now = timeutil.now_iso()
    with db.tx():
        db.insert("teams", {
            "id": team_id, "event_id": event["id"], "name": name,
            "slug": fixtures_seed.unique_slug("teams", "slug", name, "event_id", event["id"]),
            "invite_code": _invite_code(), "created_by": user["id"], "status": "active",
            "seed_hint": "created in the portal", "created_at": now, "updated_at": now})
        db.insert("team_members", {"id": util.new_id("tmm"), "team_id": team_id,
                                   "user_id": user["id"], "role": "owner",
                                   "joined_at": now})
    audit.record(action="team.created", entity_type="team", entity_id=team_id,
                 summary="Created team %s" % name, request=req,
                 after={"name": name, "event_id": event["id"]})
    return http.Response.redirect("/participant" + _ref_query(req))


def _project_with_track(project):
    """A project row plus the two display fields the editor needs."""
    if project is None:
        return None
    source = dict(project)
    row = _decorate_projects([source])[0]
    if source.get("track_id"):
        row["track"] = db.scalar("SELECT name FROM tracks WHERE id = ?",
                                 (source["track_id"],), row["track"])
    return row


def _project_form_response(req: http.Request, project, action_url: str) -> http.Response:
    """Render the submission editor, warning when the window has closed."""
    event = _active_event(req)
    team = _my_team(req.user["id"], event["id"])
    if team is None:
        return http.Response.redirect("/participant")
    allowed, _code, message, _status = events_mod.submission_window(event)
    tracks = [row["name"] for row in db.query(
        "SELECT name FROM tracks WHERE event_id = ? ORDER BY seq", (event["id"],))]
    body = project_form(project=_project_with_track(project), team=dict(team),
                        tracks=tracks, csrf_token=_csrf(req), action_url=action_url)
    return http.Response.html(render_shell(
        title="Edit Submission" if project else "Register Project", content=body,
        user=req.user, current_path="/participant", csrf_token=_csrf(req),
        event=event, error=None if allowed else message))


def handle_participant_project_new(req: http.Request) -> http.Response:
    """The empty submission editor, once a team exists."""
    event = _active_event(req)
    team = _my_team(req.user["id"], event["id"])
    if team is None:
        return http.Response.redirect("/participant")
    if _my_project(team["id"], event["id"]) is not None:
        return http.Response.redirect("/participant/project/edit" + _ref_query(req))
    return _project_form_response(req, None,
                                   "/participant/project/new" + _ref_query(req))


def handle_participant_project_edit(req: http.Request) -> http.Response:
    """The same editor, pre-filled from the team's current submission."""
    event = _active_event(req)
    team = _my_team(req.user["id"], event["id"])
    if team is None:
        return http.Response.redirect("/participant")
    project = _my_project(team["id"], event["id"])
    if project is None:
        raise http.Problem(404, "project_not_found",
                           "Your team has not registered a submission yet.",
                           "Create one first, then come back to edit it.")
    return _project_form_response(req, project,
                                   "/participant/project/edit" + _ref_query(req))


def handle_participant_project_save(req: http.Request) -> http.Response:
    """Create or update the team's submission.

    The deadline is enforced here, before anything is written. The page hides
    the button when the window is shut, but hiding a button is not a rule, so
    the rule is checked again on the way in.
    """
    event = _active_event(req)
    user = req.user

    allowed, code, message, status = events_mod.submission_window(event)
    if not allowed:
        audit.refused(req, "submission.refused", message, entity_type="event",
                      entity_id=event["id"])
        raise http.Problem(status, code, message,
                           "The submission window is checked in the API, not only "
                           "in the page that renders the form.")

    team = _my_team(user["id"], event["id"])
    if team is None:
        raise http.Problem(400, "no_team",
                           "Join or create a team before submitting a project.")

    title = req.field("title", "").strip()
    summary = req.field("summary", "").strip()
    description = req.field("description", "").strip()
    repo_url = req.field("repo_url", "").strip()
    demo_url = req.field("demo_url", "").strip()
    track_name = req.field("track", "").strip()
    if not title:
        raise http.Problem(400, "title_required", "A submission needs a title.")
    if not summary:
        raise http.Problem(400, "summary_required",
                           "A submission needs a one-line summary.")
    if len(title) > 140 or len(summary) > 280:
        raise http.Problem(400, "too_long",
                           "Titles stop at 140 characters, summaries at 280.")

    track = db.one("SELECT id FROM tracks WHERE event_id = ? AND name = ?",
                   (event["id"], track_name)) if track_name else None
    if track_name and track is None:
        raise http.Problem(400, "unknown_track",
                           "That track is not part of this event.",
                           "Pick one of the event's tracks, or leave it general.")

    action = req.field("action", "save").strip().lower()
    want_submit = req.checkbox("submit") or action in ("submit", "finalize", "publish")
    now = timeutil.now_iso()
    project = _my_project(team["id"], event["id"])
    new_status = "submitted" if want_submit else "draft"

    with db.tx():
        if project is None:
            project_id = util.new_id("prj")
            version_no = 1
            db.insert("projects", {
                "id": project_id, "event_id": event["id"], "team_id": team["id"],
                "track_id": track["id"] if track else None, "title": title,
                "summary": summary, "description": description, "repo_url": repo_url,
                "demo_url": demo_url, "video_url": "", "tags": "",
                "status": new_status, "submission_state": "open",
                "current_version": version_no,
                "submitted_at": now if want_submit else None,
                "locked_at": now if want_submit else None,
                "created_by": user["id"], "created_at": now, "updated_at": now})
            event_action = "submission.submitted" if want_submit else "submission.created"
        else:
            project_id = project["id"]
            version_no = db.scalar("""SELECT COALESCE(MAX(version_no), 0)
                                        FROM project_versions WHERE project_id = ?""",
                                   (project_id,), 0) + 1
            db.update("projects", {
                "track_id": track["id"] if track else project["track_id"],
                "title": title, "summary": summary, "description": description,
                "repo_url": repo_url, "demo_url": demo_url,
                "status": new_status if want_submit else project["status"],
                "current_version": version_no,
                "submitted_at": project["submitted_at"] or (now if want_submit else None),
                "locked_at": project["locked_at"] or (now if want_submit else None),
                "updated_at": now}, "id = ?", (project_id,))
            event_action = ("submission.resubmitted" if want_submit
                            else "submission.saved")

        db.insert("project_versions", {
            "id": util.new_id("prv"), "project_id": project_id, "version_no": version_no,
            "title": title, "summary": summary, "description": description,
            "repo_url": repo_url, "demo_url": demo_url, "video_url": "", "tags": "",
            "status": new_status, "reason": "submit" if want_submit else "save",
            "created_by": user["id"], "created_at": now,
            "snapshot": db.json_text({"title": title, "summary": summary,
                                      "track": track_name or "General"})})

    audit.record(action=event_action, entity_type="project", entity_id=project_id,
                 summary="%s %s" % ("Submitted" if want_submit else "Saved", title),
                 request=req,
                 after={"title": title, "version": version_no, "status": new_status,
                        "track": track_name or "General"})
    return http.Response.redirect("/gallery/" + project_id)


# --- judge handlers ---------------------------------------------------------

def _judge_assignments(judge_id: str) -> list[dict]:
    """Every assignment the judge holds in a published event, newest event last."""
    rows = db.query("""
        SELECT a.id AS assignment_id, a.status AS assignment_status, a.due_at,
               a.project_id, p.title AS project_title, p.status AS project_status,
               tr.name AS track_name, t.name AS team_name,
               e.id AS event_id, e.name AS event_name,
               r.id AS review_id, r.status AS review_status, r.submitted_at,
               r.weighted_raw
          FROM assignments a
          JOIN projects p ON p.id = a.project_id
          JOIN events e ON e.id = a.event_id
          JOIN teams t ON t.id = p.team_id
          LEFT JOIN tracks tr ON tr.id = p.track_id
          LEFT JOIN reviews r ON r.project_id = a.project_id
                             AND r.judge_user_id = a.judge_user_id
         WHERE a.judge_user_id = ? AND a.status != 'revoked' AND e.status != 'draft'
         ORDER BY e.seq ASC, (r.status IN ('submitted','finalized')) ASC, p.title ASC""",
        (judge_id,))
    assignments = []
    for row in rows:
        item = dict(row)
        item["status"] = item.get("assignment_status")
        item["track"] = item.get("track_name") or "General"
        assignments.append(item)
    return assignments


def _assignment_for(project_id: str, judge_id: str):
    return db.one("""SELECT * FROM assignments
                      WHERE project_id = ? AND judge_user_id = ? AND status != 'revoked'
                      ORDER BY assigned_at DESC LIMIT 1""", (project_id, judge_id))


def _require_assignment(project_id: str, req: http.Request):
    assignment = _assignment_for(project_id, req.user["id"])
    if assignment is None:
        audit.refused(req, "review.refused",
                      "%s is not assigned to %s" % (req.user["email"], project_id),
                      entity_type="project", entity_id=project_id)
        raise http.Problem(403, "not_assigned",
                           "You are not assigned to this submission.",
                           "Judges may only open submissions they were given.")
    return assignment


def handle_judge_dashboard(req: http.Request) -> http.Response:
    """The judge's queue: what is assigned, what is still pending."""
    judge = req.user
    assignments = _judge_assignments(judge["id"])
    completed = sum(1 for item in assignments
                    if item.get("review_status") in ("submitted", "finalized"))
    event = _event_row(events_mod.primary_event())
    body = judge_dashboard(judge=_actor(judge), assignments=assignments,
                           event=dict(event) if event else {}, 
                           progress={"completed": completed, "total": len(assignments)})
    return http.Response.html(render_shell(
        title="Judge Portal", content=body, user=req.user, current_path="/judge",
        csrf_token=_csrf(req), event=event))


def handle_judge_evaluate_page(req: http.Request) -> http.Response:
    """The rubric form for one assigned submission."""
    judge = req.user
    project_id = req.params.get("project_id", "")
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if row is None:
        raise http.Problem(404, "project_not_found", "No such project.")
    _require_assignment(project_id, req)

    event = _event_row(events_mod.require_event(row["event_id"]))
    rubric = scoring.active_rubric(event["id"])
    criteria = ([dict(item, name=item["label"])
                 for item in scoring.rubric_criteria(rubric["id"])] if rubric else [])
    review = db.one("""SELECT * FROM reviews WHERE project_id = ? AND judge_user_id = ?
                        ORDER BY revision_no DESC LIMIT 1""", (project_id, judge["id"]))
    existing_scores = {}
    if review is not None:
        for score in db.query("""SELECT criterion_id, criterion_key, value
                                   FROM review_scores WHERE review_id = ?""", (review["id"],)):
            existing_scores[score["criterion_id"]] = score["value"]
            existing_scores[score["criterion_key"]] = score["value"]
    shown_review = ({"notes": review["comment"], "private_notes": review["internal_note"]}
                    if review else None)
    locked = events_mod.window_state(event, "review") != "open"

    body = evaluation_form(project=dict(row), rubric=dict(rubric) if rubric else {},
                           criteria=criteria, review=shown_review,
                           existing_scores=existing_scores, csrf_token=_csrf(req))
    return http.Response.html(render_shell(
        title="Evaluating %s" % row["title"], content=body, user=req.user,
        current_path="/judge", csrf_token=_csrf(req), event=event,
        error=("The review window for %s is closed, so scores are locked."
               % event["name"]) if locked else None))


def handle_judge_evaluate_save(req: http.Request) -> http.Response:
    """Record a draft or a submitted review against the active rubric.

    A submitted review is never overwritten in place: the previous numbers are
    appended to `review_revisions` first, so a score that was announced can
    always be reproduced.
    """
    judge = req.user
    project_id = req.params.get("project_id", "")
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if row is None:
        raise http.Problem(404, "project_not_found", "No such project.")
    _require_assignment(project_id, req)

    event = _event_row(events_mod.require_event(row["event_id"]))
    _require_window(event, "review", req, "review.refused")

    rubric = scoring.active_rubric(event["id"])
    criteria = scoring.normalise_weights(scoring.rubric_criteria(rubric["id"])) if rubric else []
    action = req.field("action", "submit").strip().lower()
    status = "submitted" if action in ("submit", "finalize", "submit-final") else "draft"
    comment = req.field("notes", "").strip()
    internal_note = req.field("private_notes", "").strip()
    if len(comment) > 4000 or len(internal_note) > 4000:
        raise http.Problem(400, "too_long", "Review notes stop at 4000 characters.")

    given = {}
    for criterion in criteria:
        value = util.as_float(req.field("score_%s" % criterion["id"], ""))
        if value is not None:
            given[criterion["id"]] = util.clamp(value, float(criterion["min_score"]),
                                                float(criterion["max_score"]))
    if status == "submitted":
        if not criteria:
            raise http.Problem(400, "no_rubric",
                               "This event has no active rubric, so nothing can be scored.")
        missing = [criterion["label"] for criterion in criteria
                   if criterion["id"] not in given]
        if missing:
            raise http.Problem(400, "incomplete_review",
                               "Every rubric criterion needs a score before submission.",
                               "Still missing: " + ", ".join(missing))

    weighted = scoring.weighted_raw(
        {criterion["key"]: given.get(criterion["id"]) for criterion in criteria}, criteria)
    now = timeutil.now_iso()
    review = db.one("""SELECT * FROM reviews WHERE project_id = ? AND judge_user_id = ?
                        ORDER BY revision_no DESC LIMIT 1""", (project_id, judge["id"]))

    with db.tx():
        if review is None:
            review_id = util.new_id("rev")
            db.insert("reviews", {
                "id": review_id, "project_id": project_id, "judge_user_id": judge["id"],
                "event_id": event["id"], "rubric_id": rubric["id"] if rubric else None,
                "status": status, "revision_no": 1, "comment": comment,
                "internal_note": internal_note, "weighted_raw": weighted,
                "origin": "portal", "started_at": now, "updated_at": now,
                "submitted_at": now if status == "submitted" else None})
        else:
            review_id = review["id"]
            already_recorded = review["status"] in ("submitted", "finalized")
            revision = (review["revision_no"] or 1) + (1 if already_recorded else 0)
            if already_recorded:
                previous = [{"key": item["criterion_key"], "value": item["value"]}
                            for item in db.query("""SELECT criterion_key, value
                                                      FROM review_scores
                                                     WHERE review_id = ?""", (review_id,))]
                db.insert("review_revisions", {
                    "id": util.new_id("rvr"), "review_id": review_id,
                    "revision_no": review["revision_no"] or 1,
                    "scores_json": db.json_text(previous), "comment": review["comment"],
                    "weighted_raw": review["weighted_raw"], "status": review["status"],
                    "reason": "superseded by a later revision", "actor_id": judge["id"],
                    "created_at": now})
            db.update("reviews", {
                "status": status, "revision_no": revision, "comment": comment,
                "internal_note": internal_note, "weighted_raw": weighted,
                "rubric_id": rubric["id"] if rubric else review["rubric_id"],
                "updated_at": now,
                "submitted_at": (review["submitted_at"] or
                                 (now if status == "submitted" else None)),
                "finalized_at": (now if status == "finalized"
                                 else review["finalized_at"])}, "id = ?", (review_id,))

        for criterion in criteria:
            if criterion["id"] not in given:
                continue
            existing = db.one("""SELECT id FROM review_scores
                                  WHERE review_id = ? AND criterion_id = ?""",
                              (review_id, criterion["id"]))
            payload = {"criterion_key": criterion["key"], "weight": criterion["weight"],
                       "value": given[criterion["id"]]}
            if existing:
                db.update("review_scores", payload, "id = ?", (existing["id"],))
            else:
                db.insert("review_scores", dict(payload, id=util.new_id("rsc"),
                                                review_id=review_id,
                                                criterion_id=criterion["id"]))

    audit.record(action=("review.submitted" if status == "submitted" else "review.drafted"),
                 entity_type="review", entity_id=review_id,
                 summary="%s review of %s" % (status.capitalize(), row["title"]),
                 request=req, after={"status": status, "weighted_raw": weighted,
                                     "criteria_scored": len(given)})
    if status == "submitted":
        fixtures_seed.refresh_normalization(event["id"])

    if req.wants_json or req.headers.get("X-Requested-With") == "fetch":
        return http.Response.json({"status": status, "review_id": review_id,
                                   "weighted_raw": weighted})
    return http.Response.redirect("/judge")


# --- organizer handlers -----------------------------------------------------

def handle_manage_home(req: http.Request) -> http.Response:
    """My Hackathons: the shelf of events this caller may operate.

    The shell is rendered without an active event on purpose: this page is about
    several hackathons, so it does not borrow the masthead of one of them.
    """
    events = events_mod.manageable_events(req.user)
    body = manage_home(actor=_actor(req.user), events=_event_cards(events),
                       can_create=req.user["role"] in ("organizer", "admin"))
    return http.Response.html(render_shell(
        title="My Hackathons", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req)))


def handle_event_new(req: http.Request) -> http.Response:
    """The empty hackathon form, pre-filled with a sensible schedule."""
    body = event_form(values=eventadmin.blank_form(), errors={}, csrf_token=_csrf(req))
    return http.Response.html(render_shell(
        title="Create Hackathon", content=body, user=req.user,
        current_path="/organizer", csrf_token=_csrf(req)))


def handle_event_create(req: http.Request) -> http.Response:
    """Create a hackathon, or hand the refused form back with its errors.

    The browser is a convenience: the same `validate` runs for a hand-written
    POST, and nothing is written until every field passes.
    """
    values, errors = eventadmin.validate(req.form)
    if errors:
        audit.refused(req, "event.create_refused",
                      "Refused to create %r: %s" % (req.field("name", ""),
                                                    ", ".join(sorted(errors))),
                      entity_type="event")
        body = event_form(values=dict(req.form), errors=errors, csrf_token=_csrf(req))
        return http.Response.html(render_shell(
            title="Create Hackathon", content=body, user=req.user,
            current_path="/organizer", csrf_token=_csrf(req),
            error="Nothing was created: %d field%s need attention."
                  % (len(errors), "" if len(errors) == 1 else "s")), status=400)

    created = eventadmin.create(values, _actor(req.user))
    audit.record(action="event.created", entity_type="event",
                 entity_id=created["event_id"],
                 summary="Created hackathon %s" % created["name"], request=req,
                 after={"slug": created["slug"], "status": values["status"],
                        "seq": created["seq"]})
    return _redirect_done("/organizer/events/" + created["event_id"], "created")


def handle_event_manage(req: http.Request) -> http.Response:
    """One hackathon's management overview: state, numbers, people, next steps."""
    event = _event_scope(req)
    body = event_overview(
        event=event, metrics=events_mod.event_metrics(event),
        stages=[_stage_row(stage) for stage in events_mod.stage_pipeline(event)],
        timeline_rows=_timeline_rows(event),
        organizers=events_mod.organizers_of(event["id"]),
        judges=_event_judges(event), csrf_token=_csrf(req),
        actor_role=req.user["role"],
        gallery_visible=events_mod.gallery_is_visible(event),
        results_visible=events_mod.results_are_visible(event))
    return http.Response.html(render_shell(
        title="Managing %s" % event["name"], content=body, user=req.user,
        current_path="/organizer", csrf_token=_csrf(req), event=event,
        notice=_done_note(req)))


def handle_organizer_submissions(req: http.Request) -> http.Response:
    """Every submission in the event, superseded duplicates included."""
    event = _managed_event(req)
    projects = _decorate_projects(db.query(
        PROJECT_SELECT + " WHERE p.event_id = ? ORDER BY p.title ASC", (event["id"],)))
    body = submissions_list(projects=projects, event=event)
    return http.Response.html(render_shell(
        title="Submissions", content=body, user=req.user,
        current_path="/organizer/submissions", csrf_token=_csrf(req), event=event))


def handle_organizer_judges(req: http.Request) -> http.Response:
    """Judge roster plus the calibration numbers normalization depends on."""
    event = _managed_event(req)
    judges = db.dicts(db.query(
        "SELECT * FROM users WHERE role = 'judge' ORDER BY name ASC"))
    criteria = scoring.normalise_weights(scoring.criteria_for_event(event["id"]))
    model = scoring.normalize(scoring.load_reviews(event["id"]), criteria)
    stats = {}
    for judge_id, row in model["judges"].items():
        item = dict(row)
        item["flags"] = scoring.flag_labels(item.get("flags") or [])
        stats[judge_id] = item
    body = judges_roster(judges=judges, stats=stats, event=event)
    return http.Response.html(render_shell(
        title="Judges", content=body, user=req.user,
        current_path="/organizer/judges", csrf_token=_csrf(req), event=event))


def handle_organizer_audit(req: http.Request) -> http.Response:
    """This event's slice of the append-only log, newest first."""
    event = _managed_event(req)
    page = _page_number(req)
    records, total_pages = _event_audit(event, page=page)
    body = audit_trail(records=records, page=min(page, total_pages),
                       total_pages=total_pages, event=event)
    return http.Response.html(render_shell(
        title="Audit Trail", content=body, user=req.user,
        current_path="/organizer/audit", csrf_token=_csrf(req), event=event))


def handle_organizer_publish(req: http.Request) -> http.Response:
    """Freeze the standings as a new revision and issue certificates."""
    event = _managed_event(req)
    if event["status"] == "draft":
        raise http.Problem(403, "event_not_published",
                           "Publish the hackathon before releasing its results.",
                           "A draft event is invisible, so the ledger would have "
                           "no readers.")
    note = req.field("note", "").strip() or "Manual release from the command center."
    publication = results_mod.publish(event, actor=_actor(req.user), note=note,
                                      board=scoring.scoreboard(event))
    certificates = results_mod.issue_certificates(event, actor=_actor(req.user))
    audit.record(action="results.certified", entity_type="event", entity_id=event["id"],
                 summary="Issued %d certificates after revision %d" % (
                     len(certificates), publication["revision"]),
                 request=req, after={"revision": publication["revision"],
                                     "certificates": len(certificates)})
    return _redirect_done("/organizer/events/%s/results" % event["id"], "published",
                          str(publication["revision"]))


# --- per-event management handlers ------------------------------------------

def _manage_path(event, suffix: str = "") -> str:
    """`/organizer/events/{id}` plus a tab, so redirect targets cannot drift."""
    return "/organizer/events/%s%s" % (event["id"], suffix)


def handle_event_stages(req: http.Request) -> http.Response:
    """The stage table for one event, plus what this event invented itself."""
    event = _event_scope(req)
    body = event_stages_page(event=event, stages=events_mod.stages(event),
                             csrf_token=_csrf(req))
    return http.Response.html(render_shell(
        title="Stages", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event, notice=_done_note(req)))


def handle_event_stage_add(req: http.Request) -> http.Response:
    """Add a stage an organizer invented; the six canonical ones already exist."""
    event = _event_scope(req)
    stage_id = eventadmin.add_stage(event, req.form, _actor(req.user))
    audit.record(action="stage.added", entity_type="stage", entity_id=stage_id,
                 summary="Added a stage to %s" % event["name"], request=req,
                 after={"name": req.field("name", "")[:80]})
    return _redirect_done(_manage_path(event, "/stages"), "stage-added",
                          req.field("name", "")[:80])


def handle_event_stage_remove(req: http.Request) -> http.Response:
    """Remove a stage. The event's own windows are never touched by this."""
    event = _event_scope(req)
    name = eventadmin.remove_stage(event, req.field("stage_id", ""))
    audit.record(action="stage.removed", entity_type="event", entity_id=event["id"],
                 summary="Removed the %s stage from %s" % (name, event["name"]),
                 request=req, before={"name": name})
    return _redirect_done(_manage_path(event, "/stages"), "stage-removed", name)


def handle_event_teams(req: http.Request) -> http.Response:
    """Who is competing in one hackathon, team by team."""
    event = _event_scope(req)
    teams, members_by_team = _event_teams(event)
    body = event_roster_page(event=event, teams=teams, members_by_team=members_by_team)
    return http.Response.html(render_shell(
        title="Teams", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event))


def handle_event_submissions(req: http.Request) -> http.Response:
    """Every submission this hackathon holds, superseded copies included."""
    event = _event_scope(req)
    projects = _decorate_projects(db.query(
        PROJECT_SELECT + " WHERE p.event_id = ? ORDER BY p.title ASC", (event["id"],)))
    body = submissions_list(projects=projects, event=event)
    return http.Response.html(render_shell(
        title="Submissions", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event))


def handle_event_judges(req: http.Request) -> http.Response:
    """This event's judge roster and the invitations behind it."""
    event = _event_scope(req)
    invitations = db.dicts(db.query(
        """SELECT * FROM judge_invitations WHERE event_id = ?
            ORDER BY created_at DESC""", (event["id"],)))
    body = event_judges_page(event=event, judges=_event_judges(event),
                             invitations=invitations, csrf_token=_csrf(req))
    return http.Response.html(render_shell(
        title="Judges", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event, notice=_done_note(req)))


def handle_event_judge_invite(req: http.Request) -> http.Response:
    """Put a judge on this event's roster, creating the login when needed."""
    event = _event_scope(req)
    invited = eventadmin.invite_judge(event, req.form, _actor(req.user))
    audit.record(action="judge.invited", entity_type="event", entity_id=event["id"],
                 summary="Invited %s to judge %s" % (invited["name"], event["name"]),
                 request=req, after={"email": invited["email"],
                                     "account_created": invited["created"]})
    return _redirect_done(_manage_path(event, "/judges"), "judge-invited",
                          invited["name"])


def handle_event_assignments(req: http.Request) -> http.Response:
    """Hand work out inside one hackathon, and see what is still unscored."""
    event = _event_scope(req)
    projects = _decorate_projects(db.query(
        PROJECT_SELECT + """ WHERE p.event_id = ? AND p.status = 'submitted'
                             AND p.duplicate_of IS NULL ORDER BY p.title ASC""",
        (event["id"],)))
    body = event_assignments_page(event=event, projects=projects,
                                  judges=_event_judges(event),
                                  assignments=_event_assignments(event),
                                  csrf_token=_csrf(req))
    return http.Response.html(render_shell(
        title="Assignments", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event, notice=_done_note(req)))


def handle_event_assign(req: http.Request) -> http.Response:
    """Assign one submission to one judge -- both from this event."""
    event = _event_scope(req)
    assignment = eventadmin.assign_project(event, req.form, _actor(req.user))
    audit.record(action="assignment.created", entity_type="assignment",
                 entity_id=assignment["assignment_id"],
                 summary="Assigned %s to %s" % (assignment["project_title"],
                                                assignment["judge_name"]),
                 request=req, after={"judge_id": assignment["judge_id"]})
    return _redirect_done(_manage_path(event, "/assignments"), "assigned",
                          "%s to %s" % (assignment["project_title"],
                                        assignment["judge_name"]))


def handle_event_unassign(req: http.Request) -> http.Response:
    """Revoke an assignment without deleting the row that recorded it."""
    event = _event_scope(req)
    revoked = eventadmin.revoke_assignment(event, req.form, _actor(req.user))
    audit.record(action="assignment.revoked", entity_type="event",
                 entity_id=event["id"],
                 summary="Revoked %s from %s" % (revoked["project_title"],
                                                 revoked["judge_name"]),
                 request=req)
    return _redirect_done(_manage_path(event, "/assignments"), "revoked",
                          "%s from %s" % (revoked["project_title"],
                                          revoked["judge_name"]))


def handle_event_reviews(req: http.Request) -> http.Response:
    """Every review recorded against this event, with its normalized score."""
    event = _event_scope(req)
    body = event_reviews_page(event=event, reviews=_event_reviews(event))
    return http.Response.html(render_shell(
        title="Reviews", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event))


def handle_event_results_page(req: http.Request) -> http.Response:
    """This event's standings as its organizers see them, plus the publish switch."""
    event = _event_scope(req)
    publication = events_mod.results_published(event)
    ranked = ([_published_row(item, index) for index, item in enumerate(
                   results_mod.publication_rows(publication), start=1)]
              if publication is not None
              else [_live_row(project) for project in scoring.scoreboard(event)["ranked"]])
    body = event_results_page(event=event, ranked=ranked,
                             is_published=publication is not None,
                             publication=publication, csrf_token=_csrf(req),
                             user_role=req.user["role"])
    return http.Response.html(render_shell(
        title="Results", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event, notice=_done_note(req)))


def handle_event_publish(req: http.Request) -> http.Response:
    """Freeze this hackathon's standings as a new revision, and certify them."""
    event = _event_scope(req)
    if event["status"] == "draft":
        raise http.Problem(403, "event_not_published",
                           "Publish the hackathon before releasing its results.",
                           "A draft event is invisible, so the ledger would have "
                           "no readers.")
    note = req.field("note", "").strip() or ("Released by %s from the management page."
                                             % req.user["name"])
    publication = results_mod.publish(event, actor=_actor(req.user), note=note,
                                      board=scoring.scoreboard(event))
    certificates = results_mod.issue_certificates(event, actor=_actor(req.user))
    audit.record(action="results.published", entity_type="event", entity_id=event["id"],
                 summary="Published revision %d for %s" % (publication["revision"],
                                                           event["name"]),
                 request=req, after={"revision": publication["revision"],
                                     "certificates": len(certificates)})
    return _redirect_done(_manage_path(event, "/results"), "published",
                          str(publication["revision"]))


def handle_event_audit(req: http.Request) -> http.Response:
    """This hackathon's slice of the append-only log."""
    event = _event_scope(req)
    page = _page_number(req)
    records, total_pages = _event_audit(event, page=page)
    body = audit_trail(records=records, page=min(page, total_pages),
                       total_pages=total_pages,
                       base_url=_manage_path(event, "/audit"), event=event)
    return http.Response.html(render_shell(
        title="Audit Trail", content=body, user=req.user, current_path="/organizer",
        csrf_token=_csrf(req), event=event))


def handle_event_settings(req: http.Request) -> http.Response:
    """The settings form for one hackathon, plus who else organizes it."""
    event = _event_scope(req)
    return _event_settings_response(req, event, eventadmin.form_from_event(event), {})


def handle_event_settings_save(req: http.Request) -> http.Response:
    """Validate a settings edit, then apply it to this event and nothing else."""
    event = _event_scope(req)
    values, errors = eventadmin.validate(req.form, event=event)
    if errors:
        audit.refused(req, "event.update_refused",
                      "Refused to save %s: %s" % (event["id"], ", ".join(sorted(errors))),
                      entity_type="event", entity_id=event["id"])
        return _event_settings_response(req, event, dict(req.form), errors)

    eventadmin.update(event, values, _actor(req.user))
    audit.record(action="event.updated", entity_type="event", entity_id=event["id"],
                 summary="Saved the settings for %s" % values["name"], request=req,
                 after={"slug": values["slug"], "status": values["status"],
                        "tracks": len(values["tracks"]),
                        "criteria": len(values["criteria"])})
    return _redirect_done(_manage_path(event, "/settings"), "saved")


def _event_settings_response(req: http.Request, event: dict, values: dict,
                             errors: dict) -> http.Response:
    """Render the settings form; a refused save keeps every value that was typed."""
    body = event_settings_page(event=event, values=values, errors=errors,
                               csrf_token=_csrf(req),
                               organizers=events_mod.organizers_of(event["id"]))
    return http.Response.html(
        render_shell(title="Settings", content=body, user=req.user,
                     current_path="/organizer", csrf_token=_csrf(req), event=event,
                     notice=_done_note(req),
                     error=("Nothing was saved: %d field%s need attention."
                            % (len(errors), "" if len(errors) == 1 else "s"))
                           if errors else None),
        status=400 if errors else 200)


def handle_event_organizer_add(req: http.Request) -> http.Response:
    """Add an organizer to this hackathon's roster."""
    event = _event_scope(req)
    added = eventadmin.add_organizer(event, req.form, _actor(req.user))
    audit.record(action="organizer.added", entity_type="event", entity_id=event["id"],
                 summary="Added %s as an organizer of %s" % (added["name"],
                                                             event["name"]),
                 request=req, after={"user_id": added["user_id"],
                                     "account_created": added["created"]})
    return _redirect_done(_manage_path(event, "/settings"), "organizer-added",
                          added["name"])


def handle_event_organizer_remove(req: http.Request) -> http.Response:
    """Remove an organizer's access to this event, never the last one."""
    event = _event_scope(req)
    name = eventadmin.remove_organizer(event, req.field("user_id", ""))
    audit.record(action="organizer.removed", entity_type="event", entity_id=event["id"],
                 summary="Removed %s from the organizers of %s" % (name, event["name"]),
                 request=req, before={"user_id": req.field("user_id", "")})
    return _redirect_done(_manage_path(event, "/settings"), "organizer-removed", name)


# --- API and acceptance endpoints -------------------------------------------

def handle_api_judge_scores(req: http.Request) -> http.Response:
    """Evaluation rows as JSON, restricted to what the caller may see.

    The DOGFOOD suite sends judge B to judge A's address and expects a refusal.
    That refusal lives here, in the API: hiding the table in a template hides a
    button, not a record.
    """
    caller = req.user
    event_ref = req.q("event", "").strip()
    event = _event_row(events_mod.require_event(event_ref)) if event_ref else _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")

    requested = req.q("judge", "").strip()
    target_judge_id = ""
    if caller["role"] == "judge":
        if requested and requested not in (caller["id"], caller.get("fixture_id")):
            audit.refused(req, "scores.refused",
                          "judge %s asked to read %s" % (caller["email"], requested),
                          entity_type="event", entity_id=event["id"])
            raise http.Problem(403, "peer_scores_forbidden",
                               "Judges may only read their own evaluations.",
                               "Requested judge: %s." % requested)
        target_judge_id = caller["id"]
    elif caller["role"] in ("organizer", "admin"):
        if not events_mod.can_manage(caller, event):
            audit.refused(req, "event.manage_refused",
                          "%s asked for the evaluation scores of %s"
                          % (caller["email"], event["id"]),
                          entity_type="event", entity_id=event["id"])
            raise http.Problem(403, "not_your_event",
                               "You do not manage that hackathon.",
                               "Evaluation data is scoped to the events you run.")
        if requested:
            row = db.one("""SELECT id FROM users
                             WHERE id = ? OR fixture_id = ? OR email = ? COLLATE NOCASE""",
                         (requested, requested, requested))
            if row is None:
                raise http.Problem(404, "judge_not_found",
                                   "No judge matches that reference.",
                                   "Looked up id, fixture id and email for %r." % requested)
            target_judge_id = row["id"]
    else:
        audit.refused(req, "scores.refused",
                      "%s (a %s) asked to read evaluation scores" % (
                          caller["email"], caller["role"]),
                      entity_type="event", entity_id=event["id"])
        raise http.Problem(403, "forbidden",
                           "Only judges and organizers may read evaluation scores.")

    criteria = scoring.criteria_for_event(event["id"])
    reviews = scoring.load_reviews(event["id"], judge_id=target_judge_id,
                                   project_id=req.q("project", "").strip())
    payload = [{
        "review_id": review["id"], "project_id": review["project_id"],
        "project_title": review["project_title"], "team_name": review["team_name"],
        "judge_user_id": review["judge_user_id"], "judge_name": review["judge_name"],
        "status": review["status"], "weighted_raw": review["weighted_raw"],
        "raw": scoring.weighted_raw(review["scores"], criteria),
        "normalized": review["normalized"], "comment": review["comment"],
        "submitted_at": review["submitted_at"], "scores": review["scores"],
    } for review in reviews]

    return http.Response.json({
        "event_id": event["id"], "event": event["name"],
        "judge_user_id": target_judge_id or None,
        "scope": ("own evaluations" if caller["role"] == "judge" else "all evaluations"),
        "count": len(payload), "scores": payload})


def handle_api_export_csv(req: http.Request) -> http.Response:
    """Standings as CSV. Published rows when a publication exists, live otherwise.

    `?event=<id or slug>` exports a particular hackathon; without it the primary
    event is used, which is the one `.dogfood.toml` points at. Either way the
    caller has to manage the event they are asking to export.
    """
    reference = req.q("event", "").strip()
    event = (_event_row(events_mod.require_event(reference)) if reference
             else _event_row(events_mod.primary_event()))
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    if not events_mod.can_manage(req.user, event):
        audit.refused(req, "event.manage_refused",
                      "%s asked to export %s" % (req.user["email"], event["id"]),
                      entity_type="event", entity_id=event["id"])
        raise http.Problem(403, "not_your_event",
                           "You do not manage that hackathon.",
                           "Standings are exported one event at a time.")

    publication = events_mod.results_published(event)
    if publication is not None:
        rows = [_published_row(item, index) for index, item in enumerate(
            results_mod.publication_rows(publication), start=1)]
    else:
        rows = [_live_row(project) for project in scoring.scoreboard(event)["ranked"]]

    headers = ["rank", "project_id", "title", "team", "track", "raw_mean",
               "normalized_mean", "reviews", "coverage", "flags"]
    lines = [util.csv_row(headers)]
    for row in rows:
        lines.append(util.csv_row([
            row.get("published_rank", ""), row.get("project_id", ""),
            row.get("title", ""), row.get("team_name", ""),
            row.get("track") or "General",
            "" if row.get("raw_mean") is None else "%.2f" % row["raw_mean"],
            "" if row.get("normalized_mean") is None else "%.2f" % row["normalized_mean"],
            row.get("review_count", 0), row.get("coverage", ""),
            ";".join(row.get("flags") or [])]))

    audit.record(action="results.exported", entity_type="event", entity_id=event["id"],
                 summary="Exported %d standings rows as CSV" % len(rows), request=req,
                 after={"rows": len(rows), "revision": (publication or {}).get("revision_no")})
    body = "\r\n".join(lines) + "\r\n"
    return http.Response.csv(body, filename="lockdown-%s.csv" % util.slugify(
        event.get("slug") or event["name"], "standings"))
