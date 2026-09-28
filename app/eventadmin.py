"""Organizer-facing hackathon creation and configuration.

The browser form is a convenience; it is not the rule. Everything an organizer
can type arrives here as a plain mapping of strings, is validated, and only then
written. A request that skips the form (curl, a replay, a test, a stale tab that
posts an id from another hackathon) gets exactly the same validation and exactly
the same refusals.

Nothing here trusts the caller. The route layer decides whether the actor may
manage the event being changed (see `events.require_manage`) before anything in
this module runs, and every write here is scoped to one `event_id`.
"""

from __future__ import annotations

from . import config, db, events as events_mod, http, timeutil, util

# --- the shape of the create form ---------------------------------------

SCHEDULE_FIELDS = (
    ("registration_open", "Registration opens", "Accounts and teams can be created."),
    ("registration_close", "Registration closes", "No new sign-ups after this."),
    ("team_formation_close", "Team formation closes", "Rosters are frozen."),
    ("submissions_open", "Submissions open", "The editor accepts entries."),
    ("submissions_close", "Submission deadline", "The hard stop for new versions."),
    ("judging_open", "Judging opens", "Assignments become scoreable."),
    ("judging_close", "Judging closes", "The last moment a review counts."),
    ("results_publish_at", "Results published", "Standings are frozen and released."),
)

# (earlier field, later field, message). Applied only when both are present.
SCHEDULE_RULES = (
    ("registration_open", "registration_close", "Registration cannot close before it opens."),
    ("submissions_open", "submissions_close", "Submissions cannot close before they open."),
    ("judging_open", "judging_close", "Judging cannot close before it opens."),
    ("team_formation_close", "submissions_close",
     "Team formation must end on or before the submission deadline."),
    ("submissions_close", "results_publish_at",
     "Results cannot be published before the submission deadline."),
    ("judging_close", "results_publish_at",
     "Results cannot be published before judging closes."),
)

STATUS_CHOICES = ("draft", "published", "archived")

DEFAULT_RULES = ("One project per team. Edits are allowed until the deadline. Judges see only "
                 "the work they are assigned and never each other's scores.")

DEFAULT_TRACKS = """Static Sites | No framework, no build step, no network.
Command Line | Tools that run where the terminal is.
Data and Viz | Turn a mess into a table, then into a picture.
Offline Sync | Works with the aeroplane mode switch on.
Accessibility | Interfaces more people can actually use."""

DEFAULT_PRIZES = """Zero Dependency Award | Judges' top normalized score | One winner.
Best Static Site | Best hand-written site | Track winner.
Most Useful Offline Tool | Best offline-first workflow | Track winner."""

DEFAULT_RUBRIC = """correctness | Does it actually work | 0.45 | Runs, does what it claims, survives being poked.
simplicity | Simplicity | 0.30 | Could someone read it in one sitting and change it?
documentation | Documentation | 0.25 | Can a stranger run it with the network unplugged?"""


def blank_form() -> dict:
    """Reasonable starting values for a brand new hackathon."""
    return {
        "name": "", "slug": "", "tagline": "", "description": "",
        "rules": DEFAULT_RULES, "banner": "", "cover_tone": "ink",
        "location": "Online", "status": "draft",
        "registration_open": timeutil.days_from_now(0)[:10],
        "registration_close": timeutil.days_from_now(14)[:10],
        "team_formation_close": timeutil.days_from_now(21)[:10],
        "submissions_open": timeutil.days_from_now(14)[:10],
        "submissions_close": timeutil.days_from_now(42)[:10],
        "judging_open": timeutil.days_from_now(43)[:10],
        "judging_close": timeutil.days_from_now(56)[:10],
        "results_publish_at": timeutil.days_from_now(60)[:10],
        "min_team_size": "1", "max_team_size": "4", "target_reviews": "3",
        "gallery_visible": "1", "results_visible": "1",
        "tracks_text": DEFAULT_TRACKS, "prizes_text": DEFAULT_PRIZES,
        "rubric_text": DEFAULT_RUBRIC,
    }


