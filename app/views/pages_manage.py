"""Organizer views for running many hackathons.

This module is the shelf and the per-event desk: the list of hackathons an
organizer may run, the form that creates a new one, and the management pages
for one event (overview, stages, teams, submissions, judges, assignments,
reviews, results, settings). `pages_organizer.py` keeps the older single-event
consoles that are now scoped to whichever event the caller manages.
"""

from __future__ import annotations

from . import ui
from .pages_events import results_scope_note
from .pages_public import results_leaderboard
from .ui import esc

MANAGE_TABS = (
    ("overview", "Overview", ""),
    ("stages", "Stages", "/stages"),
    ("teams", "Teams", "/teams"),
    ("submissions", "Submissions", "/submissions"),
    ("judges", "Judges", "/judges"),
    ("assignments", "Assignments", "/assignments"),
    ("reviews", "Reviews", "/reviews"),
    ("results", "Results", "/results"),
    ("audit", "Audit Log", "/audit"),
    ("settings", "Settings", "/settings"),
)


def manage_tabs(event: dict, current: str) -> str:
    parts = []
    for key, label, suffix in MANAGE_TABS:
        href = "/organizer/events/%s%s" % (esc(event["id"]), suffix)
        css = "tab tab--here" if key == current else "tab"
        attr = ' aria-current="page"' if key == current else ""
        parts.append('<a class="%s" href="%s"%s>%s</a>' % (css, href, attr, esc(label)))
    return '<nav class="tabs" aria-label="Manage this hackathon">%s</nav>' % "".join(parts)


def manage_home(*, actor: dict, events: list[dict], can_create: bool = True) -> str:
    """MY HACKATHONS: one card per event this organizer may operate."""
    admin_note = ("You are an administrator, so every hackathon on this install is listed."
                  if actor.get("role") == "admin" else "")
    projects_total = sum((item.get("metrics") or {}).get("projects", 0) for item in events)
    judges_total = sum((item.get("metrics") or {}).get("judges", 0) for item in events)
    reviews_total = sum((item.get("metrics") or {}).get("reviews_submitted", 0)
                        for item in events)
    if not events:
        body = ui.empty_state(
            "You do not manage a hackathon yet",
            "Create one, or ask an administrator to add you to an existing event.")
    else:
        cards = []
        for item in events:
            event, metrics = item["event"], item.get("metrics") or {}
            cards.append(ui.event_card(
                event, counts=metrics,
                action_label="Manage", action_href="/organizer/events/%s" % event["id"],
                status_label=event.get("status", "draft"),
                status_variant={"published": "open", "draft": "draft"}.get(
                    event.get("status"), "default"),
                links=[("View", "/events/%s" % event["slug"]),
                       ("Results", "/events/%s/results" % event["slug"])]))
        body = '<div class="grid grid--2">%s</div>' % "".join(cards)

    create_button = ('<a class="btn btn--danger" href="/organizer/events/new">'
                     'Create Hackathon</a>') if can_create else ""
    return f"""<div class="stack stack--lg">
  <header class="spread">
    <div>
      <div class="kicker kicker--red">Operations Command</div>
      <h1 class="headline--xl">My Hackathons</h1>
      <p class="lede">{esc(admin_note or "Each hackathon keeps its own teams, projects, "
                                        "judging and results.")}</p>
    </div>
    <div class="cluster">
      <a class="btn btn--ghost" href="/events">Public Archive</a>
      {create_button}
    </div>
  </header>

  <div class="grid grid--4">
    {ui.stat_card("Hackathons you run", len(events))}
    {ui.stat_card("Projects across them", projects_total)}
    {ui.stat_card("Judges assigned", judges_total)}
    {ui.stat_card("Reviews completed", reviews_total)}
  </div>

  {body}
</div>"""



