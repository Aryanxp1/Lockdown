"""Seed the portal from the official DOGFOOD fixtures.

`fixtures.json` is input, not a data model. This module loads it, repairs the
awkward cases on purpose rather than by accident, and leaves the orchestration
to `app/boot.py`.

The transformation in one paragraph: fixture ids become primary keys, so any row
in the portal can be traced back to the file it came from. The event's only date
is `submissions_close`, so the rest of the schedule is derived from it and the
event is honest about being over. Team member emails are resolved into real
`users`. The duplicate submission (prj_41 duplicating prj_07) keeps both rows: the
later one is canonical, the earlier one is linked as superseded, and reviews stay
attached to the version they actually scored. Scores become finalized `reviews`
with per-criterion `review_scores`, and the missing slots in half-finished review
batches become *pending assignments*, so the organizer sees the same unfinished
work the fixtures describe.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys

from . import config, db, events as events_mod, scoring, security, timeutil, util

EVENT_DESCRIPTION = (
    "Sample Hack 2026 ran for one weekend across eight tracks. Forty teams submitted "
    "forty-one projects (one team resubmitted, and both versions are kept). Thirty "
    "judges reviewed what they were assigned; two review batches were never finished "
    "and a handful of judges scored everything the same. All of that is loaded verbatim "
    "from fixtures.json, so this portal can be compared against any other portal "
    "holding the same data."
)

EVENT_RULES = (
    "Teams of one to four. One project per team, resubmission allowed until the "
    "deadline and kept as a new immutable version. Judges score only what they are "
    "assigned and never see each other's scores. Scores are normalized per judge "
    "before ranking; the method is published in JUDGING.md. Published results are "
    "snapshots and are never edited in place."
)


def _shift(stamp: str, days: float = 0, hours: float = 0) -> str:
    parsed = timeutil.parse(stamp)
    if parsed is None:
        return ""
    return timeutil.iso(parsed + _dt.timedelta(days=days, hours=hours))


def load_fixtures(path=None) -> dict:
    with open(path or config.FIXTURES_PATH, "rb") as handle:
        return json.load(handle)


def is_seeded() -> bool:
    return bool(db.scalar("SELECT COUNT(*) FROM events", (), 0))


def log(message: str) -> None:
    print("[seed] %s" % message, file=sys.stdout, flush=True)


def fixture_schedule(fixture: dict) -> tuple:
    """The fixture event's id, name, and the schedule derived from its one date."""
    source = fixture.get("event") or {}
    close = (source.get("submissions_close") or "").strip() or timeutil.days_from_now(-30)
    name = (source.get("name") or "Sample Hack 2026").strip()
    return (source.get("id") or "evt_01").strip(), name, {
        "registration_open": _shift(close, -21),
        "registration_close": _shift(close, -14),
        "team_formation_close": _shift(close, -9),
        "submissions_open": _shift(close, -7),
        "submissions_close": close,
        "judging_open": close,
        "judging_close": _shift(close, 14),
        "results_publish_at": _shift(close, 17),
    }


def unique_slug(table: str, column: str, base: str, scope_column: str = "", scope_value: str = "") -> str:
    """Deterministic, collision-free slug inside a scope (an event, usually)."""
    slug = util.slugify(base, "item")
    candidate, counter = slug, 1
    while True:
        if scope_column and scope_value:
            taken = db.one("SELECT 1 FROM %s WHERE %s = ? AND %s = ?" % (table, column, scope_column),
                           (candidate, scope_value))
        else:
            taken = db.one("SELECT 1 FROM %s WHERE %s = ?" % (table, column), (candidate,))
        if taken is None:
            return candidate
        counter += 1
        candidate = "%s-%d" % (slug, counter)