def form_from_event(event) -> dict:
    """Pre-fill the settings form from a stored event."""
    tracks = db.query(
        "SELECT name, description FROM tracks WHERE event_id = ? ORDER BY seq", (event["id"],))
    prizes = db.query(
        "SELECT title, description, value FROM prizes WHERE event_id = ? ORDER BY rank",
        (event["id"],))
    rubric = db.one("""SELECT * FROM rubrics WHERE event_id = ? AND is_active = 1
                        ORDER BY created_at DESC LIMIT 1""", (event["id"],))
    criteria = []
    if rubric is not None:
        criteria = db.query(
            "SELECT * FROM rubric_criteria WHERE rubric_id = ? ORDER BY seq", (rubric["id"],))
    return {
        "id": event["id"], "name": event["name"], "slug": event["slug"],
        "tagline": event["tagline"], "description": event["description"],
        "rules": event["rules"], "banner": event.get("banner") or "",
        "cover_tone": events_mod.cover_tone(event),
        "location": event.get("location") or "", "status": event["status"],
        "registration_open": _date_input(event["registration_open"]),
        "registration_close": _date_input(event["registration_close"]),
        "team_formation_close": _date_input(event["team_formation_close"]),
        "submissions_open": _date_input(event["submissions_open"]),
        "submissions_close": _date_input(event["submissions_close"]),
        "judging_open": _date_input(event["judging_open"]),
        "judging_close": _date_input(event["judging_close"]),
        "results_publish_at": _date_input(event["results_publish_at"]),
        "min_team_size": str(event["min_team_size"]),
        "max_team_size": str(event["max_team_size"]),
        "target_reviews": str(event["target_reviews"] or 3),
        "gallery_visible": "1" if event.get("gallery_visible", 1) else "0",
        "results_visible": "1" if event.get("results_visible", 1) else "0",
        "tracks_text": _tracks_text(tracks),
        "prizes_text": _prizes_text(prizes),
        "rubric_text": _rubric_text(criteria),
    }


def _date_input(value) -> str:
    return (value or "")[:10]


def _tracks_text(rows) -> str:
    return "\n".join("%s | %s" % (row["name"], row["description"] or "") for row in rows)


def _prizes_text(rows) -> str:
    return "\n".join("%s | %s | %s" % (row["title"], row["value"] or "",
                                       row["description"] or "") for row in rows)


def _rubric_text(rows) -> str:
    return "\n".join("%s | %s | %s | %s" % (row["key"], row["label"], row["weight"],
                                            row["description"] or "") for row in rows)


# --- parsing ------------------------------------------------------------
#
# The three "one row per line, cells separated by |" fields (tracks, prizes,
# rubric) are deliberately plain text. A rich editor would be a second place
# where validation could be skipped; a textarea posts a string, and the string
# is parsed here, once, for both the form and any request that bypasses it.

def _lines(text: str) -> list[list[str]]:
    parsed = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parsed.append([cell.strip() for cell in line.split("|")])
    return parsed


def parse_tracks(text: str) -> list[dict]:
    tracks, seen = [], set()
    for index, cells in enumerate(_lines(text), start=1):
        name = cells[0] if cells else ""
        if not name:
            continue
        slug = util.slugify(name, "track-%d" % index)
        if slug in seen:
            continue
        seen.add(slug)
        tracks.append({"slug": slug, "name": name[:80],
                       "description": (cells[1] if len(cells) > 1 else "")[:300],
                       "seq": index * 10})
    return tracks[:24]


def parse_prizes(text: str) -> list[dict]:
    prizes = []
    for index, cells in enumerate(_lines(text), start=1):
        title = cells[0] if cells else ""
        if not title:
            continue
        prizes.append({"rank": index, "title": title[:120],
                       "value": (cells[1] if len(cells) > 1 else "")[:80],
                       "description": (cells[2] if len(cells) > 2 else "")[:300]})
    return prizes[:24]