def _field(label: str, name: str, value: str, *, kind: str = "text", errors: dict = None,
           hint: str = "", placeholder: str = "", required: bool = False,
           rows: int = 4) -> str:
    """One labelled control, with its own error line when validation refused it."""
    errors = errors or {}
    error = errors.get(name, "")
    css = "input input--bad" if error else "input"
    label_css = "required" if required else ""
    if kind == "textarea":
        control = ('<textarea id="%s" name="%s" rows="%d" class="textarea%s" '
                   'placeholder="%s">%s</textarea>'
                   % (esc(name), esc(name), rows, " input--bad" if error else "",
                      esc(placeholder), esc(value or "")))
    elif kind == "select":
        control = ('<select id="%s" name="%s" class="select%s">%s</select>'
                   % (esc(name), esc(name), " input--bad" if error else "", value))
    elif kind == "checkbox":
        checked = str(value).strip().lower() not in ("", "0", "false", "no", "off", "none")
        control = ('<label class="check"><input type="checkbox" name="%s" value="1"%s>'
                   '<span>%s</span></label>'
                   % (esc(name), " checked" if checked else "", esc(label)))
        label = ""
    else:
        control = ('<input type="%s" id="%s" name="%s" value="%s" class="%s" '
                   'placeholder="%s"%s>'
                   % (esc(kind), esc(name), esc(name), esc(value), css,
                      esc(placeholder), " required" if required else ""))
    head = ('<label for="%s" class="%s">%s</label>' % (esc(name), label_css, esc(label))
            if label else "")
    hint_markup = '<span class="hint">%s</span>' % esc(hint) if hint else ""
    error_markup = '<span class="field-error">%s</span>' % esc(error) if error else ""
    return ('<div class="field%s">%s%s%s%s</div>'
            % (" field--bad" if error else "", head, control, hint_markup, error_markup))



