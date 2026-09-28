"""Boot-time orchestration: practice event, community data, demo logins, banner.

`app/seed.py` transforms the fixtures. This module wraps that in everything the
portal needs to be usable the moment it starts:

  * an open "Autumn Practice Sprint" whose submission and review windows overlap,
    so a participant can draft and submit and a judge can score immediately;
  * community data (votes, comments, pairwise judgements) that is clearly ours
    rather than the fixtures';
  * staff accounts and the deterministic demo sessions whose tokens are printed
    on every boot and pasted into `.dogfood.toml`;
  * a single `seed()` entry point used by `python -m app` and by the CLI.
"""

from __future__ import annotations

from . import (audit, config, db, events as events_mod, results as results_mod,
               scoring, security, timeutil, util)
from .auth import create_user, issue_session
from . import seed as fixtures_seed

PRACTICE_EVENT_ID = "evt_practice"

_PRACTICE_TRACKS = (
    ("Tooling", "Developer workflow, CLIs, editors, build systems."),
    ("Data", "Anything that turns a mess into a table."),
    ("Accessibility", "Interfaces that more people can actually use."),
)


def first_members(fixture: dict, team_id: str, count: int) -> list[str]:
    for team in fixture.get("teams") or []:
        if (team.get("id") or "").strip() == team_id:
            return [str(email).strip() for email in (team.get("members") or [])][:count]
    return []


def seed_practice_event(fixture: dict, judge_index: dict, member_index: dict) -> dict:
    """An event that is open right now, so every role has something to do."""
    schedule = {
        "registration_open": timeutil.days_from_now(-45),
        "registration_close": timeutil.days_from_now(-38),
        "team_formation_close": timeutil.days_from_now(-33),
        "submissions_open": timeutil.days_from_now(-12),
        "submissions_close": timeutil.days_from_now(16),
        "judging_open": timeutil.days_from_now(-6),
        "judging_close": timeutil.days_from_now(20),
        "results_publish_at": timeutil.days_from_now(26),
    }
    fixtures_seed.create_event(
        event_id=PRACTICE_EVENT_ID, slug="autumn-practice-sprint",
        name="Autumn Practice Sprint",
        tagline="Submissions and reviews are open. Try the whole pipeline here.",
        description=(
            "A short rolling sprint used to demonstrate the live pipeline. The submission "
            "window and the review window deliberately overlap, because this event reviews "
            "in waves rather than in one batch after a deadline. Submissions opened twelve "
            "days ago, reviews six days ago, and results publish in about four weeks."),
        rules=("Same rules as any other event in this portal: one project per team, edits "
               "until the deadline, judges see only their own assignments and only their "
               "own scores."),
        seq=20, schedule=schedule, target_reviews=3,
        min_team=1, max_team=4)
    fixtures_seed.seed_prizes(PRACTICE_EVENT_ID, [
        ("Sprint winner", "Highest normalized score at the close of review.", "Bragging rights"),
        ("Reviewer's choice", "One pick from each judge, weighted equally.", "Chosen by judges"),
    ])
    for index, (name, description) in enumerate(_PRACTICE_TRACKS, start=1):
        db.insert("tracks", {
            "id": "trk_practice_%02d" % index, "event_id": PRACTICE_EVENT_ID,
            "slug": util.slugify(name, "track"), "name": name,
            "description": description, "seq": index * 10})

    roster = [
        ("team_loose", "Loose Threads", ["priya1@example.org", "member1_1@example.org"],
         "trk_practice_01"),
        ("team_carto", "Night Cartography",
         first_members(fixture, "tm_09", 2) or ["member9_1@example.org"], "trk_practice_02"),
        ("team_kiln", "Kiln Nine",
         first_members(fixture, "tm_15", 1) or ["member15_1@example.org"], "trk_practice_01"),
    ]
    now = timeutil.now_iso()
    teams = {}
    for index, (team_id, name, emails, track_id) in enumerate(roster, start=1):
        emails = [email for email in emails if email in member_index]
        if not emails:
            continue
        owner = member_index[emails[0]]["user_id"]
        invite_code = "%s-P%02d" % (util.slugify(name, "team").upper()[:12], index)
        db.insert("teams", {
            "id": team_id, "event_id": PRACTICE_EVENT_ID, "name": name,
            "slug": fixtures_seed.unique_slug("teams", "slug", name, "event_id",
                                              PRACTICE_EVENT_ID),
            "invite_code": invite_code, "created_by": owner, "status": "active",
            "seed_hint": "practice roster", "created_at": now, "updated_at": now})
        teams[team_id] = {"name": name, "owner": owner, "emails": emails,
                          "invite_code": invite_code, "track_id": track_id}
        for position, email in enumerate(emails):
            db.insert("team_members", {
                "id": "tmb_%s_%s" % (team_id, fixtures_seed._id_suffix(
                    member_index[email]["user_id"])),
                "team_id": team_id, "user_id": member_index[email]["user_id"],
                "role": "owner" if position == 0 else "member", "joined_at": now})
    return {"teams": teams, "schedule": schedule}