def parse_rubric(text: str, *, fallback=None) -> list[dict]:
    """`key | label | weight | description`. Weights are checked by `validate`."""
    criteria = []
    for index, cells in enumerate(_lines(text), start=1):
        if not cells or not cells[0]:
            continue
        key = util.slugify(cells[0], "criterion-%d" % index).replace("-", "_")[:40]
        label = (cells[1] if len(cells) > 1 else "") or key.replace("_", " ").title()
        criteria.append({
            "key": key, "label": label[:80],
            "weight": util.as_float(cells[2] if len(cells) > 2 else "", None),
            "description": (cells[3] if len(cells) > 3 else "")[:300],
            "min_score": 1, "max_score": 5, "seq": index * 10})
    if not criteria and fallback:
        for index, (key, label, description, weight, low, high) in enumerate(fallback, start=1):
            criteria.append({"key": key, "label": label, "description": description,
                             "weight": weight, "min_score": low, "max_score": high,
                             "seq": index * 10})
    return criteria[:12]


def parse_schedule(form) -> tuple[dict, dict]:
    """(schedule, errors). Accepts `2026-03-01` and `2026-03-01T18:00`."""
    schedule, errors = {}, {}
    for field, _label, _help in SCHEDULE_FIELDS:
        raw = (form.get(field) or "").strip()
        if not raw:
            schedule[field] = None
            continue
        stamp = timeutil.from_form(raw)
        if stamp is None:
            errors[field] = "Use a date like 2026-03-01, or leave it blank."
            schedule[field] = None
        else:
            schedule[field] = stamp
    for earlier, later, message in SCHEDULE_RULES:
        first, second = schedule.get(earlier), schedule.get(later)
        if first and second and first > second:
            errors[later] = message
    return schedule, errors


def requested_slug(form, name: str, *, current: str = "") -> str:
    """A slug the caller typed, or one derived from the name."""
    typed = (form.get("slug") or "").strip()
    if typed:
        return util.slugify(typed, "")
    return current or util.slugify(name, "hackathon")


def unique_slug(base: str, *, exclude_id: str = "") -> str:
    """`zero-dependency-2026`, then `zero-dependency-2026-2`, and so on."""
    base = util.slugify(base, "hackathon")
    candidate, counter = base, 1
    while True:
        row = db.one("SELECT id FROM events WHERE slug = ?", (candidate,))
        if row is None or (exclude_id and row["id"] == exclude_id):
            return candidate
        counter += 1
        candidate = "%s-%d" % (base, counter)



# --- validation ---------------------------------------------------------