def event_form(*, values: dict, errors: dict, csrf_token: str, is_edit: bool = False,
               event: dict | None = None) -> str:
    """The multi-section create/settings form. Four sections, one submit."""
    from .. import eventadmin as admin

    status_options = "".join(
        '<option value="%s"%s>%s</option>'
        % (value, " selected" if values.get("status") == value else "", value.title())
        for value in admin.STATUS_CHOICES)
    tone_options = "".join(
        '<option value="%s"%s>%s</option>'
        % (tone, " selected" if values.get("cover_tone") == tone else "",
           ui.TONE_LABELS.get(tone, tone.title()))
        for tone in ("ink", "red", "blue", "green", "amber"))
    schedule_fields = "".join(
        _field(label, name, values.get(name, ""), kind="date", errors=errors, hint=help_text)
        for name, label, help_text in admin.SCHEDULE_FIELDS)

    heading = "Manage Hackathon" if is_edit else "Create Hackathon"
    action = ("/organizer/events/%s/settings" % esc(event["id"]) if is_edit
              else "/organizer/events/new")
    back = ('/organizer/events/%s' % esc(event["id"]) if is_edit else "/organizer")
    submit = "Save Changes" if is_edit else "Create Hackathon"

    return f"""<div class="stack stack--lg" style="max-width:980px;margin:0 auto">
  <header>
    <a href="{back}" class="tiny mono dim">&larr; Back</a>
    <div class="kicker kicker--red" style="margin-top:10px">Hackathon configuration</div>
    <h1 class="headline--xl">{heading}</h1>
    <p class="lede">Every field below is validated on the server before anything is
      written. The form is a convenience, not the rule.</p>
  </header>

  <form method="POST" action="{action}" class="stack stack--lg">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">

    <section class="panel">
      <div class="panel__head"><h3>1 &middot; Basic information</h3></div>
      <div class="panel__body stack">
        <div class="grid grid--2">
          {_field("Name", "name", values.get("name", ""), errors=errors, required=True)}
          {_field("Slug", "slug", values.get("slug", ""), errors=errors,
                  hint="Used in the URL: /events/your-slug")}
        </div>
        {_field("Tagline", "tagline", values.get("tagline", ""), errors=errors,
                hint="One line, shown on the event card.")}
        {_field("Description", "description", values.get("description", ""),
                kind="textarea", errors=errors,
                hint="What the hackathon is for. Required once you publish.")}
        {_field("Rules", "rules", values.get("rules", ""), kind="textarea", errors=errors,
                hint="The short version entrants actually read.")}
        <div class="grid grid--3">
          <div class="field">
            <label for="cover_tone">Cover tone</label>
            <select id="cover_tone" name="cover_tone" class="select">{tone_options}</select>
          </div>
          {_field("Cover glyph", "banner", values.get("banner", ""), errors=errors,
                  hint="Up to four characters.")}
          {_field("Location", "location", values.get("location", ""), errors=errors)}
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head"><h3>2 &middot; Schedule</h3></div>
      <div class="panel__body"><div class="grid grid--2">{schedule_fields}</div></div>
    </section>

    <section class="panel">
      <div class="panel__head"><h3>3 &middot; Competition</h3></div>
      <div class="panel__body stack">
        <div class="grid grid--3">
          {_field("Min team size", "min_team_size", values.get("min_team_size", "1"),
                  kind="number", errors=errors)}
          {_field("Max team size", "max_team_size", values.get("max_team_size", "4"),
                  kind="number", errors=errors)}
          {_field("Reviews per project", "target_reviews", values.get("target_reviews", "3"),
                  kind="number", errors=errors)}
        </div>
        {_field("Tracks", "tracks_text", values.get("tracks_text", ""), kind="textarea",
                rows=6, errors=errors, hint="One per line: Name | description")}
        {_field("Prizes", "prizes_text", values.get("prizes_text", ""), kind="textarea",
                rows=4, errors=errors,
                hint="One per line, in rank order: Title | value | description")}
        {_field("Rubric criteria", "rubric_text", values.get("rubric_text", ""),
                kind="textarea", rows=5, errors=errors,
                hint="One per line: key | label | weight | description")}
      </div>
    </section>

    <section class="panel">
      <div class="panel__head"><h3>4 &middot; Publishing</h3></div>
      <div class="panel__body stack">
        <div class="field">
          <label for="status">Event status</label>
          <select id="status" name="status" class="select">{status_options}</select>
          <span class="hint">A draft is invisible to the public archive.</span>
        </div>
        {_field("Show the gallery", "gallery_visible",
                values.get("gallery_visible", "0"), kind="checkbox", errors=errors)}
        {_field("Show results", "results_visible", values.get("results_visible", "0"),
                kind="checkbox", errors=errors)}
      </div>
    </section>

    <div class="spread">
      <a href="{back}" class="btn btn--ghost">Cancel</a>
      <button type="submit" class="btn">{submit}</button>
    </div>
  </form>
</div>"""