def seed_practice_projects(practice: dict, judge_index: dict, rubric_id: str) -> dict:
    """Three projects: one editable draft, two submitted and ready to review."""
    now = timeutil.now_iso()
    criteria = [dict(row) for row in db.query(
        "SELECT * FROM rubric_criteria WHERE rubric_id = ? ORDER BY seq", (rubric_id,))]
    specs = [
        ("prj_practice_field", "team_loose", "trk_practice_01", "Field Notes",
         "A pocket notebook for field researchers that syncs over a LAN.", "draft", ""),
        ("prj_practice_carto", "team_carto", "trk_practice_02", "Cartograph",
         "Turn a folder of CSVs into an explorable map without writing code.",
         "submitted", timeutil.days_from_now(-5)),
        ("prj_practice_kiln", "team_kiln", "trk_practice_01", "Kiln Timer",
         "Pottery firing schedules with a kiln-safe offline controller.",
         "submitted", timeutil.days_from_now(-3)),
    ]
    projects = {}
    for project_id, team_id, track_id, title, summary, status, submitted_at in specs:
        team = practice["teams"].get(team_id)
        if not team:
            continue
        repo = "https://example.org/%s" % project_id
        db.insert("projects", {
            "id": project_id, "event_id": PRACTICE_EVENT_ID, "team_id": team_id,
            "track_id": track_id, "title": title, "summary": summary, "description": "",
            "repo_url": repo, "demo_url": "", "video_url": "", "tags": "", "status": status,
            "submission_state": "open", "current_version": 1,
            "submitted_at": submitted_at or None, "fixture_id": None, "fixture_rank": None,
            "created_by": team["owner"], "created_at": submitted_at or now,
            "updated_at": submitted_at or now})
        db.insert("project_versions", {
            "id": "ver_%s_1" % project_id, "project_id": project_id, "version_no": 1,
            "title": title, "summary": summary, "description": "", "repo_url": repo,
            "demo_url": "", "video_url": "", "tags": "", "status": status,
            "reason": "draft saved" if status == "draft" else "final submission",
            "created_by": team["owner"], "created_at": submitted_at or now,
            "snapshot": db.json_text({"source": "practice seed"})})
        projects[project_id] = {"team": team_id, "title": title, "status": status}

    for project_id, judge_fixture, status in (
            ("prj_practice_carto", "jdg_01", "assigned"),
            ("prj_practice_carto", "jdg_02", "assigned"),
            ("prj_practice_kiln", "jdg_01", "assigned"),
            ("prj_practice_kiln", "jdg_03", "assigned")):
        judge = judge_index.get(judge_fixture)
        if not judge:
            continue
        db.insert("assignments", {
            "id": "asg_%s_%s" % (project_id, fixtures_seed._id_suffix(judge["user_id"])),
            "event_id": PRACTICE_EVENT_ID, "project_id": project_id,
            "judge_user_id": judge["user_id"], "status": status, "origin": "practice_plan",
            "due_at": practice["schedule"]["judging_close"], "assigned_by": None,
            "assigned_at": now, "updated_at": now})

    # One half-finished review, so the judge dashboard shows a draft to resume.
    judge_a = judge_index.get("jdg_01")
    if judge_a:
        partial = {"functionality": 4.0, "quality": 3.0}
        raw = scoring.weighted_raw(partial, criteria)
        note = "Solid core. Still checking what happens with malformed input."
        review_id = "rev_practice_draft"
        db.insert("reviews", {
            "id": review_id, "project_id": "prj_practice_carto",
            "judge_user_id": judge_a["user_id"], "event_id": PRACTICE_EVENT_ID,
            "rubric_id": rubric_id, "status": "draft", "revision_no": 1, "comment": note,
            "internal_note": "", "weighted_raw": raw, "normalized": None, "norm_method": "",
            "norm_flags": "", "origin": "portal", "started_at": timeutil.days_from_now(-2),
            "submitted_at": None, "finalized_at": None,
            "updated_at": timeutil.days_from_now(-1), "signature": ""})
        for key, value in partial.items():
            criterion = next((item for item in criteria if item["key"] == key), None)
            db.insert("review_scores", {
                "id": "rsc_%s_%s" % (review_id, key), "review_id": review_id,
                "criterion_id": criterion["id"] if criterion else None,
                "criterion_key": key, "value": value,
                "weight": float(criterion["weight"]) if criterion else 0.0, "comment": ""})
        db.insert("review_revisions", {
            "id": "rre_%s_1" % review_id, "review_id": review_id, "revision_no": 1,
            "scores_json": db.json_text(partial), "comment": note, "weighted_raw": raw,
            "status": "draft", "reason": "draft autosave",
            "actor_id": judge_a["user_id"], "created_at": timeutil.days_from_now(-1)})
    return projects


