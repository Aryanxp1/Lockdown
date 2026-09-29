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
    """Render the participant project hub with modern developer workspace aesthetic."""
    query = f"?event={esc(event_ref)}" if event_ref else ""

    events_markup = ""
    if other_events:
        links = []
        for other in other_events:
            label = other.get("name", "")
            if other.get("has_team"):
                label += " (Your Team)"
            elif other.get("accepting"):
                label += " (Open)"
            links.append(
                f'<a class="chip" href="/participant?event={esc(other.get("slug"))}">'
                f'{esc(label)}</a>')
        events_markup = (f'<div class="cluster cluster--loose u-mt-14">'
                         f'<span class="tiny mono dim">COMPETITIONS:</span>'
                         f'{"".join(links)}</div>')

    if not team:
        return f"""<div class="panel u-center-620 u-p-28">
  <div class="kicker">TEAM ONBOARDING</div>
  <h2>Register Your Team</h2>
  <p class="lede">You must form or register a team before submitting a candidate project for <strong class="u-text-accent">{esc(event.get('name'))}</strong>.</p>
  <form method="POST" action="/participant/team/create{query}" class="form-stack u-mt-24">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
    <div class="field">
      <label for="name">Team Name</label>
      <input type="text" id="name" name="name" required class="input" placeholder="e.g. Cobalt Labs, Quantum Core">
      <span class="hint">Your team name will be displayed publicly on the project dossier and leaderboard.</span>
    </div>
    <button type="submit" class="btn u-mt-8">Create Team &rarr;</button>
  </form>
  {events_markup}
</div>"""

    # Certificates section
    cert_markup = ""
    if certificates:
        cert_cards = []
        for c in certificates:
            cert_cards.append(f"""<div class="cert u-p-28 u-my-16">
  <div class="cert__kicker">&#10022; {esc(c.get("award_tier", "Verified Certificate"))} &#10022;</div>
  <div class="cert__title u-fs-18">Certificate of Completion</div>
  <div class="cert__recipient">{esc(c.get("recipient_name"))}</div>
  <div class="cert__project">{esc(project.get("title") if project else event.get("name"))}</div>
  <div class="cert__meta">
    <span>Event: {esc(event.get("name"))}</span>
    <span>Issued: {ui.format_iso(c.get("issued_at"))}</span>
  </div>
  <div class="cert__hash mono tiny">VERIFIED SHA256: {esc(c.get("sha256"))}</div>
</div>""")
        cert_markup = f"""<div class="u-mt-28">
  <div class="kicker">VERIFIED RECOGNITION</div>
  <h3>Issued Cryptographic Certificates</h3>
  {"".join(cert_cards)}
</div>"""

    # Project details
    project_section = ""
    if project:
        status_variant = "submitted" if project.get("status") == "submitted" else "draft"
        status_badge = ui.badge(project.get("status", "draft"), status_variant)
        project_section = f"""<div class="panel">
  <div class="ambient-red-aura" aria-hidden="true"></div>
  <div class="panel__head">
    <div>
      <span class="kicker">CANDIDATE SUBMISSION</span>
      <h3 class="panel-title-lg">{esc(project.get("title"))}</h3>
    </div>
    {status_badge}
  </div>
  <div class="panel__body">
    <p class="lede">{esc(project.get("summary") or "")}</p>
    <div class="cluster mb-18">
      <span class="chip chip--solid">Track: {esc(project.get("track") or "General")}</span>
      <span class="chip chip--red">★ {project.get("vote_count", 0)} Community Votes</span>
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
            "Register your team's project entry and software architecture before the submission deadline.",
            action_label="Create Project Submission",
            action_href=f"/participant/project/new{query}")

    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker">PARTICIPANT WORKSPACE</div>
    <div class="spread">
      <div>
        <h1 class="headline--xl">{esc(team.get("name"))}</h1>
        <p class="lede">Manage your team roster, publish submission drafts, and view verified certificates.</p>
      </div>
      <div class="chip chip--solid u-pad-pill u-fs-082">
        ACTIVE EVENT: {esc(event.get("name"))}
      </div>
    </div>
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
        <div><span class="dim">Submissions Close</span><br><strong class="u-text-accent u-fs-095">{ui.format_iso(event.get("submissions_close"))}</strong></div>
        <div><span class="dim">Judging Closes</span><br><strong class="u-text-ink u-fs-095">{ui.format_iso(event.get("judging_close"))}</strong></div>
        <div><span class="dim">Results Published</span><br><strong class="u-text-green u-fs-095">{ui.format_iso(event.get("results_publish_at"))}</strong></div>
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

    heading = "Edit Project Submission" if project else "Register New Project Submission"

    return f"""<div class="stack stack--lg u-center-820">
  <header>
    <a href="/participant" class="tiny mono dim">&larr; Back to Participant Workspace</a>
    <div class="kicker kicker--spaced">PROJECT DOSSIER</div>
    <h1 class="headline--xl">{heading}</h1>
    <p class="lede">Submissions are evaluated by judges against the competition rubric. Provide clear architectural context and reproduction links.</p>
  </header>

  <form method="POST" action="{esc(action_url)}" class="panel panel--sunk u-p-26">
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">

    <div class="form-stack">
      <div class="field">
        <label for="title" class="required">Project Title</label>
        <input type="text" id="title" name="title" value="{esc(title)}" required class="input" placeholder="e.g. HyperFlow Engine">
      </div>

      <div class="field">
        <label for="track">Competition Track</label>
        <select id="track" name="track" class="select">{"".join(track_opts)}</select>
        <span class="hint">Select the focus track that best matches your solution.</span>
      </div>

      <div class="field">
        <label for="summary" class="required">Elevator Pitch (One-line summary)</label>
        <input type="text" id="summary" name="summary" value="{esc(summary)}" required class="input" placeholder="High-impact one sentence summary of your technology...">
      </div>

      <div class="field">
        <label for="description">Detailed Description &amp; Architecture</label>
        <textarea id="description" name="description" rows="8" class="textarea" placeholder="Explain the problem statement, system architecture, key libraries, and technical novelty...">{esc(desc)}</textarea>
      </div>

      <div class="grid grid--2">
        <div class="field">
          <label for="repo_url">Repository URL</label>
          <input type="url" id="repo_url" name="repo_url" value="{esc(repo_url)}" class="input input--mono" placeholder="https://github.com/org/repo">
        </div>
        <div class="field">
          <label for="demo_url">Live Deployment / Demo URL</label>
          <input type="url" id="demo_url" name="demo_url" value="{esc(demo_url)}" class="input input--mono" placeholder="https://demo.app.com">
        </div>
      </div>
    </div>

    <div class="spread u-mt-28 u-pt-18 u-rule-top">
      <a href="/participant" class="btn btn--ghost">Cancel</a>
      <button type="submit" class="btn">Save &amp; Publish Submission &rarr;</button>
    </div>
  </form>
</div>"""
