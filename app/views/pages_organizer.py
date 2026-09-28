"""Organizer views: Operations center, submissions, judges, audit trail."""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def organizer_dashboard(*, event: dict, stats: dict, recent_audit: list[dict],
                        csrf_token: str) -> str:
    """Render the main operations control panel."""
    audit_rows = []
    for a in recent_audit:
        audit_rows.append(f"""<tr>
  <td class="mono tiny">{ui.format_iso(a.get('created_at'))}</td>
  <td><span class="chip">{esc(a.get('action'))}</span></td>
  <td class="tiny">{esc(a.get('actor_name') or a.get('actor_email') or 'System')}</td>
  <td class="mono tiny">{esc(a.get('entity_type'))}:{esc(a.get('entity_id'))}</td>
</tr>""")

    audit_tbody = "".join(audit_rows) if audit_rows else '<tr><td colspan="4" class="center dim">No audit records.</td></tr>'

    return f"""<div class="stack stack--lg">
  <header class="spread">
    <div>
      <div class="kicker kicker--red">Operations Command</div>
      <h1 class="headline--lg">{esc(event.get("name"))}</h1>
      <p class="lede">Competition status: <strong>{esc(event.get("status"))}</strong></p>
    </div>
    <div class="cluster">
      <form method="POST" action="/organizer/publish">
        <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
        <button type="submit" class="btn btn--danger" data-confirm="Are you sure you want to publish official results?">Publish Results</button>
      </form>
    </div>
  </header>

  <div class="grid grid--4">
    {ui.stat_card("Total Teams", stats.get("teams", 0))}
    {ui.stat_card("Submissions", stats.get("projects", 0))}
    {ui.stat_card("Active Judges", stats.get("judges", 0))}
    {ui.stat_card("Reviews In", stats.get("reviews", 0))}
  </div>

  <div class="grid grid--2">
    <div class="panel">
      <div class="panel__head"><h3>Quick Operations</h3></div>
      <div class="panel__body stack">
        <a href="/organizer/submissions" class="btn btn--ghost btn--block">Manage Submissions &rarr;</a>
        <a href="/organizer/judges" class="btn btn--ghost btn--block">Judge Assignments & Progress &rarr;</a>
        <a href="/organizer/export" class="btn btn--ghost btn--block">Export Standings (CSV/JSON) &rarr;</a>
        <a href="/organizer/audit" class="btn btn--ghost btn--block">Full Immutable Audit Log &rarr;</a>
      </div>
    </div>

    <div class="panel">
      <div class="panel__head"><h3>Recent Actions</h3></div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Target</th>
            </tr>
          </thead>
          <tbody>
            {audit_tbody}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>"""


def submissions_list(*, projects: list[dict], event: dict) -> str:
    """Render the submissions management roster."""
    rows = []
    for p in projects:
        status_badge = ui.badge(p.get("status", "draft"), "submitted" if p.get("status") == "submitted" else "draft")
        dup_tag = '<span class="chip chip--red">SUPERSEDED</span>' if p.get("superseded_by") else ""
        rows.append(f"""<tr>
  <td>
    <a href="/gallery/{esc(p.get('id'))}"><strong>{esc(p.get('title'))}</strong></a>
    {dup_tag}
    <div class="tiny dim">{esc(p.get('team_name'))}</div>
  </td>
  <td>{esc(p.get('track') or 'General')}</td>
  <td>{status_badge}</td>
  <td class="num">{p.get('review_count', 0)}</td>
  <td class="num">{p.get('vote_count', 0)}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="5" class="center dim">No submissions found.</td></tr>'

    return f"""<div class="stack stack--lg">
  <header>
    <a href="/organizer" class="tiny mono dim">&larr; Back to Command Center</a>
    <h1 class="headline--lg" style="margin-top:10px">Submissions Dossier</h1>
    <p class="lede">All active and superseded team entries for {esc(event.get("name"))}.</p>
  </header>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Project / Team</th>
          <th>Track</th>
          <th>Status</th>
          <th class="num">Reviews</th>
          <th class="num">Votes</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
    </table>
  </div>
</div>"""


def judges_roster(*, judges: list[dict], stats: dict[str, dict]) -> str:
    """Render the judges monitoring console with normalization metrics."""
    rows = []
    for j in judges:
        jid = j["id"]
        s = stats.get(jid, {})
        flags = " ".join(f'<span class="badge badge--draft">{esc(f)}</span>' for f in s.get("flags", []))

        rows.append(f"""<tr>
  <td><strong>{esc(j.get('name'))}</strong><div class="tiny dim">{esc(j.get('email'))}</div></td>
  <td class="num">{s.get('n', 0)}</td>
  <td class="num">{ui.format_score(s.get('mean'))}</td>
  <td class="num">{ui.format_score(s.get('sd'))}</td>
  <td>{flags}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="5" class="center dim">No judges registered.</td></tr>'

    return f"""<div class="stack stack--lg">
  <header>
    <a href="/organizer" class="tiny mono dim">&larr; Back to Command Center</a>
    <h1 class="headline--lg" style="margin-top:10px">Judges Roster & Severity Calibration</h1>
    <p class="lede">Per-judge distribution metrics used for z-score normalization.</p>
  </header>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Judge</th>
          <th class="num">Reviews</th>
          <th class="num">Mean</th>
          <th class="num">Std Dev</th>
          <th>Calibration Flags</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
    </table>
  </div>
</div>"""


def audit_trail(*, records: list[dict], page: int, total_pages: int) -> str:
    """Render the full immutable audit trail."""
    rows = []
    for r in records:
        rows.append(f"""<tr>
  <td class="mono tiny">{ui.format_iso(r.get('created_at'))}</td>
  <td><span class="chip">{esc(r.get('action'))}</span></td>
  <td class="tiny">{esc(r.get('actor_name') or r.get('actor_email') or 'System')}</td>
  <td class="mono tiny">{esc(r.get('entity_type'))}:{esc(r.get('entity_id'))}</td>
  <td class="mono tiny" style="word-break:break-all">{esc(r.get('metadata') or '')}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="5" class="center dim">No audit entries.</td></tr>'
    pager_html = ui.pager(page, total_pages, lambda p: f"/organizer/audit?page={p}")

    return f"""<div class="stack stack--lg">
  <header>
    <a href="/organizer" class="tiny mono dim">&larr; Back to Command Center</a>
    <h1 class="headline--lg" style="margin-top:10px">Immutable Audit Trail</h1>
    <p class="lede">Append-only operational history with cryptographic non-repudiation.</p>
  </header>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Action</th>
          <th>Actor</th>
          <th>Entity</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
    </table>
  </div>

  {pager_html}
</div>"""