# --- a second, independent hackathon ------------------------------------
#
# Sample Hack 2026 is the fixture event: closed, judged, published. This second
# event is deliberately the opposite -- live, barely judged, unpublished -- so
# that "one Lockdown, many hackathons" is visible in the running portal rather
# than only in the schema. It shares no rows with the fixture event: different
# tracks, different rubric weights, different teams, its own judging state, and
# its own stage, because its dates are its own.

ZERO_DEP_EVENT_ID = "evt_zero_dep"
ZERO_DEP_SLUG = "zero-dependency-2026"

_ZERO_DEP_TRACKS = (
    ("Static Sites", "No framework, no build step, no network."),
    ("Command Line", "Tools that run where the terminal is."),
    ("Data and Viz", "Turn a mess into a table, then into a picture."),
    ("Offline Sync", "Works with the aeroplane mode switch on."),
    ("Accessibility", "Interfaces more people can actually use."),
)

_ZERO_DEP_RUBRIC = (
    ("correctness", "Does it actually work",
     "Runs, does what it claims, and survives being poked at.", 0.45, 1, 5),
    ("simplicity", "Simplicity",
     "Could someone read the whole thing in one sitting and change it?", 0.30, 1, 5),
    ("documentation", "Documentation",
     "Can a stranger run it with the network unplugged?", 0.25, 1, 5),
)

# team id, team name, track position, member emails
_ZERO_DEP_ROSTER = (
    ("team_zero_lantern", "Lantern Index", 1, ["zoe.tan@zero.test", "milo.reyes@zero.test"]),
    ("team_zero_abacus", "Abacus Field", 2, ["kenji.ito@zero.test"]),
    ("team_zero_ledger", "Quiet Ledger", 3,
     ["sara.lind@zero.test", "tobias.venn@zero.test", "amal.nasser@zero.test"]),
    ("team_zero_saltflat", "Salt Flat", 5, ["ines.mora@zero.test"]),
)

# project id, team id, track position, title, summary, status, age in days
_ZERO_DEP_PROJECTS = (
    ("prj_zero_lantern", "team_zero_lantern", 1, "Lantern Index",
     "A phone-first index of every offline file on a device, with no bundler.",
     "submitted", 8),
    ("prj_zero_abacus", "team_zero_abacus", 2, "Abacus Field",
     "One binary that turns a folder of receipts into a queryable ledger.",
     "submitted", 6),
    ("prj_zero_ledger", "team_zero_ledger", 3, "Quiet Ledger",
     "Household accounts rendered as one hand-drawn SVG chart, no chart library.",
     "submitted", 4),
    ("prj_zero_saltflat", "team_zero_saltflat", 5, "Salt Flat Sketchbook",
     "A keyboard-only sketching tool for people who cannot use a pointer.",
     "draft", 2),
)

# judge email, project id, criterion scores, review comment
_ZERO_DEP_REVIEWS = (
    ("noor.haddad@example.org", "prj_zero_lantern",
     {"correctness": 4, "simplicity": 5, "documentation": 4},
     "Loads on a two-year-old phone with the radio off. The file index is the part "
     "I would steal."),
    ("kofi.mensah@example.org", "prj_zero_ledger",
     {"correctness": 5, "simplicity": 4, "documentation": 3},
     "The hand-rolled SVG chart is genuinely good. The README assumes I already know "
     "where the data comes from."),
)

# judge email, project id -- handed out but not yet scored
_ZERO_DEP_PENDING = (
    ("noor.haddad@example.org", "prj_zero_abacus"),
    ("kofi.mensah@example.org", "prj_zero_abacus"),
)