def seed_rubric(event_id: str, *, created_by: str | None = None,
                rubric_id: str = "rub_default") -> str:
    if db.one("SELECT id FROM rubrics WHERE id = ?", (rubric_id,)):
        return rubric_id
    db.insert("rubrics", {
        "id": rubric_id, "event_id": event_id, "name": "Default weighted rubric",
        "notes": ("Weights are relative: the portal rescales them to sum to 1, so "
                  "editing one weight cannot silently change the scale."),
        "is_active": 1, "created_by": created_by, "created_at": timeutil.now_iso()})
    for index, (key, label, description, weight, low, high) in enumerate(
            config.RUBRIC_DEFAULT, start=1):
        db.insert("rubric_criteria", {
            "id": "crit_%s_%s" % (rubric_id, key), "rubric_id": rubric_id, "key": key,
            "label": label, "description": description, "weight": weight,
            "min_score": low, "max_score": high, "seq": index * 10,
        })
    return rubric_id


def create_event(*, event_id: str, slug: str, name: str, tagline: str, description: str,
                 rules: str, seq: int, schedule: dict, created_by: str | None = None,
                 target_reviews: int = 3, min_team: int = 1, max_team: int = 4,
                 status: str = "published") -> str:
    """Insert an event and its six stages. Shared by the seed and the organizer UI."""
    now = timeutil.now_iso()
    row = {"id": event_id, "slug": util.slugify(slug or name, event_id), "name": name,
           "tagline": tagline, "description": description, "rules": rules, "seq": seq,
           "status": status, "min_team_size": min_team, "max_team_size": max_team,
           "reviews_required": target_reviews, "target_reviews": target_reviews,
           "created_by": created_by, "created_at": now, "updated_at": now}
    for key in ("registration_open", "registration_close", "team_formation_close",
                "submissions_open", "submissions_close", "judging_open", "judging_close",
                "results_publish_at"):
        row[key] = schedule.get(key)
    db.insert("events", row)
    stamp = timeutil.now_iso()
    for index, (key, stage_name, stage_desc, opens_field, closes_field) in enumerate(
            events_mod.STAGE_SEQUENCE, start=1):
        closes_at = schedule.get(closes_field)
        if closes_at and closes_at < stamp:
            state = "closed"
        elif (schedule.get(opens_field) or "0000") <= stamp:
            state = "open"
        else:
            state = "scheduled"
        db.insert("event_stages", {
            "id": "stg_%s_%s" % (event_id, key), "event_id": event_id, "seq": index * 10,
            "key": key, "name": stage_name, "description": stage_desc,
            "opens_at": schedule.get(opens_field), "closes_at": closes_at, "status": state})
    return event_id


def seed_prizes(event_id: str, prizes=None) -> None:
    entries = prizes if prizes is not None else [
        ("Grand prize", "Highest normalized score across all tracks.", "Chosen by the judges"),
        ("Judging engine prize", "Best documented scoring and normalization.", "Best method"),
        ("Track winners", "One winner and one runner-up per track.", "Eight tracks"),
        ("Best newcomer team", "First competition for every member.", "Nominated by organizers"),
    ]
    for index, (title, description, value) in enumerate(entries, start=1):
        db.insert("prizes", {"id": "prz_%s_%02d" % (event_id, index), "event_id": event_id,
                             "track_id": None, "rank": index, "title": title,
                             "description": description, "value": value})


# --- people -------------------------------------------------------------

def fixture_user_id(fixture_id: str) -> str:
    return "usr_%s" % fixture_id.strip()


def member_user_id(email: str) -> str:
    return "usr_%s" % util.slugify((email or "").split("@")[0], "member")


def hash_passwords(pairs, password: str, *, workers: int = 8) -> dict:
    """Hash one password per account, in parallel.

    scrypt and PBKDF2 release the GIL, so seeding ~120 accounts costs a couple of
    seconds instead of ten. Every account still gets its own random salt.
    """
    import concurrent.futures as cf
    results = {}

    def work(pair):
        key, _email = pair
        return key, security.hash_password(password)

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for key, digest in pool.map(work, pairs):
            results[key] = digest
    return results


def name_from_email(email: str) -> str:
    local = (email or "participant").split("@")[0]
    parts = [chunk for chunk in local.replace(".", " ").replace("_", " ").split() if chunk]
    if not parts:
        return "Participant"
    return " ".join(part.capitalize() for part in parts)