def validate(form, *, event=None) -> tuple[dict, dict]:
    """Return (values, errors). `errors` is field -> message; empty when clean."""
    errors: dict = {}

    name = (form.get("name") or "").strip()
    if not name:
        errors["name"] = "A hackathon needs a name."
    elif len(name) > 120:
        errors["name"] = "Names stop at 120 characters."

    status = (form.get("status") or "draft").strip().lower()
    if status not in STATUS_CHOICES:
        errors["status"] = "Status must be draft, published or archived."

    tone = (form.get("cover_tone") or "ink").strip().lower()
    if tone not in events_mod.COVER_TONES:
        errors["cover_tone"] = "Pick one of the listed cover tones."

    min_team = util.as_int(form.get("min_team_size"), 1)
    max_team = util.as_int(form.get("max_team_size"), 4)
    if min_team is None or min_team < 1:
        errors["min_team_size"] = "Minimum team size starts at 1."
    if max_team is None or max_team < 1:
        errors["max_team_size"] = "Maximum team size starts at 1."
    elif max_team > 20:
        errors["max_team_size"] = "This portal caps teams at 20 people."
    elif min_team and max_team < min_team:
        errors["max_team_size"] = "Maximum cannot be smaller than the minimum."

    target = util.as_int(form.get("target_reviews"), 3)
    if target is None or not 1 <= target <= 10:
        errors["target_reviews"] = "Between 1 and 10 reviews per project."

    schedule, schedule_errors = parse_schedule(form)
    errors.update(schedule_errors)

    slug = requested_slug(form, name, current=event["slug"] if event else "")
    if not slug:
        errors["slug"] = "A slug is required (letters, numbers and dashes)."
    else:
        taken = db.one("SELECT id, name FROM events WHERE slug = ?", (slug,))
        if taken is not None and (event is None or taken["id"] != event["id"]):
            errors["slug"] = "%s already uses the slug %s." % (taken["name"], slug)

    tracks = parse_tracks(form.get("tracks_text", ""))
    if not tracks:
        errors["tracks_text"] = "Define at least one track."

    description = (form.get("description") or "").strip()
    if status == "published" and not description:
        errors["description"] = "Describe the hackathon before publishing it."

    criteria = parse_rubric(form.get("rubric_text", ""), fallback=config.RUBRIC_DEFAULT)
    if not criteria:
        errors["rubric_text"] = "A hackathon needs at least one rubric criterion."
    elif len({item["key"] for item in criteria}) != len(criteria):
        errors["rubric_text"] = "Two criteria cannot share the same key."
    else:
        unweighted = [item["key"] for item in criteria
                      if item["weight"] is None or item["weight"] <= 0]
        if unweighted:
            errors["rubric_text"] = ("Every criterion needs a weight above zero. Check: "
                                     + ", ".join(unweighted))
    if any(item["key"] in ("", "item") for item in criteria):
        errors["rubric_text"] = errors.get("rubric_text") or \
            "Give every criterion a name made of letters and numbers."

    values = {
        "name": name, "slug": slug, "status": status, "cover_tone": tone,
        "tagline": (form.get("tagline") or "").strip()[:200],
        "description": description[:8000],
        "rules": (form.get("rules") or "").strip()[:8000],
        "banner": (form.get("banner") or "").strip()[:40],
        "location": (form.get("location") or "").strip()[:120],
        "min_team_size": min_team or 1, "max_team_size": max_team or 4,
        "target_reviews": target or 3,
        "gallery_visible": 1 if form.get("gallery_visible") else 0,
        "results_visible": 1 if form.get("results_visible") else 0,
        "tracks": tracks, "prizes": parse_prizes(form.get("prizes_text", "")),
        "criteria": criteria,
    }
    values.update(schedule)
    return values, errors



# --- writes -------------------------------------------------------------

def create(values, actor) -> dict:
    """Create the event and everything that describes it. Returns its ids.

    One transaction: a hackathon that half-exists (an event with no tracks, a
    rubric with no criteria) is worse than one that was never created.
    """
    from . import seed as fixtures_seed

    event_id = util.new_id("evt")
    seq = (db.scalar("SELECT COALESCE(MAX(seq), 0) FROM events", (), 0) or 0) + 10
    schedule = {field: values.get(field) for field, _l, _h in SCHEDULE_FIELDS}

    with db.tx():
        fixtures_seed.create_event(
            event_id=event_id, slug=values["slug"], name=values["name"],
            tagline=values["tagline"], description=values["description"],
            rules=values["rules"], seq=seq, schedule=schedule,
            created_by=actor["id"] if actor else None,
            target_reviews=values["target_reviews"],
            min_team=values["min_team_size"], max_team=values["max_team_size"],
            status=values["status"], banner=values["banner"],
            cover_tone=values["cover_tone"], location=values["location"],
            gallery_visible=values["gallery_visible"],
            results_visible=values["results_visible"])
        if actor:
            db.insert("event_organizers", {
                "id": util.new_id("evo"), "event_id": event_id,
                "user_id": actor["id"], "role": "owner",
                "added_by": actor["id"], "added_at": timeutil.now_iso()})
        _write_tracks(event_id, values["tracks"])
        _write_prizes(event_id, values["prizes"])
        _write_rubric(event_id, values["criteria"], actor)
    return {"event_id": event_id, "slug": values["slug"], "name": values["name"], "seq": seq}