def event_overview(*, event: dict, metrics: dict, stages: list[dict],
                   timeline_rows: list[dict], organizers: list[dict],
                   judges: list[dict], csrf_token: str, actor_role: str = "",
                   gallery_visible: bool = True, results_visible: bool = True) -> str:
    """The management home for one hackathon: state, numbers, and what to do next."""
    stage_block = ui.stage_rail(stages, metrics.get("stage_key", "")) if stages else ""
    organizer_rows = "".join(
        '<li class="tiny"><strong>%s</strong> <span class="dim mono">%s</span> '
        '<span class="chip">%s</span></li>'
        % (esc(row["name"]), esc(row["email"]), esc(row["role"]))
        for row in organizers) or '<li class="tiny dim">Nobody is listed yet.</li>'
    judge_list = ", ".join(esc(row["name"]) for row in judges) or "no judges yet"

    publish_form = f"""<form method="POST" action="/organizer/events/{esc(event['id'])}/results">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <button type="submit" class="btn btn--danger"
          data-confirm="Publish these standings as a new immutable revision?">
    Publish Results</button>
</form>"""

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], ""), ("Overview", "")])}
  <header class="spread">
    <div>
      <div class="kicker kicker--red">Managing</div>
      <h1 class="headline--lg">{esc(event["name"])}</h1>
      <p class="lede">Status <strong>{esc(event["status"])}</strong> &middot;
        slug <span class="mono">/events/{esc(event["slug"])}</span></p>
    </div>
    <div class="cluster">
      <a class="btn btn--ghost" href="/events/{esc(event['slug'])}">Public Page</a>
      {publish_form}
    </div>
  </header>

  {manage_tabs(event, "overview")}

  <div class="grid grid--4">
    {ui.stat_card("Teams", metrics.get("teams", 0))}
    {ui.stat_card("Submissions", metrics.get("projects", 0))}
    {ui.stat_card("Judging progress",
                  "%s%%" % metrics.get("judging_percent", 0), red=metrics.get("judging_percent", 0) < 100)}
    {ui.stat_card("Results",
                  "rev %d" % metrics.get("results_revision", 0)
                  if metrics.get("results_published") else "unpublished",
                  red=not metrics.get("results_published"))}
  </div>

  <div class="grid grid--2">
    <div class="panel">
      <div class="panel__head"><h3>Stage</h3></div>
      <div class="panel__body">
        {stage_block or '<p class="tiny dim">No stages configured.</p>'}
        <div class="tiny mono dim" style="margin-top:10px">
          Current: <strong>{esc(metrics.get("stage") or "unset")}</strong>
          &middot; Judging {metrics.get("judging_done", 0)}/{metrics.get("judging_total", 0)}
          reviews &middot; Judges: {judge_list}
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="panel__head"><h3>Visibility</h3></div>
      <div class="panel__body stack tiny mono">
        <div>Gallery: <strong>{'public' if gallery_visible else 'hidden'}</strong></div>
        <div>Results: <strong>{'public' if results_visible else 'hidden'}</strong></div>
        <div>Reviews required per project: <strong>{metrics.get("target_reviews", 0)}</strong></div>
        <div>Organizers: <strong>{metrics.get("organizers", 0)}</strong></div>
        <div class="dim">Signed in as a {esc(actor_role or "organizer")}.</div>
      </div>
    </div>
  </div>

  <div class="grid grid--sidebar">
    <div class="panel">
      <div class="panel__head"><h3>Key dates</h3></div>
      <div class="panel__body">{ui.timeline(timeline_rows)}</div>
    </div>
    <div class="panel">
      <div class="panel__head"><h3>Who runs this</h3></div>
      <div class="panel__body">
        <ul class="plain-list">{organizer_rows}</ul>
        <a class="btn btn--sm btn--ghost" href="/organizer/events/{esc(event['id'])}/settings">
          Add an organizer</a>
      </div>
    </div>
  </div>
</div>"""


def event_stages_page(*, event: dict, stages: list[dict], csrf_token: str) -> str:
    """The stage table, plus the form that adds a stage this event invented."""
    rows = "".join(
        f"""<tr>
  <td class="num mono">{row['seq']}</td>
  <td><strong>{esc(row['name'])}</strong><div class="tiny dim mono">{esc(row['key'])}</div></td>
  <td class="tiny">{esc(row['description'])}</td>
  <td class="mono tiny">{esc((row['opens_at'] or '--')[:10])}</td>
  <td class="mono tiny">{esc((row['closes_at'] or '--')[:10])}</td>
  <td>{ui.badge(row['status'], 'open' if row['status'] == 'open' else 'draft')}</td>
  <td class="actions">
    <form method="POST" action="/organizer/events/{esc(event['id'])}/stages/remove">
      <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
      <input type="hidden" name="stage_id" value="{esc(row['id'])}">
      <button type="submit" class="btn btn--sm btn--ghost"
              data-confirm="Remove this stage?">Remove</button>
    </form>
  </td>
