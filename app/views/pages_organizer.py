"""Organizer views: the single-event consoles, now scoped to one hackathon.

These are the older operations pages: the submission dossier, the judge
calibration roster and the audit trail. Each one renders exactly one event --
the handler resolves it and proves the caller may manage it before the rows are
queried, so these pages never mix two hackathons together. The shelf of events
and the per-event desk live in `pages_manage.py`.
"""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def _back_href(event: dict | None) -> str:
    """Where "back" goes: this hackathon's desk, or the shelf of hackathons."""
    return "/organizer/events/%s" % esc(event["id"]) if event else "/organizer"


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
    <a href="/organizer/events/{esc(event.get("id"))}" class="tiny mono dim">&larr; Back to this hackathon</a>
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


def judges_roster(*, judges: list[dict], stats: dict[str, dict],
                  event: dict | None = None) -> str:
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
    <a href="{_back_href(event)}" class="tiny mono dim">&larr; Back to this hackathon</a>
    <h1 class="headline--lg" style="margin-top:10px">Judges Roster &amp; Severity Calibration</h1>
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


def audit_trail(*, records: list[dict], page: int, total_pages: int,
                base_url: str = "/organizer/audit", event: dict | None = None) -> str:
    """Render one hackathon's slice of the immutable audit trail."""
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
    pager_html = ui.pager(page, total_pages, lambda p: f"{base_url}?page={p}")

    return f"""<div class="stack stack--lg">
  <header>
    <a href="{_back_href(event)}" class="tiny mono dim">&larr; Back to this hackathon</a>
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