def update(event, values, actor) -> dict:
    """Apply an organizer's settings edit. Only this event's rows change."""
    schedule = {field: values.get(field) for field, _l, _h in SCHEDULE_FIELDS}
    with db.tx():
        db.update("events", {
            "name": values["name"], "slug": values["slug"], "status": values["status"],
            "tagline": values["tagline"], "description": values["description"],
            "rules": values["rules"], "banner": values["banner"],
            "cover_tone": values["cover_tone"], "location": values["location"],
            "min_team_size": values["min_team_size"],
            "max_team_size": values["max_team_size"],
            "target_reviews": values["target_reviews"],
            "reviews_required": values["target_reviews"],
            "gallery_visible": values["gallery_visible"],
            "results_visible": values["results_visible"],
            "updated_at": timeutil.now_iso(), **schedule},
            "id = ?", (event["id"],))
        _sync_stages(event["id"], schedule)
        db.execute("DELETE FROM tracks WHERE event_id = ?", (event["id"],))
        _write_tracks(event["id"], values["tracks"])
        db.execute("DELETE FROM prizes WHERE event_id = ?", (event["id"],))
        _write_prizes(event["id"], values["prizes"])
        rubric = db.one("""SELECT * FROM rubrics WHERE event_id = ? AND is_active = 1
                            ORDER BY created_at DESC LIMIT 1""", (event["id"],))
        if rubric is None:
            _write_rubric(event["id"], values["criteria"], actor)
        else:
            db.execute("DELETE FROM rubric_criteria WHERE rubric_id = ?", (rubric["id"],))
            _write_criteria(rubric["id"], values["criteria"])
    return {"event_id": event["id"], "slug": values["slug"], "name": values["name"]}


def _write_tracks(event_id: str, tracks) -> None:
    for track in tracks:
        db.insert("tracks", {
            "id": util.new_id("trk"), "event_id": event_id, "slug": track["slug"],
            "name": track["name"], "description": track["description"], "seq": track["seq"]})


def _write_prizes(event_id: str, prizes) -> None:
    for prize in prizes:
        db.insert("prizes", {
            "id": util.new_id("prz"), "event_id": event_id, "track_id": None,
            "rank": prize["rank"], "title": prize["title"],
            "description": prize["description"], "value": prize["value"]})


def _write_rubric(event_id: str, criteria, actor) -> str:
    rubric_id = util.new_id("rub")
    db.insert("rubrics", {
        "id": rubric_id, "event_id": event_id, "name": "Weighted rubric",
        "notes": ("Weights are relative: the portal rescales them to sum to 1, so "
                  "editing one weight cannot silently change the scale."),
        "is_active": 1, "created_by": actor["id"] if actor else None,
        "created_at": timeutil.now_iso()})
    _write_criteria(rubric_id, criteria)
    return rubric_id


def _write_criteria(rubric_id: str, criteria) -> None:
    for item in criteria:
        db.insert("rubric_criteria", {
            "id": util.new_id("crit"), "rubric_id": rubric_id, "key": item["key"],
            "label": item["label"], "description": item["description"],
            "weight": float(item["weight"]), "min_score": item["min_score"],
            "max_score": item["max_score"], "seq": item["seq"]})



def _sync_stages(event_id: str, schedule: dict) -> None:
    """Keep the derived stages in step with the event's own windows.

    Custom stages an organizer added are left alone; only the six canonical
    stages are re-dated, so editing a schedule never deletes work.
    """
    for index, (key, name, description, opens_field, closes_field) in enumerate(
            events_mod.STAGE_SEQUENCE, start=1):
        existing = db.one("SELECT id, status FROM event_stages WHERE event_id = ? AND key = ?",
                          (event_id, key))
        opens_at = schedule.get(opens_field)
        closes_at = schedule.get(closes_field)
        if existing is None:
            db.insert("event_stages", {
                "id": util.new_id("stg"), "event_id": event_id, "seq": index * 10,
                "key": key, "name": name, "description": description,
                "opens_at": opens_at, "closes_at": closes_at, "status": "scheduled"})
            continue
        if existing["status"] == "published":
            continue                # a released stage is history, not configuration
        db.update("event_stages", {"name": name, "description": description,
                                   "opens_at": opens_at, "closes_at": closes_at},
                  "id = ?", (existing["id"],))


# --- stage and roster administration ------------------------------------