</tr>""" for row in stages) or \
        '<tr><td colspan="7" class="center dim">No stages yet.</td></tr>'

    add_form = f"""<form method="POST" action="/organizer/events/{esc(event['id'])}/stages"
      class="panel panel--sunk" style="padding:16px">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <div class="grid grid--3 grid--tight">
    <div class="field"><label for="name">Stage name</label>
      <input class="input" id="name" name="name" placeholder="Wildcard round" required></div>
    <div class="field"><label for="opens_at">Opens</label>
      <input class="input" type="date" id="opens_at" name="opens_at"></div>
    <div class="field"><label for="closes_at">Closes</label>
      <input class="input" type="date" id="closes_at" name="closes_at"></div>
  </div>
  <div class="field"><label for="description">Note</label>
    <input class="input" id="description" name="description"
           placeholder="What happens in this stage?"></div>
  <button type="submit" class="btn btn--sm">Add Stage</button>
</form>"""

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]), ("Stages", "")])}
  <header>
    <h1 class="headline--lg">Stages</h1>
    <p class="lede">The six stage windows that drive deadlines come from this event's
      schedule. Extra stages are kept per event.</p>
  </header>
  {manage_tabs(event, "stages")}
  <div class="table-wrap">
    <table class="table">
      <thead><tr><th class="num">#</th><th>Stage</th><th>Purpose</th><th>Opens</th>
        <th>Closes</th><th>State</th><th class="actions">Action</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  {add_form}
</div>"""


def event_roster_page(*, event: dict, teams: list[dict], members_by_team: dict) -> str:
    """Who is competing, per team, in this event only."""
    cards = []
    for team in teams:
        members = members_by_team.get(team["id"], [])
        member_rows = "".join(
            '<li class="tiny">%s <span class="dim mono">%s</span></li>'
            % (esc(row["name"]), esc(row["role"])) for row in members)
        project = team.get("project_title")
        cards.append("""<article class="card">
  <div class="card__meta"><span>%s</span><span class="mono">%d member(s)</span></div>
  <h3 class="card__title">%s</h3>
  <div class="card__body tiny dim">%s</div>
  <ul class="plain-list">%s</ul>
  <div class="card__foot tiny mono">%s</div>
</article>""" % (esc(team["status"]), len(members), esc(team["name"]),
                 esc(team.get("seed_hint") or ""), member_rows,
                 "Project: " + esc(project) if project else "No submission yet"))
    body = '<div class="grid grid--3">%s</div>' % "".join(cards) if cards \
        else ui.empty_state("No teams yet", "Nobody has registered for this hackathon.")

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]), ("Teams", "")])}
  <header>
    <h1 class="headline--lg">Teams</h1>
    <p class="lede">Rosters registered to {esc(event["name"])}. Teams from every other
      hackathon on this install are filtered out before this page renders.</p>
  </header>
  {manage_tabs(event, "teams")}
  {body}
</div>"""


def event_assignments_page(*, event: dict, projects: list[dict], judges: list[dict],
                           assignments: list[dict], csrf_token: str) -> str:
    """Hand work out, and see what is still unscored."""
    project_opts = "".join(
        '<option value="%s">%s</option>' % (esc(row["id"]), esc(row["title"]))
        for row in projects) or '<option value="">No submitted projects</option>'
    judge_opts = "".join(
        '<option value="%s">%s (%s)</option>'
        % (esc(row["id"]), esc(row["name"]), esc(row["email"]))
        for row in judges) or '<option value="">No judges on this portal</option>'
    rows = "".join(
        f"""<tr>
  <td><strong>{esc(row['project_title'])}</strong></td>
  <td class="tiny">{esc(row['judge_name'])}
    <div class="tiny dim">{esc(row['judge_email'])}</div></td>
  <td class="tiny mono">{esc(row['status'])}</td>
  <td class="tiny mono">{esc(row['origin'])}</td>
  <td>{ui.badge('Scored' if row.get('review_status') in ('submitted', 'finalized')
                else 'Pending', 'submitted' if row.get('review_status') else 'open')}</td>
  <td class="actions">
    <form method="POST" action="/organizer/events/{esc(event['id'])}/assignments/revoke">
      <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
      <input type="hidden" name="assignment_id" value="{esc(row['id'])}">
      <button type="submit" class="btn btn--sm btn--ghost"
              data-confirm="Revoke this assignment?">Revoke</button>
    </form>
  </td>