def seed_people(fixture: dict, password: str) -> dict:
    """Create every judge and every team member as a real, loggable-in user."""
    judges, members = {}, {}
    now = timeutil.now_iso()
    pending = []
    for index, judge in enumerate(fixture.get("judges") or [], start=1):
        fixture_id = (judge.get("id") or "jdg_%02d" % index).strip()
        email = (judge.get("email") or "%s@example.org" % fixture_id).strip()
        user_id = fixture_user_id(fixture_id)
        judges[fixture_id] = {
            "fixture_id": fixture_id, "user_id": user_id, "email": email,
            "name": (judge.get("name") or fixture_id).strip(),
            "tracks": [str(track) for track in (judge.get("tracks") or [])]}
        pending.append((user_id, email))
    for team in fixture.get("teams") or []:
        for email in team.get("members") or []:
            address = (email or "").strip()
            if address and address not in members:
                members[address] = {"user_id": member_user_id(address), "email": address}
    digests = hash_passwords(
        list(pending) + [(entry["user_id"], address) for address, entry in members.items()],
        password)
    for judge in judges.values():
        db.insert("users", {
            "id": judge["user_id"], "email": judge["email"], "name": judge["name"],
            "role": "judge", "password_hash": digests.get(judge["user_id"]),
            "created_at": now, "is_active": 1, "fixture_id": judge["fixture_id"],
            "org": "Invited judge",
            "notes": "track preference: %s" % ", ".join(judge["tracks"])})
    for address, entry in members.items():
        db.insert("users", {
            "id": entry["user_id"], "email": address, "name": name_from_email(address),
            "role": "participant", "password_hash": digests.get(entry["user_id"]),
            "created_at": now, "is_active": 1, "org": "Fixture roster"})
    return {"judges": judges, "members": members}


# --- teams --------------------------------------------------------------

def seed_teams(fixture: dict, event_id: str, member_index: dict) -> dict:
    teams = {}
    now = timeutil.now_iso()
    for index, team in enumerate(fixture.get("teams") or [], start=1):
        fixture_id = (team.get("id") or "tm_%02d" % index).strip()
        name = (team.get("name") or fixture_id).strip()
        members = [address.strip() for address in (team.get("members") or []) if address]
        owner = member_index.get(members[0], {}).get("user_id") if members else None
        if owner is None:
            log("skipping team %s: no members" % fixture_id)
            continue
        invite_code = "%s-%02d" % (util.slugify(name, "team").upper()[:12], index)
        db.insert("teams", {
            "id": fixture_id, "event_id": event_id, "name": name,
            "slug": unique_slug("teams", "slug", name, "event_id", event_id),
            "invite_code": invite_code, "created_by": owner, "status": "active",
            "seed_hint": "fixtures.json team %s" % fixture_id,
            "created_at": now, "updated_at": now})
        teams[fixture_id] = {"name": name, "members": members, "owner": owner,
                             "invite_code": invite_code}
        for position, address in enumerate(members):
            member = member_index.get(address)
            if not member:
                continue
            db.insert("team_members", {
                "id": "tmb_%s_%s" % (fixture_id, member["user_id"][4:]),
                "team_id": fixture_id, "user_id": member["user_id"],
                "role": "owner" if position == 0 else "member", "joined_at": now})
    return teams


# --- projects -----------------------------------------------------------

