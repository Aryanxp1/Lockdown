"""Organizer views: the single-event consoles, scoped to one hackathon."""

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
        status_variant = "submitted" if p.get("status") == "submitted" else "draft"
        status_badge = ui.badge(p.get("status", "draft"), status_variant)
        dup_tag = '<span class="chip chip--red u-ml-6">SUPERSEDED</span>' if p.get("superseded_by") else ""
        rows.append(f"""<tr>
  <td>
    <a href="/gallery/{esc(p.get('id'))}" class="u-text-white u-bold">{esc(p.get('title'))}</a>
    {dup_tag}
    <div class="tiny dim">Team: {esc(p.get('team_name'))}</div>
  </td>
  <td><span class="chip">{esc(p.get('track') or 'General')}</span></td>
  <td>{status_badge}</td>
  <td class="num font-bold">{p.get('review_count', 0)}</td>
  <td class="num u-text-accent">★ {p.get('vote_count', 0)}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="5" class="center dim is-empty">No submissions registered for this hackathon yet.</td></tr>'

    return f"""<div class="stack stack--lg">
  <header>
    <a href="/organizer/events/{esc(event.get("id"))}" class="tiny mono dim">&larr; Back to {esc(event.get("name"))} Console</a>
    <div class="kicker kicker--spaced">OPERATIONAL ROSTER</div>
    <h1 class="headline--xl">Submissions Dossier</h1>
    <p class="lede">All active and superseded team entries for <strong class="u-text-accent">{esc(event.get("name"))}</strong>.</p>
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
  <td>
    <strong class="u-text-white">{esc(j.get('name'))}</strong>
    <div class="tiny mono dim">{esc(j.get('email'))}</div>
  </td>
  <td class="num font-bold">{s.get('n', 0)}</td>
  <td class="num u-text-accent">{ui.format_score(s.get('mean'))}</td>
  <td class="num">{ui.format_score(s.get('sd'))}</td>
  <td>{flags or '<span class="tiny dim">—</span>'}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="5" class="center dim is-empty">No judges registered on this roster.</td></tr>'

    event_sub = f" for {esc(event.get('name'))}" if event else ""

    return f"""<div class="stack stack--lg">
  <header>
    <a href="{_back_href(event)}" class="tiny mono dim">&larr; Back to Organizer Console</a>
    <div class="kicker kicker--spaced">EVALUATION METRICS</div>
    <h1 class="headline--xl">Judges Roster &amp; Severity Calibration</h1>
    <p class="lede">Per-judge distribution metrics and variance analysis used for automated Z-score consensus normalization{event_sub}.</p>
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
  <td><span class="chip chip--solid">{esc(r.get('action'))}</span></td>
  <td class="tiny font-bold">{esc(r.get('actor_name') or r.get('actor_email') or 'System')}</td>
  <td class="mono tiny u-text-accent">{esc(r.get('entity_type'))}:{esc(r.get('entity_id'))}</td>
  <td class="mono tiny u-break-all u-text-ink-2">{esc(r.get('metadata') or '—')}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="5" class="center dim is-empty">No audit entries recorded.</td></tr>'
    pager_html = ui.pager(page, total_pages, lambda p: f"{base_url}?page={p}")

    return f"""<div class="stack stack--lg">
  <header>
    <a href="{_back_href(event)}" class="tiny mono dim">&larr; Back to Organizer Console</a>
    <div class="kicker kicker--spaced">CRYPTOGRAPHIC RECORD</div>
    <h1 class="headline--xl">Immutable Audit Trail</h1>
    <p class="lede">Append-only operational event ledger with cryptographic non-repudiation and timestamp verification.</p>
  </header>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Action</th>
          <th>Actor</th>
          <th>Entity</th>
          <th>Audit Details</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
    </table>
  </div>

  {pager_html}
</div>"""