def _zero_dep_scaffold() -> dict:
    """The event row, its own tracks, prizes and rubric weights."""
    schedule = {
        "registration_open": timeutil.days_from_now(-20),
        "registration_close": timeutil.days_from_now(14),
        "team_formation_close": timeutil.days_from_now(21),
        "submissions_open": timeutil.days_from_now(-10),
        "submissions_close": timeutil.days_from_now(30),
        "judging_open": timeutil.days_from_now(-2),
        "judging_close": timeutil.days_from_now(38),
        "results_publish_at": timeutil.days_from_now(45),
    }
    fixtures_seed.create_event(
        event_id=ZERO_DEP_EVENT_ID, slug=ZERO_DEP_SLUG, name="Zero Dependency 2026",
        tagline="Ship something that runs with the network unplugged.",
        description=(
            "Zero Dependency 2026 is the second hackathon hosted on this portal, and it is "
            "still running. Registration and submissions are open, judging has just started, "
            "and nothing has been published. It uses its own tracks, its own rubric weights "
            "and its own teams, so the two events on this install never share a number."),
        rules=("Same portal rules as every event: one project per team, edits until the "
               "deadline, judges score only their own assignments. The twist is the theme: "
               "nothing the judges have to install."),
        seq=30, schedule=schedule, target_reviews=2, min_team=1, max_team=3,
        banner="ZD", cover_tone="blue", location="Online")
    fixtures_seed.seed_prizes(ZERO_DEP_EVENT_ID, [
        ("Zero Dependency Award", "The judges' top normalized score.", "One winner"),
        ("Best Static Site", "Hand-written, no build step.", "Track winner"),
        ("Most Useful Offline Tool", "Best offline-first workflow.", "Track winner"),
    ])
    tracks = {}
    for index, (name, description) in enumerate(_ZERO_DEP_TRACKS, start=1):
        track_id = "trk_zero_%02d" % index
        tracks[index] = track_id
        db.insert("tracks", {
            "id": track_id, "event_id": ZERO_DEP_EVENT_ID,
            "slug": util.slugify(name, "track-%d" % index), "name": name,
            "description": description, "seq": index * 10})
    rubric_id = fixtures_seed.seed_rubric(
        ZERO_DEP_EVENT_ID, rubric_id="rub_zero_dep", criteria=_ZERO_DEP_RUBRIC)
    criteria = {row["key"]: dict(row) for row in db.query(
        "SELECT * FROM rubric_criteria WHERE rubric_id = ?", (rubric_id,))}
    return {"schedule": schedule, "tracks": tracks, "rubric_id": rubric_id,
            "criteria": criteria}


def _zero_dep_people(roster) -> dict:
    """Create (or find) the participants this demo event needs."""
    from .auth import create_user

    people = {}
    for _team_id, _name, _track, emails in roster:
        for email in emails:
            user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
            if user is None:
                create_user(email, fixtures_seed.name_from_email(email),
                            "participant", config.DEMO_PASSWORD)
                user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
            people[email] = user
    return people


def _zero_dep_teams(roster, people, tracks) -> dict:
    now = timeutil.now_iso()
    teams = {}
    for index, (team_id, name, track_pos, emails) in enumerate(roster, start=1):
        owner = people[emails[0]]["id"]
        invite = "ZERO-%s-%02d" % (util.slugify(name, "team").upper()[:10], index)
        db.insert("teams", {
            "id": team_id, "event_id": ZERO_DEP_EVENT_ID, "name": name,
            "slug": fixtures_seed.unique_slug("teams", "slug", name, "event_id",
                                              ZERO_DEP_EVENT_ID),
            "invite_code": invite, "created_by": owner, "status": "active",
            "seed_hint": "zero dependency demo roster",
            "created_at": now, "updated_at": now})
        teams[team_id] = {"name": name, "owner": owner, "emails": emails,
                          "invite_code": invite, "track_id": tracks[track_pos]}
        for position, email in enumerate(emails):
            db.insert("team_members", {
                "id": "tmb_%s_%02d" % (team_id, position + 1), "team_id": team_id,
                "user_id": people[email]["id"],
                "role": "owner" if position == 0 else "member", "joined_at": now})
    return teams


def _zero_dep_projects(specs, teams, tracks) -> dict:
    now = timeutil.now_iso()
    projects = {}
    for project_id, team_id, track_pos, title, summary, status, age in specs:
        team = teams[team_id]
        submitted_at = timeutil.days_from_now(-age) if status == "submitted" else None
        repo = "https://example.org/zero/%s" % project_id
        db.insert("projects", {
            "id": project_id, "event_id": ZERO_DEP_EVENT_ID, "team_id": team_id,
            "track_id": tracks[track_pos], "title": title, "summary": summary,
            "description": ("%s Built for Zero Dependency 2026: nothing to install and "
                            "nothing that phones home." % summary),
            "repo_url": repo, "demo_url": "", "video_url": "", "tags": "",
            "status": status, "submission_state": "open", "current_version": 1,
            "submitted_at": submitted_at, "created_by": team["owner"],
            "created_at": submitted_at or now, "updated_at": submitted_at or now})
        db.insert("project_versions", {
            "id": "prv_%s_1" % project_id, "project_id": project_id, "version_no": 1,
            "title": title, "summary": summary, "description": "", "repo_url": repo,
            "demo_url": "", "video_url": "", "tags": "", "status": status,
            "reason": "seed" if status == "submitted" else "draft",
            "created_by": team["owner"], "created_at": submitted_at or now,
            "snapshot": db.json_text({"title": title, "summary": summary})})
        projects[project_id] = {"title": title, "team_id": team_id, "team": team["name"]}
    return projects


