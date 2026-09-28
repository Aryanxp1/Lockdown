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

from . import (audit, auth, config, db, events as events_mod, http,
               results as results_mod, scoring, seed as fixtures_seed, security,
               timeutil, util)
from .views import (
    audit_trail,
    evaluation_form,
    gallery as gallery_view,
    judge_dashboard,
    judges_roster,
    landing,
    organizer_dashboard,
    participant_dashboard,
    project_detail as project_detail_view,
    project_form,
    render_shell,
    results_leaderboard,
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

    # --- sessions -------------------------------------------------------
    r.get("/signin", handle_signin_page, public=True)
    r.get("/login", handle_signin_page, public=True)
    # The sign-in POST cannot require a CSRF token: the visitor has no session
    # yet, so there is nothing to compare a token against.
    r.post("/signin", handle_signin, public=True)
    r.post("/signout", handle_signout, public=True, csrf=True)

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
    r.get("/organizer", handle_organizer_dashboard, roles=STAFF_ROLES)
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
    """Published standings, and nothing else.

    Before publication this page renders an embargo panel for everyone except
    organizers, and the handler hands the template an empty table rather than
    the live numbers, so an embargo cannot be undone by editing the HTML.
    """
    event = _event_row(events_mod.primary_event())
    if event is None:
        return http.Response.html(render_shell(
            title="Results", user=req.user, csrf_token=_csrf(req),
            content="<p>No event has been published in this portal yet.</p>"))

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

    body = results_leaderboard(event=event, ranked=ranked,
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

def handle_organizer_dashboard(req: http.Request) -> http.Response:
    """The operations desk: counts, recent actions, publishing."""
    event = _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    counts = events_mod.event_counts(event["id"])
    stats = {"projects": counts["projects_submitted"], "teams": counts["teams"],
             "judges": counts["judges"], "reviews": counts["reviews_submitted"],
             "drafts": counts["projects_draft"], "pending": counts["reviews_draft"],
             "assignments": counts["assignments"]}
    recent = _audit_rows(db.query(
        "SELECT * FROM audit_log ORDER BY at DESC, rowid DESC LIMIT 8"))
    body = organizer_dashboard(event=dict(event), stats=stats, recent_audit=recent,
                               csrf_token=_csrf(req))
    return http.Response.html(render_shell(
        title="Operations Command", content=body, user=req.user,
        current_path="/organizer", csrf_token=_csrf(req), event=event))


def handle_organizer_submissions(req: http.Request) -> http.Response:
    """Every submission in the event, superseded duplicates included."""
    event = _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    projects = _decorate_projects(db.query(
        PROJECT_SELECT + " WHERE p.event_id = ? ORDER BY p.title ASC", (event["id"],)))
    body = submissions_list(projects=projects, event=dict(event))
    return http.Response.html(render_shell(
        title="Submissions", content=body, user=req.user,
        current_path="/organizer/submissions", csrf_token=_csrf(req), event=event))


def handle_organizer_judges(req: http.Request) -> http.Response:
    """Judge roster plus the calibration numbers normalization depends on."""
    event = _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    judges = db.dicts(db.query(
        "SELECT * FROM users WHERE role = 'judge' ORDER BY name ASC"))
    criteria = scoring.normalise_weights(scoring.criteria_for_event(event["id"]))
    model = scoring.normalize(scoring.load_reviews(event["id"]), criteria)
    stats = {}
    for judge_id, row in model["judges"].items():
        item = dict(row)
        item["flags"] = scoring.flag_labels(item.get("flags") or [])
        stats[judge_id] = item
    body = judges_roster(judges=judges, stats=stats)
    return http.Response.html(render_shell(
        title="Judges", content=body, user=req.user,
        current_path="/organizer/judges", csrf_token=_csrf(req), event=event))


def handle_organizer_audit(req: http.Request) -> http.Response:
    """The append-only log, newest first."""
    page = _page_number(req)
    per_page = 50
    total = db.scalar("SELECT COUNT(*) FROM audit_log", (), 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = _audit_rows(db.query(
        """SELECT * FROM audit_log ORDER BY at DESC, rowid DESC LIMIT ? OFFSET ?""",
        (per_page, (page - 1) * per_page)))
    body = audit_trail(records=records, page=page, total_pages=total_pages)
    return http.Response.html(render_shell(
        title="Audit Trail", content=body, user=req.user,
        current_path="/organizer/audit", csrf_token=_csrf(req)))


def handle_organizer_publish(req: http.Request) -> http.Response:
    """Freeze the standings as a new revision and issue certificates."""
    event = _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")
    note = req.field("note", "").strip() or "Manual release from the command center."
    publication = results_mod.publish(event, actor=_actor(req.user), note=note,
                                      board=scoring.scoreboard(event))
    certificates = results_mod.issue_certificates(event, actor=_actor(req.user))
    audit.record(action="results.certified", entity_type="event", entity_id=event["id"],
                 summary="Issued %d certificates after revision %d" % (
                     len(certificates), publication["revision"]),
                 request=req, after={"revision": publication["revision"],
                                     "certificates": len(certificates)})
    return http.Response.redirect("/results")


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
    """Standings as CSV. Published rows when a publication exists, live otherwise."""
    event = _event_row(events_mod.primary_event())
    if event is None:
        raise http.Problem(404, "no_events", "No event exists in this portal yet.")

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