def seed_projects(fixture: dict, event_id: str, team_index: dict) -> dict:
    """Insert every fixture project, then link the duplicate pair.

    Duplicate detection is explicit rather than clever: same team, same
    normalized title and same repo means a resubmission. The later row stays
    canonical, the earlier row is marked superseded, and both stay queryable.
    """
    now = timeutil.now_iso()
    projects, seen = {}, {}
    for rank, project in enumerate(fixture.get("projects") or [], start=1):
        fixture_id = (project.get("id") or "prj_%02d" % rank).strip()
        team_fixture_id = (project.get("team") or "").strip()
        team = team_index.get(team_fixture_id)
        if team is None or not team.get("owner"):
            log("skipping project %s: no team or no owner" % fixture_id)
            continue
        title = (project.get("title") or "").strip() or "Untitled submission"
        submitted_at = (project.get("submitted_at") or "").strip() or None
        key = (team_fixture_id, title.lower(), (project.get("repo_url") or "").strip())
        duplicate_of = seen.get(key)
        seen.setdefault(key, fixture_id)
        db.insert("projects", {
            "id": fixture_id, "event_id": event_id, "team_id": team_fixture_id,
            "track_id": (project.get("track") or "").strip() or None,
            "title": title, "summary": (project.get("summary") or "").strip(),
            "description": "", "repo_url": (project.get("repo_url") or "").strip(),
            "demo_url": "", "video_url": "", "tags": "", "status": "submitted",
            "submission_state": "closed", "current_version": 1,
            "submitted_at": submitted_at, "fixture_id": fixture_id, "fixture_rank": rank,
            "duplicate_of": duplicate_of, "superseded_by": None,
            "created_by": team["owner"], "created_at": submitted_at or now,
            "updated_at": submitted_at or now})
        projects[fixture_id] = {"id": fixture_id, "team": team_fixture_id,
                                "track": (project.get("track") or "").strip(),
                                "title": title, "rank": rank,
                                "submitted_at": submitted_at, "superseded_by": None}
        if duplicate_of:
            projects[duplicate_of]["superseded_by"] = fixture_id
    for fixture_id, project in projects.items():
        if project["superseded_by"]:
            db.update("projects", {"superseded_by": project["superseded_by"]},
                      "id = ?", (fixture_id,))
        insert_fixture_version(fixture_id)
    return projects


def insert_fixture_version(project_id: str) -> None:
    """Every project gets an immutable version 1 recording what was submitted."""
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if row is None:
        return
    db.insert("project_versions", {
        "id": "ver_%s_1" % project_id, "project_id": project_id, "version_no": 1,
        "title": row["title"], "summary": row["summary"], "description": row["description"],
        "repo_url": row["repo_url"], "demo_url": row["demo_url"],
        "video_url": row["video_url"], "tags": row["tags"], "status": "submitted",
        "reason": "fixtures.json submission", "created_by": row["created_by"],
        "created_at": row["submitted_at"] or timeutil.now_iso(),
        "snapshot": db.json_text({"source": "fixtures.json", "fixture_id": project_id})})


# --- scores and the assignment plan -------------------------------------