</tr>""" for row in assignments) or \
        '<tr><td colspan="6" class="center dim">Nothing assigned yet.</td></tr>'

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]),
                  ("Assignments", "")])}
  <header>
    <h1 class="headline--lg">Assignments</h1>
    <p class="lede">Both the submission and the judge are re-checked against
      {esc(event['name'])} before an assignment is written.</p>
  </header>
  {manage_tabs(event, "assignments")}
  <form method="POST" action="/organizer/events/{esc(event['id'])}/assignments"
        class="panel panel--sunk" style="padding:16px">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
    <div class="grid grid--3 grid--tight">
      <div class="field"><label for="project_id">Submission</label>
        <select class="select" id="project_id" name="project_id">{project_opts}</select></div>
      <div class="field"><label for="judge">Judge</label>
        <select class="select" id="judge" name="judge">{judge_opts}</select></div>
      <div class="field"><label>&nbsp;</label>
        <button type="submit" class="btn btn--block">Assign</button></div>
    </div>
  </form>
  <div class="table-wrap">
    <table class="table">
      <thead><tr><th>Submission</th><th>Judge</th><th>Status</th><th>Origin</th>
        <th>Review</th><th class="actions">Action</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""


def event_reviews_page(*, event: dict, reviews: list[dict]) -> str:
    """Every review recorded against this event, with its normalized score."""
    rows = "".join(
        f"""<tr>
  <td><strong>{esc(row['project_title'])}</strong></td>
  <td class="tiny">{esc(row['judge_name'])}</td>
  <td>{ui.badge(row['status'], 'submitted' if row['status'] in ('submitted', 'finalized')
                else 'draft')}</td>
  <td class="num">{ui.format_score(row['weighted_raw'])}</td>
  <td class="num">{ui.format_score(row['normalized'])}</td>
  <td class="tiny mono">{esc((row['submitted_at'] or row['started_at'] or '')[:16])}</td>
</tr>""" for row in reviews) or \
        '<tr><td colspan="6" class="center dim">No reviews recorded here.</td></tr>'
    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]), ("Reviews", "")])}
  <header>
    <h1 class="headline--lg">Reviews</h1>
    <p class="lede">Raw and normalized scores for {esc(event['name'])} only. Another
      hackathon's reviews are filtered out before this page renders.</p>
  </header>
  {manage_tabs(event, "reviews")}
  <div class="table-wrap">
    <table class="table">
      <thead><tr><th>Submission</th><th>Judge</th><th>Status</th><th class="num">Raw</th>
        <th class="num">Normalized</th><th>Submitted</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""


def event_settings_page(*, event: dict, values: dict, errors: dict, csrf_token: str,
                        organizers: list[dict]) -> str:
    """The settings form plus the organizer roster for this event."""
    people = "".join(
        f"""<li class="spread tiny">
  <span><strong>{esc(row['name'])}</strong>
    <span class="dim mono">{esc(row['email'])}</span></span>
  <form method="POST" action="/organizer/events/{esc(event['id'])}/organizers/remove">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
    <input type="hidden" name="user_id" value="{esc(row['user_id'])}">
    <button type="submit" class="btn btn--sm btn--ghost">Remove</button>
  </form>
</li>""" for row in organizers) or '<li class="tiny dim">No organizers listed.</li>'

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]), ("Settings", "")])}
  {manage_tabs(event, "settings")}

  <section class="panel">
    <div class="panel__head"><h3>Organizers for this hackathon</h3></div>
    <div class="panel__body stack">
      <ul class="plain-list">{people}</ul>
      <form method="POST" action="/organizer/events/{esc(event['id'])}/organizers"
            class="cluster">
        <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
        <input class="input" type="email" name="email" placeholder="colleague@example.org"
               required style="max-width:280px">
        <button type="submit" class="btn btn--sm">Add Organizer</button>
      </form>
      <p class="tiny dim">Adding an organizer gives them access to this event only.</p>
    </div>
  </section>

  {event_form(values=values, errors=errors, csrf_token=csrf_token, is_edit=True,
              event=event)}
</div>"""