def _zero_dep_judging(criteria, rubric_id, judge_index, projects, schedule) -> dict:
    """Two scored reviews and two assignments still waiting. Its own numbers."""
    def judge_for(email: str):
        for judge in judge_index.values():
            if judge["email"].lower() == email.lower():
                return judge
        return None

    now = timeutil.now_iso()
    reviews = 0
    for level, (email, project_id, scores, comment) in enumerate(_ZERO_DEP_REVIEWS, start=1):
        judge = judge_for(email)
        if judge is None or project_id not in projects:
            continue
        review_id = "rev_zero_%02d" % level
        raw = scoring.weighted_raw(scores, list(criteria.values()))
        submitted_at = timeutil.days_from_now(-1)
        db.insert("reviews", {
            "id": review_id, "project_id": project_id, "judge_user_id": judge["user_id"],
            "event_id": ZERO_DEP_EVENT_ID, "rubric_id": rubric_id, "status": "submitted",
            "revision_no": 1, "comment": comment, "internal_note": "",
            "weighted_raw": raw, "origin": "portal", "started_at": timeutil.days_from_now(-2),
            "submitted_at": submitted_at, "updated_at": submitted_at})
        for key, value in scores.items():
            criterion = criteria.get(key)
            db.insert("review_scores", {
                "id": "rsc_%s_%s" % (review_id, key), "review_id": review_id,
                "criterion_id": criterion["id"] if criterion else None,
                "criterion_key": key, "value": value,
                "weight": float(criterion["weight"]) if criterion else 0.0, "comment": ""})
        db.insert("review_revisions", {
            "id": "rre_%s_1" % review_id, "review_id": review_id, "revision_no": 1,
            "scores_json": db.json_text([{"key": key, "value": value}
                                         for key, value in scores.items()]),
            "comment": comment, "weighted_raw": raw, "status": "submitted",
            "reason": "zero dependency demo", "actor_id": judge["user_id"],
            "created_at": submitted_at})
        db.insert("assignments", {
            "id": "asg_%s_%s" % (project_id, fixtures_seed._id_suffix(judge["user_id"])),
            "event_id": ZERO_DEP_EVENT_ID, "project_id": project_id,
            "judge_user_id": judge["user_id"], "status": "accepted",
            "origin": "zero_dep_demo", "due_at": schedule["judging_close"],
            "assigned_by": None, "assigned_at": now, "updated_at": now})
        reviews += 1

    pending = 0
    for email, project_id in _ZERO_DEP_PENDING:
        judge = judge_for(email)
        if judge is None or project_id not in projects:
            continue
        db.insert("assignments", {
            "id": "asg_%s_%s" % (project_id, fixtures_seed._id_suffix(judge["user_id"])),
            "event_id": ZERO_DEP_EVENT_ID, "project_id": project_id,
            "judge_user_id": judge["user_id"], "status": "assigned",
            "origin": "zero_dep_demo", "due_at": schedule["judging_close"],
            "assigned_by": None, "assigned_at": now, "updated_at": now})
        pending += 1
    return {"reviews": reviews, "pending": pending}


def _zero_dep_community(people, projects, teams) -> dict:
    """Votes and comments that belong to this event and no other."""
    voters = sorted({entry["id"] for entry in people.values()})
    roster_of = {team_id: roster_ids(team_id) for team_id in teams}
    votes, comments, shadow = 0, 0, 0
    for index, project_id in enumerate(sorted(projects)):
        roster = roster_of.get(projects[project_id]["team_id"], set())
        for offset in range(2 - index % 2):
            voter = voters[(index * 3 + offset) % len(voters)]
            if voter in roster:
                continue
            db.insert("votes", {
                "id": util.new_id("vot"), "event_id": ZERO_DEP_EVENT_ID,
                "project_id": project_id, "user_id": voter, "weight": 1,
                "created_at": timeutil.days_from_now(-float(index + offset + 1)),
                "ip_hash": security.ip_hash("seeded")})
            votes += 1
    for index, project_id in enumerate(sorted(projects)[:3]):
        author = voters[(index * 5) % len(voters)]
        db.insert("comments", {
            "id": util.new_id("cmt"), "project_id": project_id, "user_id": author,
            "parent_id": None,
            "body": ("Ran this with the wifi off and it still worked, which is the whole "
                     "point of the theme."),
            "is_hidden": 0, "created_at": timeutil.days_from_now(-1.5),
            "updated_at": timeutil.days_from_now(-1.5)})
        comments += 1
    return {"votes": votes, "comments": comments}