def seed_reviews(fixture: dict, event_id: str, rubric_id: str, judge_index: dict,
                 project_index: dict, schedule: dict) -> dict:
    """Turn fixture scores into finalized reviews, one row per criterion."""
    criteria = [dict(row) for row in db.query(
        "SELECT * FROM rubric_criteria WHERE rubric_id = ? ORDER BY seq", (rubric_id,))]
    by_key = {item["key"]: item for item in criteria}
    judging_open = schedule.get("judging_open") or timeutil.now_iso()
    review_counts, inserted, skipped, empty_comments = {}, 0, 0, 0
    for index, score in enumerate(fixture.get("scores") or [], start=1):
        judge = judge_index.get(str(score.get("judge") or "").strip())
        project_fixture = str(score.get("project") or "").strip()
        project = project_index.get(project_fixture)
        if judge is None or project is None:
            skipped += 1
            continue
        values = {}
        for key, value in (score.get("criteria") or {}).items():
            try:
                values[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        if not values:
            skipped += 1
            continue
        comment = (score.get("comment") or "").strip()
        if not comment:
            empty_comments += 1
        raw = scoring.weighted_raw(values, criteria)
        offset = 2 + (index * 7) % 120
        started = _shift(judging_open, hours=offset)
        submitted = _shift(judging_open, hours=offset + 3)
        finalized = _shift(judging_open, hours=offset + 6)
        review_id = "rev_fx_%03d" % index
        db.insert("reviews", {
            "id": review_id, "project_id": project_fixture, "judge_user_id": judge["user_id"],
            "event_id": event_id, "rubric_id": rubric_id, "status": "finalized",
            "revision_no": 1, "comment": comment, "internal_note": "",
            "weighted_raw": raw, "normalized": None, "norm_method": "", "norm_flags": "",
            "origin": "fixtures", "started_at": started, "submitted_at": submitted,
            "finalized_at": finalized, "updated_at": finalized,
            "signature": security.sign("review|%s|%s|%s|%s" % (
                review_id, project_fixture, judge["user_id"], raw))})
        for key, number in values.items():
            criterion = by_key.get(key)
            db.insert("review_scores", {
                "id": "rsc_%s_%s" % (review_id, util.slugify(key, "criterion")),
                "review_id": review_id,
                "criterion_id": criterion["id"] if criterion else None,
                "criterion_key": key, "value": number,
                "weight": float(criterion["weight"]) if criterion else 0.0, "comment": ""})
        db.insert("review_revisions", {
            "id": "rre_%s_1" % review_id, "review_id": review_id, "revision_no": 1,
            "scores_json": db.json_text(values), "comment": comment, "weighted_raw": raw,
            "status": "finalized", "reason": "fixtures.json score",
            "actor_id": judge["user_id"], "created_at": finalized})
        review_counts.setdefault(project_fixture, []).append(judge["user_id"])
        inserted += 1
    return {"counts": review_counts, "inserted": inserted, "skipped": skipped,
            "empty_comments": empty_comments}

def plan_assignments(event_id: str, projects: dict, judge_index: dict, review_counts: dict,
                     schedule: dict) -> dict:
    """Every review implies an assignment; every missing review becomes pending work.

    This is how the fixtures' "two unfinished review batches" show up as real,
    assignable work in the organizer dashboard instead of as a silent gap.
    """
    target = config.TARGET_REVIEWS_PER_PROJECT
    due_at = schedule.get("judging_close")
    loads, accepted, pending = {}, 0, 0
    now = timeutil.now_iso()
    for project_fixture, judge_user_ids in review_counts.items():
        for judge_user_id in judge_user_ids:
            db.insert("assignments", {
                "id": "asg_%s_%s" % (project_fixture, _id_suffix(judge_user_id)),
                "event_id": event_id, "project_id": project_fixture,
                "judge_user_id": judge_user_id, "status": "accepted",
                "origin": "fixture_scores", "due_at": due_at, "assigned_by": None,
                "assigned_at": now, "updated_at": now})
            loads[judge_user_id] = loads.get(judge_user_id, 0) + 1
            accepted += 1
    for project_fixture, project in projects.items():
        if project.get("superseded_by"):
            continue
        have = set(review_counts.get(project_fixture, []))
        need = max(0, target - len(have))
        if not need:
            continue
        candidates = sorted(
            (judge for judge in judge_index.values() if judge["user_id"] not in have),
            key=lambda judge: (0 if project["track"] in judge["tracks"] else 1,
                               loads.get(judge["user_id"], 0), judge["user_id"]))
        for judge in candidates[:need]:
            db.insert("assignments", {
                "id": "asg_%s_%s" % (project_fixture, _id_suffix(judge["user_id"])),
                "event_id": event_id, "project_id": project_fixture,
                "judge_user_id": judge["user_id"], "status": "assigned",
                "origin": "fixture_plan", "due_at": due_at, "assigned_by": None,
                "assigned_at": now, "updated_at": now})
            loads[judge["user_id"]] = loads.get(judge["user_id"], 0) + 1
            pending += 1
    return {"accepted": accepted, "pending": pending}


def _id_suffix(user_id: str) -> str:
    return user_id[4:] if user_id.startswith("usr_") else user_id


def refresh_normalization(event_id: str) -> dict:
    """Store normalized values, flags and signatures for every review of an event."""
    event = events_mod.require_event(event_id)
    board = scoring.scoreboard(event)
    for review in board["reviews"]:
        db.update("reviews", {
            "normalized": review["normalized"],
            "norm_method": review["norm_method"],
            "norm_flags": ",".join(review["flags"]),
            "signature": security.sign("review|%s|%s|%s|%s" % (
                review["id"], review["project_id"], review["judge_user_id"], review["raw"]))},
            "id = ?", (review["id"],))
    return board