def event_judges_page(*, event: dict, judges: list[dict], invitations: list[dict],
                      csrf_token: str) -> str:
    """This hackathon's judge roster, and the form that adds to it.

    Accepting an invitation creates the login if the address is new; here all
    the organizer sees is who is on the roster and how much of it is finished.
    """
    rows = "".join(
        f"""<tr>
  <td><strong>{esc(row['name'])}</strong></td>
  <td class="tiny mono">{esc(row['email'])}</td>
  <td class="num">{row.get('assignments', 0)}</td>
  <td class="num">{row.get('reviews', 0)}</td>
  <td>{ui.badge('Complete' if row.get('assignments') and
                row.get('reviews', 0) >= row.get('assignments', 0) else 'In progress',
                'submitted' if row.get('assignments') and
                row.get('reviews', 0) >= row.get('assignments', 0) else 'open')}</td>
</tr>""" for row in judges) or \
        '<tr><td colspan="5" class="center dim">No judges on this roster yet.</td></tr>'

    invitation_rows = "".join(
        '<li class="tiny"><strong>%s</strong> <span class="dim mono">%s</span> '
        '<span class="chip">%s</span></li>'
        % (esc(row["name"] or row["email"]), esc(row["email"]), esc(row["status"]))
        for row in invitations) or '<li class="tiny dim">No invitations recorded.</li>'

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]), ("Judges", "")])}
  <header>
    <h1 class="headline--lg">Judges</h1>
    <p class="lede">Everyone judging {esc(event["name"])} and nothing else. A judge who
      also works another hackathon is added to each roster separately.</p>
  </header>
  {manage_tabs(event, "judges")}

  <form method="POST" action="/organizer/events/{esc(event['id'])}/judges"
        class="panel panel--sunk" style="padding:16px">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
    <div class="grid grid--3 grid--tight">
      <div class="field"><label for="judge_email">Email</label>
        <input class="input" type="email" id="judge_email" name="email"
               placeholder="judge@example.org" required></div>
      <div class="field"><label for="judge_name">Name</label>
        <input class="input" id="judge_name" name="name" placeholder="Optional"></div>
      <div class="field"><label>&nbsp;</label>
        <button type="submit" class="btn btn--block">Add Judge</button></div>
    </div>
  </form>

  <div class="table-wrap">
    <table class="table">
      <thead><tr><th>Judge</th><th>Email</th><th class="num">Assigned</th>
        <th class="num">Reviewed</th><th>Progress</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <section class="panel">
    <div class="panel__head"><h3>Invitations for this hackathon</h3></div>
    <div class="panel__body"><ul class="plain-list">{invitation_rows}</ul></div>
  </section>
</div>"""


def event_results_page(*, event: dict, ranked: list[dict], is_published: bool,
                       publication: dict | None, csrf_token: str,
                       user_role: str | None = None) -> str:
    """The standings as this event's organizers see them, plus the publish switch."""
    publish_form = f"""<form method="POST"
      action="/organizer/events/{esc(event['id'])}/results" class="cluster">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <input class="input" name="note" placeholder="Release note (optional)"
         style="max-width:240px">
  <button type="submit" class="btn btn--danger"
          data-confirm="Publish these standings as a new immutable revision?">
    Publish Results</button>
</form>"""

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("My Hackathons", "/organizer"),
                  (event["name"], "/organizer/events/%s" % event["id"]), ("Results", "")])}
  <header class="spread">
    <div>
      <h1 class="headline--lg">Results</h1>
      <p class="lede">Standings for {esc(event["name"])}. Publishing freezes the current
        numbers as a new revision; nothing already published is edited in place.</p>
    </div>
    {publish_form}
  </header>
  {manage_tabs(event, "results")}
  {results_scope_note(event=event, publication=publication)}
  {results_leaderboard(event=event, ranked=ranked, is_published=is_published,
                       user_role=user_role)}
</div>"""