def seed_zero_dependency_event(judge_index: dict) -> dict:
    """Create the demo second hackathon and its own little world.

    Called once, from `seed()`, after the fixture event exists: the demo judges
    this event uses are the fixture judges, which is exactly the point -- one
    judge account can work two hackathons and still see only what each event
    handed them.
    """
    scaffold = _zero_dep_scaffold()
    people = _zero_dep_people(_ZERO_DEP_ROSTER)
    teams = _zero_dep_teams(_ZERO_DEP_ROSTER, people, scaffold["tracks"])
    projects = _zero_dep_projects(_ZERO_DEP_PROJECTS, teams, scaffold["tracks"])
    judging = _zero_dep_judging(scaffold["criteria"], scaffold["rubric_id"],
                                judge_index, projects, scaffold["schedule"])
    community = _zero_dep_community(people, projects, teams)
    board = fixtures_seed.refresh_normalization(ZERO_DEP_EVENT_ID)
    return {"event_id": ZERO_DEP_EVENT_ID, "teams": len(teams), "projects": len(projects),
            "members": len(people), "reviews": judging["reviews"],
            "pending_assignments": judging["pending"], "votes": community["votes"],
            "comments": community["comments"], "ranked_preview": len(board["ranked"])}





# --- community data that is ours, not the fixtures' ---------------------

COMMENT_LIBRARY = (
    "The offline story is the interesting part. Does the README explain how to run it "
    "with the network unplugged?",
    "Good call keeping the earlier version. I could follow what changed between the two "
    "submissions, which is more than most portals manage.",
    "Tried the demo on a phone with no setup. That is rarer than it should be.",
    "The judging notes say reviews are normalized. Worth writing down what happens when "
    "a judge scores everything the same, because that case really happens.",
    "Good scope. It does one thing and does not pretend to do more.",
    "I would like a screenshot in the repository. The description is clear but I still "
    "had to clone it to see anything.",
    "Two of us used this in the same room and it stayed readable, which says more about "
    "the interface than the code.",
)


def seed_community(event_id: str, member_index: dict, judge_index: dict, stamps: dict) -> dict:
    """Votes, comments and pairwise comparisons for the fixture event."""
    member_ids = sorted({entry["user_id"] for entry in member_index.values()})
    canonical = db.query("""SELECT * FROM projects WHERE event_id = ? AND status = 'submitted'
                             AND superseded_by IS NULL ORDER BY fixture_rank""", (event_id,))
    window = stamps.get("results_publish_at") or timeutil.now_iso()
    votes, comments = 0, 0
    for index, project in enumerate(canonical):
        roster = roster_ids(project["team_id"])
        stamp = fixtures_seed._shift(window, hours=-(2 + index))
        for k in range(2 + index % 3):
            voter = member_ids[(index * 5 + k * 7) % len(member_ids)]
            if voter in roster or db.one(
                    "SELECT id FROM votes WHERE project_id = ? AND user_id = ?",
                    (project["id"], voter)):
                continue
            db.insert("votes", {
                "id": util.new_id("vot"), "event_id": event_id, "project_id": project["id"],
                "user_id": voter, "weight": 1, "created_at": stamp,
                "ip_hash": security.ip_hash("seeded")})
            votes += 1
    for index, project in enumerate(canonical[:10]):
        roster = roster_ids(project["team_id"])
        for k in range(1 + index % 2):
            author = member_ids[(index * 11 + k * 13) % len(member_ids)]
            if author in roster:
                continue
            stamp = fixtures_seed._shift(window, hours=-(6 + index + k))
            db.insert("comments", {
                "id": util.new_id("cmt"), "project_id": project["id"], "user_id": author,
                "parent_id": None,
                "body": COMMENT_LIBRARY[(index + k) % len(COMMENT_LIBRARY)],
                "is_hidden": 0, "created_at": stamp, "updated_at": stamp})
            comments += 1

    board = scoring.scoreboard(events_mod.require_event(event_id))
    top = [row for row in board["ranked"] if row["raw_mean"] is not None][:8]
    judge_users = sorted(judge_index.values(), key=lambda item: item["user_id"])
    comparisons = 0
    for i, left in enumerate(top):
        for j, right in enumerate(top):
            if i >= j or (i + j) % 4:
                continue
            winner = left if left["raw_mean"] >= right["raw_mean"] else right
            judge = judge_users[(i * 3 + j) % len(judge_users)]
            db.insert("pairwise_comparisons", {
                "id": util.new_id("pw"), "event_id": event_id,
                "judge_user_id": judge["user_id"], "project_a": left["project_id"],
                "project_b": right["project_id"], "winner": winner["project_id"],
                "reason": "seeded pairwise pass",
                "created_at": fixtures_seed._shift(window, hours=-5)})
            comparisons += 1
    return {"votes": votes, "comments": comments, "comparisons": comparisons}


def roster_ids(team_id: str) -> set:
    return {row["user_id"] for row in db.query(
        "SELECT user_id FROM team_members WHERE team_id = ?", (team_id,))}


