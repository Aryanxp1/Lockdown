"""Participant views: Team workspace, submission editor, certificates."""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def participant_dashboard(*, user: dict, team: dict | None,
                          project: dict | None, event: dict,
                          certificates: list[dict], csrf_token: str,
                          event_ref: str = "",
                          other_events: list[dict] | None = None) -> str:
    """Render the participant project hub."""
    query = f"?event={esc(event_ref)}" if event_ref else ""

    events_markup = ""
    if other_events:
        links = []
        for other in other_events:
            label = other.get("name", "")
            if other.get("has_team"):
                label += " (your team)"
            elif other.get("accepting"):
                label += " (open for submissions)"
            links.append(
                f'<a class="chip" href="/participant?event={esc(other.get("slug"))}">'
                f'{esc(label)}</a>')
        events_markup = (f'<div class="cluster cluster--loose" style="margin-top:10px">'
                         f'<span class="tiny mono dim">OTHER EVENTS</span>'
                         f'{"".join(links)}</div>')

    if not team:
        return f"""<div class="panel" style="max-width:600px;margin:40px auto;padding:24px">
  <div class="kicker kicker--red">Team Registration</div>
  <h2>Create or Join a Team</h2>
  <p class="lede">You need a team before you can submit a project for {esc(event.get('name'))}.</p>
  <form method="POST" action="/participant/team/create{query}" class="form-stack" style="margin-top:20px">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
    <div class="field">
      <label for="name">Team Name</label>
      <input type="text" id="name" name="name" required class="input" placeholder="e.g. Cobalt Forge">
    </div>
    <button type="submit" class="btn">Create Team</button>
  </form>
  {events_markup}
</div>"""

    # Certificates section
    cert_markup = ""
    if certificates:
        cert_cards = []
        for c in certificates:
            cert_cards.append(f"""<div class="cert" style="padding:20px;margin:10px 0">
  <div class="cert__kicker">{esc(c.get("award_tier", "Certificate"))}</div>
  <div class="cert__recipient">{esc(c.get("recipient_name"))}</div>
  <div class="cert__project">{esc(project.get("title") if project else "Lockdown")}</div>
  <div class="cert__hash mono tiny">SHA256: {esc(c.get("sha256"))}</div>
</div>""")
        cert_markup = f"""<div>
  <div class="kicker">Recognition</div>
  <h3>Issued Certificates</h3>
  {"".join(cert_cards)}
</div>"""

    # Project details
    project_section = ""
    if project:
        status_badge = ui.badge(project.get("status", "draft"),
                                "submitted" if project.get("status") == "submitted" else "draft")
        project_section = f"""<div class="panel">
  <div class="panel__head">
    <div>
      <span class="mono tiny dim">PROJECT SUBMISSION</span>
      <h3>{esc(project.get("title"))}</h3>
    </div>
    {status_badge}
  </div>
  <div class="panel__body">
    <p class="lede">{esc(project.get("summary") or "")}</p>
    <div class="cluster" style="margin-bottom:14px">
      <span class="chip">Track: {esc(project.get("track") or "General")}</span>
      <span class="chip">Votes: {project.get("vote_count", 0)}</span>
    </div>
    <div class="cluster">
      <a href="/participant/project/edit{query}" class="btn btn--sm">Edit Submission</a>
      <a href="/gallery/{esc(project.get('id'))}" class="btn btn--sm btn--ghost">View Public Dossier &rarr;</a>
    </div>
  </div>
</div>"""
    else:
        project_section = ui.empty_state(
            "No project submitted yet",
            "Register your submission before the deadline.",
            action_label="Create Project Submission",
            action_href=f"/participant/project/new{query}")

    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker kicker--red">Participant Workspace</div>
    <h1 class="headline--lg">{esc(team.get("name"))}</h1>
    <p class="lede">Manage your team and track competition submissions.</p>
    {events_markup}
  </header>

  <div class="grid grid--sidebar">
    <div class="stack">
      {project_section}
      {cert_markup}
    </div>

    <aside class="panel">
      <div class="panel__head"><h3>Event Deadlines</h3></div>
      <div class="panel__body stack tiny mono">
        <div><span class="dim">Submissions Close</span><br><strong>{ui.format_iso(event.get("submissions_close"))}</strong></div>
        <div><span class="dim">Judging Closes</span><br><strong>{ui.format_iso(event.get("judging_close"))}</strong></div>
        <div><span class="dim">Results Published</span><br><strong>{ui.format_iso(event.get("results_publish_at"))}</strong></div>
      </div>
    </aside>
  </div>
</div>"""


def project_form(*, project: dict | None, team: dict, tracks: list[str],
                 csrf_token: str, action_url: str) -> str:
    """Render the project create / edit form."""
    title = project.get("title", "") if project else ""
    summary = project.get("summary", "") if project else ""
    desc = project.get("description", "") if project else ""
    repo_url = project.get("repo_url", "") if project else ""
    demo_url = project.get("demo_url", "") if project else ""
    cur_track = project.get("track", "") if project else ""

    track_opts = ['<option value="">General Track</option>']
    for t in tracks:
        sel = ' selected' if t == cur_track else ''
        track_opts.append(f'<option value="{esc(t)}"{sel}>{esc(t)}</option>')

    return f"""<div class="stack stack--lg" style="max-width:760px;margin:0 auto">
  <header>
    <a href="/participant" class="tiny mono dim">&larr; Back to Workspace</a>
    <h1 class="headline--lg" style="margin-top:10px">{"Edit Submission" if project else "Register Project"}</h1>
  </header>

  <form method="POST" action="{esc(action_url)}" class="panel panel--sunk" style="padding:20px">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">

    <div class="form-stack">
      <div class="field">
        <label for="title">Project Title</label>
        <input type="text" id="title" name="title" value="{esc(title)}" required class="input">
      </div>

      <div class="field">
        <label for="track">Competition Track</label>
        <select id="track" name="track" class="select">{"".join(track_opts)}</select>
      </div>

      <div class="field">
        <label for="summary">Elevator Pitch (One line summary)</label>
        <input type="text" id="summary" name="summary" value="{esc(summary)}" required class="input" placeholder="Short description of the solution...">
      </div>

      <div class="field">
        <label for="description">Detailed Description & Architecture</label>
        <textarea id="description" name="description" rows="8" class="textarea">{esc(desc)}</textarea>
      </div>

      <div class="grid grid--2">
        <div class="field">
          <label for="repo_url">Repository URL</label>
          <input type="url" id="repo_url" name="repo_url" value="{esc(repo_url)}" class="input" placeholder="https://github.com/...">
        </div>
        <div class="field">
          <label for="demo_url">Live Demo URL</label>
          <input type="url" id="demo_url" name="demo_url" value="{esc(demo_url)}" class="input" placeholder="https://...">
        </div>
      </div>
    </div>

    <div class="spread" style="margin-top:24px">
      <a href="/participant" class="btn btn--ghost">Cancel</a>
      <button type="submit" class="btn">Save & Publish Submission</button>
    </div>
  </form>
</div>"""