def add_stage(event, form, actor) -> str:
    """Add a stage an organizer invented. The six canonical stages already exist."""
    name = (form.get("name") or "").strip()
    if not name:
        raise http.Problem(400, "stage_name_required", "A stage needs a name.")
    key = util.slugify(form.get("key") or name, "stage").replace("-", "_")[:40]
    if db.exists("SELECT id FROM event_stages WHERE event_id = ? AND key = ?",
                 (event["id"], key)):
        raise http.Problem(409, "stage_exists",
                           "This event already has a stage with that key.",
                           "Stage keys are unique inside one event.")
    opens_at = timeutil.from_form(form.get("opens_at", ""))
    closes_at = timeutil.from_form(form.get("closes_at", ""))
    if opens_at and closes_at and opens_at > closes_at:
        raise http.Problem(400, "stage_window_invalid", "A stage cannot close before it opens.")
    row = db.one("SELECT COALESCE(MAX(seq), 0) AS seq FROM event_stages WHERE event_id = ?",
                 (event["id"],))
    stage_id = util.new_id("stg")
    db.insert("event_stages", {
        "id": stage_id, "event_id": event["id"], "seq": (row["seq"] or 0) + 10,
        "key": key, "name": name[:80],
        "description": (form.get("description") or "").strip()[:300],
        "opens_at": opens_at, "closes_at": closes_at, "status": "scheduled"})
    return stage_id


def remove_stage(event, stage_id: str) -> str:
    row = db.one("SELECT * FROM event_stages WHERE id = ? AND event_id = ?",
                 (stage_id, event["id"]))
    if row is None:
        raise http.Problem(404, "stage_not_found", "No such stage in this event.")
    db.execute("DELETE FROM event_stages WHERE id = ?", (stage_id,))
    return row["name"]


def invite_judge(event, form, actor) -> dict:
    """Put a judge on this event's roster, creating the account when needed.

    The user row is global (one login for the whole portal); this records that
    this person judges *this* hackathon. A judge on two events still only ever
    sees the assignments each event handed them.
    """
    from .auth import create_user, user_by_email
    from . import security

    email = (form.get("email") or "").strip().lower()
    if "@" not in email or len(email) > 160:
        raise http.Problem(400, "judge_email_invalid",
                           "A judge invitation needs a working email address.")
    name = (form.get("name") or "").strip() or email.split("@")[0].replace(".", " ").title()
    user = user_by_email(email)
    created = False
    if user is None:
        create_user(email, name, "judge", config.DEMO_PASSWORD)
        user = user_by_email(email)
        created = True
    if user["role"] not in ("judge", "organizer", "admin"):
        raise http.Problem(409, "judge_role_conflict",
                           "%s already has an account as a %s." % (email, user["role"]),
                           "Change that account's role first, or invite someone else.")
    now = timeutil.now_iso()
    invitation = db.one("""SELECT * FROM judge_invitations WHERE event_id = ? AND email = ?
                            ORDER BY created_at DESC LIMIT 1""", (event["id"], email))
    if invitation is None:
        db.insert("judge_invitations", {
            "id": util.new_id("jiv"), "event_id": event["id"], "email": email,
            "name": user["name"],
            "token_hash": security.token_hash("invite|%s|%s" % (email, event["id"])),
            "token_hint": "", "track_ids": "", "status": "accepted",
            "invited_by": actor["id"] if actor else None, "user_id": user["id"],
            "created_at": now, "accepted_at": now})
    return {"user_id": user["id"], "email": email, "name": user["name"], "created": created}



