"""Judge views: Assignment queue, review scoring form, evaluation history."""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def judge_dashboard(*, judge: dict, assignments: list[dict],
                    event: dict, progress: dict) -> str:
    """Render the judge's home overview."""
    completed = progress.get("completed", 0)
    total = progress.get("total", 0)
    pending = total - completed

    rows = []
    for a in assignments:
        status_chip = ui.chip("Accepted" if a.get("status") == "accepted" else "Assigned")
        review_badge = ui.badge("Complete" if a.get("review_status") in ("submitted", "finalized") else "Pending",
                                "submitted" if a.get("review_status") in ("submitted", "finalized") else "open")
        action_btn = ui.button("Evaluate" if not a.get("review_id") else "Edit Evaluation",
                               href=f"/judge/evaluate/{a['project_id']}", size="sm")

        rows.append(f"""<tr>
  <td><strong>{esc(a.get('project_title'))}</strong><div class="tiny dim">{esc(a.get('track') or 'General')}</div></td>
  <td>{status_chip}</td>
  <td>{review_badge}</td>
  <td class="actions">{action_btn}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="4" class="center dim">No projects assigned.</td></tr>'

    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker kicker--red">Judge Evaluation Portal</div>
    <h1 class="headline--lg">Welcome, {esc(judge.get("name"))}</h1>
    <p class="lede">Review your assigned projects against the official competition rubric.</p>
  </header>

  <div class="grid grid--3">
    {ui.stat_card("Assigned Projects", total)}
    {ui.stat_card("Evaluations Completed", completed)}
    {ui.stat_card("Pending Evaluations", pending, red=pending > 0)}
  </div>

  <div class="panel">
    <div class="panel__head">
      <h3>Assigned Queue</h3>
      <span class="mono tiny">{completed}/{total} Completed</span>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Project</th>
            <th>Assignment</th>
            <th>Review Status</th>
            <th class="actions">Action</th>
          </tr>
        </thead>
        <tbody>
          {tbody}
        </tbody>
      </table>
    </div>
  </div>
</div>"""


def evaluation_form(*, project: dict, rubric: dict, criteria: list[dict],
                    review: dict | None, existing_scores: dict[str, int],
                    csrf_token: str) -> str:
    """Render the judging rubric score submission form."""
    criteria_inputs = []
    for c in criteria:
        cid = c["id"]
        current_val = existing_scores.get(cid, 3)
        radios = []
        for score_val in range(int(c.get("min_score", 1)), int(c.get("max_score", 5)) + 1):
            checked = " checked" if score_val == current_val else ""
            radios.append(f"""<label class="score-radio">
  <input type="radio" name="score_{esc(cid)}" value="{score_val}"{checked} required>
  <span>{score_val}</span>
</label>""")

        criteria_inputs.append(f"""<div class="rubric-criteria" tabindex="0" data-weight="{c.get('weight', 1.0)}" data-min="{c.get('min_score', 1)}" data-max="{c.get('max_score', 5)}" aria-label="{esc(c.get('name'))}">
  <div class="rubric-header">
    <h4>{esc(c.get("name"))}</h4>
    <span class="rubric-weight">Weight: {c.get("weight", 1.0)}</span>
  </div>
  <p class="tiny dim" style="margin:4px 0 8px">{esc(c.get("description", ""))}</p>
  <div class="score-radios">
    {"".join(radios)}
  </div>
</div>""")

    notes = review.get("notes") or "" if review else ""
    private_notes = review.get("private_notes") or "" if review else ""

    return f"""<div class="stack stack--lg" style="max-width:800px;margin:0 auto">
  <header>
    <a href="/judge" class="tiny mono dim">&larr; Back to Judge Queue</a>
    <div class="kicker kicker--red" style="margin-top:10px">Scoring Rubric</div>
    <div class="spread" style="align-items:flex-start">
      <div>
        <h1 class="headline--lg">Evaluating: {esc(project.get("title"))}</h1>
        <p class="lede">{esc(project.get("summary") or "")}</p>
      </div>
      <div id="live-score-badge" class="stat stat--red" style="padding:8px 14px;min-width:110px;text-align:center" aria-live="polite">
        <div id="live-score-val" class="stat__value" style="font-size:1.6rem">—</div>
        <div class="stat__label">Est. Raw %</div>
      </div>
    </div>
    <div class="tiny mono dim" style="margin-top:4px">
      Keyboard tip: Click or Tab to a criterion and press 1–5 to select a score instantly.
    </div>
  </header>

  <form method="POST" action="/judge/evaluate/{esc(project['id'])}" class="panel panel--sunk" style="padding:20px" data-autosave>
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">

    <div class="stack">
      {"".join(criteria_inputs)}
    </div>

    <div class="rule"></div>

    <div class="form-stack">
      <div class="field">
        <label for="notes">Public Feedback for Team</label>
        <span class="hint">Constructive comments shared with participants upon official results release.</span>
        <textarea id="notes" name="notes" rows="4" class="textarea" placeholder="What stood out? Where can this project improve?">{esc(notes)}</textarea>
      </div>

      <div class="field">
        <label for="private_notes">Private Organizer Notes</label>
        <span class="hint">Confidential to judging committee and evaluation auditing.</span>
        <textarea id="private_notes" name="private_notes" rows="3" class="textarea" placeholder="Internal notes, integrity questions, or tie-break observations...">{esc(private_notes)}</textarea>
      </div>
    </div>

    <div class="spread" style="margin-top:20px;flex-wrap:wrap;gap:12px">
      <span id="autosave-status" class="mono tiny dim">Auto-saved as draft</span>
      <div class="cluster">
        <button type="submit" name="action" value="draft" class="btn btn--ghost">Save Draft</button>
        <button type="submit" name="action" value="submit" class="btn">Submit Final Evaluation</button>
      </div>
    </div>
  </form>
</div>"""