def seed_webhook(event_id: str, actor_id: str | None = None) -> None:
    """One inactive example endpoint. Nothing is called unless a human turns it on."""
    db.insert("webhooks", {
        "id": "whk_example", "event_id": event_id, "url": "http://localhost:9000/lockdown",
        "secret": security.random_token(16),
        "topics": '["submission.finalized","review.submitted"]', "is_active": 0,
        "created_by": actor_id, "created_at": timeutil.now_iso()})


# --- demo accounts and boot banner --------------------------------------

def seed_demo_accounts(*, password: str | None = None) -> dict:
    """Create the staff accounts and the deterministic demo sessions.

    The tokens are fixed so `.dogfood.toml` can be written once and keep working.
    They are demo credentials for synthetic data, they are printed on every boot,
    and they do not expire, because an acceptance report may be regenerated
    months from now.
    """
    accounts = {}
    for key, email, name, role, token in (config.DEMO_ACCOUNTS + config.EXTRA_DEMO_ACCOUNTS):
        user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
        if user is None:
            create_user(email, name, role, password or config.DEMO_PASSWORD,
                        id="usr_demo_%s" % key)
            user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
        if not user["password_hash"]:
            db.update("users", {"password_hash": security.hash_password(
                password or config.DEMO_PASSWORD)}, "id = ?", (user["id"],))
        if not db.one("SELECT token_hash FROM sessions WHERE token_hash = ?",
                      (security.token_hash(token),)):
            issue_session(user, label="demo:%s" % key, token=token, is_demo=True,
                          expires_at=config.DEMO_SESSION_EXPIRY)
        accounts[key] = {"id": user["id"], "user_id": user["id"], "email": user["email"],
                         "name": user["name"], "role": user["role"], "token": token}
    return accounts


def demo_login_table(accounts: dict) -> list[dict]:
    ordered = []
    for key, *_rest in config.DEMO_ACCOUNTS:
        account = accounts.get(key)
        if account:
            ordered.append({"key": key, **account})
    for key, *_rest in config.EXTRA_DEMO_ACCOUNTS:
        account = accounts.get(key)
        if account:
            ordered.append({"key": key, **account})
    return ordered


def banner(accounts: dict, summary: dict, *, base_url: str) -> str:
    lines = ["", "seeded. test logins:"]
    for account in demo_login_table(accounts):
        lines.append("  %-14s Cookie: session=%s" % (account["key"], account["token"]))
    lines.append("")
    lines.append("  fixture accounts: %s" % config.FIXTURE_PASSWORD)
    lines.append("  staff accounts:   %s" % config.DEMO_PASSWORD)
    lines.append("  portal:           %s" % base_url)
    lines.append("  loaded: %(projects)s projects, %(teams)s teams, %(judges)s judges, "
                 "%(reviews)s reviews, %(assignments)s assignments" % summary)
    lines.append("")
    return "\n".join(lines)

# --- the whole boot -----------------------------------------------------

WIPE_TABLES = (
    "webhook_deliveries", "webhooks", "certificates", "result_publications", "advancements",
    "pairwise_comparisons", "comments", "vote_ballots", "votes", "review_revisions",
    "review_scores", "reviews", "assignments", "judge_invitations", "project_versions",
    "projects", "team_members", "teams", "prizes", "tracks", "rubric_criteria", "rubrics",
    "event_stages", "event_organizers", "events", "sessions", "users", "rate_limits",
    "audit_log",
)


def wipe() -> None:
    """Delete every competition row. Settings (and the portal secret) survive."""
    with db.tx():
        for table in WIPE_TABLES:
            db.execute("DELETE FROM %s" % table)
    fixtures_seed.log("wiped %d tables" % len(WIPE_TABLES))


def seed_event_organizers(*, events=("evt_01", "evt_practice", ZERO_DEP_EVENT_ID)) -> int:
    """Give the demo organizer and the admin the events they are meant to run.

    The isolation tests depend on this being exactly these events: a third
    organizer account (`organizer_b`) is deliberately left out, so it has a
    valid organizer login and no hackathon to manage.
    """
    added = 0
    for key in ("organizer", "admin"):
        email = next((row[1] for row in config.DEMO_ACCOUNTS if row[0] == key), "")
        user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
        if user is None:
            continue
        for event_id in events:
            if not db.exists("SELECT id FROM events WHERE id = ?", (event_id,)):
                continue
            if events_mod.add_organizer(event_id, user["id"], role="owner"):
                added += 1
    return added


