"""Judge views: Assignment queue, review scoring form, evaluation history."""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def judge_dashboard(*, judge: dict, assignments: list[dict],
                    event: dict, progress: dict) -> str:
    """Render the judge's home overview with clear metrics and queue."""
    completed = progress.get("completed", 0)
    total = progress.get("total", 0)
    pending = total - completed

    rows = []
    for a in assignments:
        is_done = a.get("review_status") in ("submitted", "finalized")
        status_chip = ui.chip("Accepted" if a.get("status") == "accepted" else "Assigned")
        review_badge = ui.badge("Complete" if is_done else "Pending Evaluation",
                                "submitted" if is_done else "open")
        btn_variant = "ghost" if is_done else "default"
        btn_label = "Edit Evaluation" if is_done else "Evaluate Submission &rarr;"
        action_btn = ui.button(btn_label,
                               href=f"/judge/evaluate/{a['project_id']}",
                               size="sm", variant=btn_variant)

        rows.append(f"""<tr>
  <td>
    <div class="u-bold u-fs-102 u-text-white">{esc(a.get('project_title'))}</div>
    <div class="tiny dim mono u-mt-2">Track: {esc(a.get('track') or 'General')}</div>
  </td>
  <td>{status_chip}</td>
  <td>{review_badge}</td>
  <td class="actions">{action_btn}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="4" class="center dim is-empty">No projects assigned to your evaluation queue.</td></tr>'

    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker">EVALUATION PORTAL</div>
    <div class="spread">
      <div>
        <h1 class="headline--xl">Welcome, {esc(judge.get("name"))}</h1>
        <p class="lede">Double-blind rubric evaluation portal for <strong class="u-text-accent">{esc(event.get('name'))}</strong>.</p>
      </div>
      <div class="chip chip--solid u-pad-pill">
        JUDGING ROSTER
      </div>
    </div>
  </header>

  <div class="grid grid--3">
    {ui.stat_card("Assigned Projects", total, hint="Total workload")}
    {ui.stat_card("Evaluations Completed", completed, hint="Submitted to consensus")}
    {ui.stat_card("Pending Evaluations", pending, red=pending > 0, hint="Action required")}
  </div>

  <div class="panel">
    <div class="panel__head">
      <div>
        <h3>Evaluation Queue</h3>
        <span class="tiny dim">Review candidate projects against standard rubrics</span>
      </div>
      <span class="chip chip--solid">{completed}/{total} Completed</span>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Project / Track</th>
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
    """Render the judging rubric score submission form with live calculated score feedback."""
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
    <h4 class="u-fs-11 u-text-white">{esc(c.get("name"))}</h4>
    <span class="rubric-weight">Weight Factor: {c.get("weight", 1.0)}x</span>
  </div>
  <p class="tiny dim u-my-6-12 u-lh-15">{esc(c.get("description", ""))}</p>
  <div class="score-radios">
    {"".join(radios)}
  </div>
</div>""")

    notes = review.get("notes") or "" if review else ""
    private_notes = review.get("private_notes") or "" if review else ""

    return f"""<div class="stack stack--lg u-center-840">
  <header>
    <a href="/judge" class="tiny mono dim">&larr; Back to Judge Queue</a>
    <div class="kicker kicker--spaced">COMPETITION RUBRIC</div>
    <div class="spread u-items-start">
      <div>
        <h1 class="headline--xl">Evaluating: {esc(project.get("title"))}</h1>
        <p class="lede">{esc(project.get("summary") or "")}</p>
        <div class="cluster u-mt-10">
          {f'<a href="{esc(project.get("repo_url"))}" target="_blank" rel="noopener" class="chip">Repo Link &nearr;</a>' if project.get("repo_url") else ''}
          {f'<a href="{esc(project.get("demo_url"))}" target="_blank" rel="noopener" class="chip">Live Demo &nearr;</a>' if project.get("demo_url") else ''}
          <a href="/gallery/{esc(project.get('id'))}" target="_blank" rel="noopener" class="chip">Open Full Dossier &nearr;</a>
        </div>
      </div>
      <div id="live-score-badge" class="stat live-score-badge" aria-live="polite">
        <div id="live-score-val" class="stat__value stat__value--lg">—</div>
        <div class="stat__label">Est. Raw %</div>
      </div>
    </div>
    <div class="shortcut-tip">
      Keyboard Shortcut: Click or Tab to any criterion and press keys <strong>1–5</strong> to select score instantly.
    </div>
  </header>

  <form method="POST" action="/judge/evaluate/{esc(project['id'])}" class="panel panel--sunk form-panel-pad" data-autosave>
    <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">

    <div class="stack">
      {"".join(criteria_inputs)}
    </div>

    <div class="rule"></div>

    <div class="form-stack">
      <div class="field">
        <label for="notes">Public Feedback for Team</label>
        <span class="hint">Constructive comments shared with participants upon official results publication.</span>
        <textarea id="notes" name="notes" rows="4" class="textarea" placeholder="What stood out? Where could the architecture or implementation improve?">{esc(notes)}</textarea>
      </div>

      <div class="field">
        <label for="private_notes">Private Organizer Notes</label>
        <span class="hint">Confidential to the organizing committee and evaluation audit trail.</span>
        <textarea id="private_notes" name="private_notes" rows="3" class="textarea" placeholder="Internal observations, integrity questions, or tie-break context...">{esc(private_notes)}</textarea>
      </div>
    </div>

    <div class="spread u-mt-24 u-pt-16 u-rule-top u-wrap u-gap-14">
      <span id="autosave-status" class="mono tiny dim">Auto-saved draft active</span>
      <div class="cluster">
        <button type="submit" name="action" value="draft" class="btn btn--ghost">Save Draft</button>
        <button type="submit" name="action" value="submit" class="btn">Submit Final Evaluation &rarr;</button>
      </div>
    </div>
  </form>
</div>"""