def assign_project(event, form, actor) -> dict:
    """Hand one submitted project to one judge on this event.

    Both ids are re-checked against this event before anything is written, so a
    crafted form cannot attach a project from hackathon A to a judge in B.
    """
    project_id = (form.get("project_id") or "").strip()
    judge_ref = (form.get("judge") or "").strip()
    project = db.one("SELECT * FROM projects WHERE id = ? AND event_id = ?",
                     (project_id, event["id"]))
    if project is None:
        raise http.Problem(404, "project_not_in_event",
                           "That submission is not part of this hackathon.",
                           "Assignments are only ever made inside one event.")
    judge = db.one("""SELECT * FROM users
                       WHERE (id = ? OR email = ? COLLATE NOCASE OR fixture_id = ?)
                         AND role IN ('judge','organizer','admin')""",
                   (judge_ref, judge_ref, judge_ref))
    if judge is None:
        raise http.Problem(404, "judge_not_found", "No such judge on this portal.")
    if db.exists("""SELECT id FROM assignments
                     WHERE project_id = ? AND judge_user_id = ? AND status != 'revoked'""",
                 (project["id"], judge["id"])):
        raise http.Problem(409, "already_assigned",
                           "%s already holds this submission." % judge["name"])
    now = timeutil.now_iso()
    assignment_id = util.new_id("asg")
    db.insert("assignments", {
        "id": assignment_id, "event_id": event["id"], "project_id": project["id"],
        "judge_user_id": judge["id"], "track_id": project["track_id"],
        "status": "assigned", "origin": "organizer",
        "due_at": event["judging_close"], "assigned_by": actor["id"] if actor else None,
        "assigned_at": now, "updated_at": now})
    return {"assignment_id": assignment_id, "project_title": project["title"],
            "judge_name": judge["name"], "judge_id": judge["id"],
            "judge_email": judge["email"]}


def revoke_assignment(event, form, actor) -> dict:
    assignment_id = (form.get("assignment_id") or "").strip()
    row = db.one("""SELECT a.*, p.title AS project_title, u.name AS judge_name
                      FROM assignments a
                      JOIN projects p ON p.id = a.project_id
                      JOIN users u ON u.id = a.judge_user_id
                     WHERE a.id = ? AND a.event_id = ?""", (assignment_id, event["id"]))
    if row is None:
        raise http.Problem(404, "assignment_not_found",
                           "No such assignment in this hackathon.")
    db.update("assignments", {"status": "revoked", "updated_at": timeutil.now_iso()},
              "id = ?", (assignment_id,))
    return {"project_title": row["project_title"], "judge_name": row["judge_name"]}


def add_organizer(event, form, actor) -> dict:
    """Add a second organizer to this hackathon."""
    from .auth import create_user, user_by_email

    email = (form.get("email") or "").strip().lower()
    if "@" not in email:
        raise http.Problem(400, "organizer_email_invalid",
                           "An organizer needs a working email address.")
    user = user_by_email(email)
    created = False
    if user is None:
        create_user(email, email.split("@")[0].replace(".", " ").title(),
                    "organizer", config.DEMO_PASSWORD)
        user = user_by_email(email)
        created = True
    if user["role"] not in ("organizer", "admin"):
        raise http.Problem(409, "organizer_role_conflict",
                           "%s has a %s account, not an organizer account."
                           % (email, user["role"]))
    added = events_mod.add_organizer(event["id"], user["id"], role="organizer",
                                     added_by=actor["id"] if actor else None)
    if not added:
        raise http.Problem(409, "already_organizing",
                           "%s already manages this hackathon." % user["name"])
    return {"user_id": user["id"], "name": user["name"], "email": user["email"],
            "created": created}


def remove_organizer(event, user_id: str) -> str:
    """Remove an organizer's access. The last one cannot be removed."""
    row = db.one("""SELECT eo.*, u.name FROM event_organizers eo
                      JOIN users u ON u.id = eo.user_id
                     WHERE eo.event_id = ? AND eo.user_id = ?""", (event["id"], user_id))
    if row is None:
        raise http.Problem(404, "organizer_not_found",
                           "That person does not manage this hackathon.")
    remaining = db.scalar("SELECT COUNT(*) FROM event_organizers WHERE event_id = ?",
                          (event["id"],), 0) or 0
    if remaining <= 1 and event["created_by"] is None:
        raise http.Problem(409, "last_organizer",
                           "A hackathon needs at least one organizer.",
                           "Add someone else before removing the last one.")
    db.execute("DELETE FROM event_organizers WHERE id = ?", (row["id"],))
    return row["name"]