def seed(*, force: bool = False, quiet: bool = False, fixture_path=None,
         base_url: str | None = None) -> dict:
    """Load the fixtures and the boot state. Returns a summary dict."""
    if fixtures_seed.is_seeded() and not force:
        return {"seeded": False, "reason": "already seeded"}
    if force:
        wipe()
    fixture = fixtures_seed.load_fixtures(fixture_path)
    started = timeutil.now()
    event_id, name, schedule = fixtures_seed.fixture_schedule(fixture)
    with db.tx():
        fixtures_seed.create_event(
            event_id=event_id, slug=name, name=name,
            tagline="Seeded from the official DOGFOOD fixtures: closed, judged, published.",
            description=fixtures_seed.EVENT_DESCRIPTION, rules=fixtures_seed.EVENT_RULES,
            seq=10, schedule=schedule, target_reviews=config.TARGET_REVIEWS_PER_PROJECT)
        fixtures_seed.seed_prizes(event_id)
        for index, track in enumerate(fixture.get("tracks") or [], start=1):
            db.insert("tracks", {
                "id": (track.get("id") or "trk_%02d" % index).strip(), "event_id": event_id,
                "slug": util.slugify(track.get("name", ""), "track-%d" % index),
                "name": (track.get("name") or "Track %d" % index).strip(),
                "description": (track.get("description") or "").strip(),
                "seq": index * 10})
        rubric_id = fixtures_seed.seed_rubric(event_id)
        people = fixtures_seed.seed_people(fixture, config.FIXTURE_PASSWORD)
        teams = fixtures_seed.seed_teams(fixture, event_id, people["members"])
        projects = fixtures_seed.seed_projects(fixture, event_id, teams)
        scores = fixtures_seed.seed_reviews(fixture, event_id, rubric_id, people["judges"],
                                            projects, schedule)
        plan = fixtures_seed.plan_assignments(event_id, projects, people["judges"],
                                             scores["counts"], schedule)
        practice = seed_practice_event(fixture, people["judges"], people["members"])
        # The practice event gets its own rubric, with the same weights and the
        # same five-point scale, so a judge can finish an evaluation there
        # without borrowing another event's rubric row.
        practice_rubric = fixtures_seed.seed_rubric(PRACTICE_EVENT_ID,
                                                    rubric_id="rub_practice")
        seed_practice_projects(practice, people["judges"], practice_rubric)
        # The second hackathon. Deliberately built from its own data rather than
        # copied from the fixtures: different tracks, different weights, its own
        # rosters, and judging that has only just started.
        zero_dep = seed_zero_dependency_event(people["judges"])
        accounts = seed_demo_accounts()
        organizer_grants = seed_event_organizers()
        seed_webhook(event_id, accounts["organizer"]["user_id"])

        event = events_mod.require_event(event_id)
        board = fixtures_seed.refresh_normalization(event_id)
        decisions = []
        for row in board["ranked"]:
            decisions.append((row["project_id"],
                              "advanced" if row["published_rank"] <= 8 else "eliminated",
                              row["published_rank"], row["normalized_mean"]))
        advancements = results_mod.advance(
            event, decisions, to_stage="showcase",
            note="Derived from the fixture scoring at seed time.")
        publication = results_mod.publish(
            event, board=board, note="Seeded publication of the fixture results.")
        certificates = results_mod.issue_certificates(
            event, actor=accounts["organizer"])
        community = seed_community(event_id, people["members"], people["judges"], schedule)
        summary = {
            "projects": db.scalar("SELECT COUNT(*) FROM projects WHERE event_id = ?",
                                  (event_id,), 0),
            "teams": len(teams), "judges": len(people["judges"]),
            "members": len(people["members"]), "reviews": scores["inserted"],
            "skipped_scores": scores["skipped"], "empty_comments": scores["empty_comments"],
            "assignments": plan["accepted"] + plan["pending"],
            "pending_assignments": plan["pending"], "votes": community["votes"],
            "comments": community["comments"], "comparisons": community["comparisons"],
            "certificates": len(certificates), "advancements": len(advancements),
            "publication_revision": publication["revision"],
            "practice_projects": db.scalar("SELECT COUNT(*) FROM projects WHERE event_id = ?",
                                           (PRACTICE_EVENT_ID,), 0),
            "events": db.scalar("SELECT COUNT(*) FROM events", (), 0),
            "event_organizer_grants": organizer_grants,
            "second_event": zero_dep,
            "event": event_id}
        audit.record(action="seed.fixtures_loaded", entity_type="event", entity_id=event_id,
                     summary="Loaded %d fixture projects and %d fixture scores" % (
                         summary["projects"], summary["reviews"]),
                     actor=accounts["organizer"], after=summary)
    summary["seconds"] = round((timeutil.now() - started).total_seconds(), 1)
    summary["accounts"] = accounts
    if not quiet:
        print(banner(accounts, summary, base_url=base_url or config.BASE_URL), flush=True)
    return {"seeded": True, "summary": summary, "fixture_event": event_id}
