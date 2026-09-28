"""Public views for Lockdown: Landing, Gallery, Project Detail, Results, Auth."""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def landing(event: dict | None, stats: dict, recent_projects: list[dict],
            stages: list[dict], current_stage: str) -> str:
    """Render the homepage."""
    stage_bar = ui.stage_rail(stages, current_stage) if stages else ""

    stats_markup = f"""<div class="grid grid--4" style="margin-bottom:24px">
  {ui.stat_card("Submitted Projects", stats.get("projects", 0))}
  {ui.stat_card("Active Teams", stats.get("teams", 0))}
  {ui.stat_card("Completed Reviews", stats.get("reviews", 0))}
  {ui.stat_card("Community Votes", stats.get("votes", 0))}
</div>"""

    recent_cards = []
    for p in recent_projects:
        recent_cards.append(_project_card(p))
    cards_html = "".join(recent_cards) or ui.empty_state("No submissions yet", "Check back soon.")

    event_banner = ""
    if event:
        status_badge = ui.badge(event.get("status", "draft"), "open" if event.get("status") == "published" else "default")
        event_banner = f"""<div class="panel" style="margin-bottom:24px">
  <div class="panel__head">
    <div>
      <div class="kicker kicker--red">Current Event</div>
      <h2>{esc(event.get("name"))}</h2>
    </div>
    {status_badge}
  </div>
  <div class="panel__body">
    <p class="lede">{esc(event.get("description", ""))}</p>
    {stage_bar}
    <div class="cluster cluster--loose tiny mono dim" style="margin-top:12px">
      <span>Submissions Close: {ui.format_iso(event.get("submissions_close"))}</span>
      <span>Judging Closes: {ui.format_iso(event.get("judging_close"))}</span>
      <span>Results: {ui.format_iso(event.get("results_publish_at"))}</span>
    </div>
  </div>
</div>"""

    return f"""<div class="stack stack--lg">
  {event_banner}
  {stats_markup}
  <div>
    <div class="spread" style="margin-bottom:14px">
      <div>
        <div class="kicker">Exhibition</div>
        <h2>Recent Submissions</h2>
      </div>
      <a href="/gallery" class="btn btn--sm btn--ghost">View All Submissions &rarr;</a>
    </div>
    <div class="grid grid--3">
      {cards_html}
    </div>
  </div>
</div>"""


def _project_card(p: dict) -> str:
    tags = "".join(f'<span class="badge">{esc(t)}</span>' for t in (p.get("tags") or []))
    summary = esc(p.get("summary") or p.get("description", ""))
    if len(summary) > 130:
        summary = summary[:127] + "…"
    team_name = esc(p.get("team_name") or "Solo")
    pid = esc(p.get("id"))
    return f"""<article class="card card--link">
  <a href="/gallery/{pid}" class="card__stretch">{esc(p.get("title"))}</a>
  <div class="card__meta">
    <span>{team_name}</span>
    <span>{esc(p.get("track") or "General")}</span>
  </div>
  <h3 class="card__title">{esc(p.get("title"))}</h3>
  <div class="card__body">{summary}</div>
  <div class="card__foot">
    <div class="cluster">{tags}</div>
    <span class="mono tiny">{p.get("vote_count", 0)} votes</span>
  </div>
</article>"""


def gallery(*, projects: list[dict], tracks: list[str], selected_track: str,
            query: str, page: int, total_pages: int, total_count: int,
            sort: str = "title") -> str:
    """Render the public submissions exhibition gallery."""
    track_options = ['<option value="">All Tracks</option>']
    for t in tracks:
        sel = ' selected' if t == selected_track else ''
        track_options.append(f'<option value="{esc(t)}"{sel}>{esc(t)}</option>')

    sort_options = [
        ("title", "Alphabetical"),
        ("newest", "Newest First"),
        ("votes", "Most Upvoted"),
    ]
    sort_markup = []
    for val, lbl in sort_options:
        sel = ' selected' if val == sort else ''
        sort_markup.append(f'<option value="{val}"{sel}>{lbl}</option>')

    filter_form = f"""<form method="GET" action="/gallery" class="panel panel--sunk" style="padding:14px;margin-bottom:20px" data-autosubmit>
  <div class="grid grid--3 grid--tight">
    <div class="field">
      <label for="q">Search</label>
      <input type="search" id="q" name="q" value="{esc(query)}" placeholder="Search by title, team, tech..." class="input">
    </div>
    <div class="field">
      <label for="track">Track</label>
      <select id="track" name="track" class="select">{"".join(track_options)}</select>
    </div>
    <div class="field">
      <label for="sort">Sort</label>
      <select id="sort" name="sort" class="select">{"".join(sort_markup)}</select>
    </div>
  </div>
  <div class="spread" style="margin-top:10px">
    <span class="mono tiny dim">Showing {len(projects)} of {total_count} projects</span>
    <button type="submit" class="btn btn--sm">Apply Filters</button>
  </div>
</form>"""

    cards = [_project_card(p) for p in projects]
    grid = f'<div class="grid grid--3">{"".join(cards)}</div>' if cards else ui.empty_state("No submissions match", "Try broadening your query or selecting another track.")

    pager_html = ui.pager(page, total_pages, lambda p: f"/gallery?page={p}&track={esc(selected_track)}&q={esc(query)}&sort={esc(sort)}")

    return f"""<header style="margin-bottom:20px">
  <div class="kicker kicker--red">Exhibition</div>
  <h2 class="headline--lg">Project Gallery</h2>
  <p class="lede">Browse candidate solutions, inspect architectures, and cast community votes.</p>
</header>
{filter_form}
{grid}
{pager_html}"""


def project_detail(*, project: dict, team: dict, members: list[dict],
                   versions: list[dict], comments: list[dict],
                   user_has_voted: bool, user: dict | None,
                   csrf_token: str, superseded_by: dict | None = None,
                   duplicate_of: dict | None = None) -> str:
    """Render the full project dossier."""
    tags = "".join(f'<span class="badge">{esc(t)}</span>' for t in (project.get("tags") or []))

    # Version warning banners
    superseded_banner = ""
    if superseded_by:
        superseded_banner = ui.callout(
            f'This submission has been superseded by an updated entry: <a href="/gallery/{esc(superseded_by["id"])}"><strong>{esc(superseded_by["title"])}</strong></a>.',
            title="Superseded Revision", variant="warn")
    elif duplicate_of:
        superseded_banner = ui.callout(
            f'This submission is an updated revision of <a href="/gallery/{esc(duplicate_of["id"])}"><strong>{esc(duplicate_of["title"])}</strong></a>.',
            title="Revised Entry", variant="default")

    # Team member list
    member_items = "".join(f"<li>{esc(m.get('name'))} <span class='dim tiny mono'>({esc(m.get('role', 'member'))})</span></li>" for m in members)

    # Comments thread
    comment_blocks = []
    for c in comments:
        comment_blocks.append(f"""<div class="panel panel--sunk" style="padding:10px 14px;margin-bottom:8px">
  <div class="spread tiny mono dim" style="margin-bottom:4px">
    <span>{esc(c.get("author_name", "Anonymous"))}</span>
    <span>{ui.format_iso(c.get("created_at"))}</span>
  </div>
  <div>{esc(c.get("body"))}</div>
</div>""")
    comments_html = "".join(comment_blocks) or "<p class='dim tiny'>No comments yet.</p>"

    # Comment form (authenticated)
    comment_form = ""
    if user:
        comment_form = f"""<form method="POST" action="/gallery/{esc(project['id'])}/comment" style="margin-top:14px">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <div class="field">
    <label for="body">Add Comment</label>
    <textarea id="body" name="body" required rows="3" class="textarea" placeholder="Constructive feedback or question..."></textarea>
  </div>
  <button type="submit" class="btn btn--sm" style="margin-top:8px">Post Comment</button>
</form>"""
    else:
        comment_form = '<p class="tiny dim"><a href="/signin">Sign in</a> to leave a comment.</p>'

    # Vote button
    vote_action = f"""<form method="POST" action="/gallery/{esc(project['id'])}/vote">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <button type="submit" class="btn {'btn--danger' if user_has_voted else 'btn--ghost'} btn--block">
    {'★ Upvoted' if user_has_voted else '☆ Upvote Project'} ({project.get('vote_count', 0)})
  </button>
</form>""" if user else f'<a href="/signin" class="btn btn--ghost btn--block">Sign in to Vote ({project.get("vote_count", 0)})</a>'

    return f"""<div class="stack stack--lg">
  {superseded_banner}
  <div class="grid grid--sidebar">
    <article>
      <div class="kicker kicker--red">{esc(project.get("track") or "General Track")}</div>
      <h1 class="headline--xl">{esc(project.get("title"))}</h1>
      <p class="lede">{esc(project.get("summary") or "")}</p>
      <div class="cluster" style="margin-bottom:20px">{tags}</div>

      <div class="rule rule--thick"></div>

      <div class="stack">
        <h3>Description</h3>
        <div style="white-space:pre-wrap;line-height:1.6">{esc(project.get("description") or "No description provided.")}</div>
      </div>

      <div class="rule"></div>

      <div class="stack">
        <h3>Discussion ({len(comments)})</h3>
        {comments_html}
        {comment_form}
      </div>
    </article>

    <aside class="stack">
      <div class="panel">
        <div class="panel__head"><h3>Support</h3></div>
        <div class="panel__body">
          {vote_action}
        </div>
      </div>

      <div class="panel">
        <div class="panel__head"><h3>Team</h3></div>
        <div class="panel__body">
          <h4>{esc(team.get("name"))}</h4>
          <ul style="padding-left:18px;margin:8px 0 0">{member_items}</ul>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head"><h3>Links</h3></div>
        <div class="panel__body stack">
          {f'<div><span class="dim tiny mono">REPO</span><br><a href="{esc(project.get("repo_url"))}" target="_blank" rel="noopener">{esc(project.get("repo_url"))}</a></div>' if project.get("repo_url") else ''}
          {f'<div><span class="dim tiny mono">DEMO</span><br><a href="{esc(project.get("demo_url"))}" target="_blank" rel="noopener">{esc(project.get("demo_url"))}</a></div>' if project.get("demo_url") else ''}
        </div>
      </div>
    </aside>
  </div>
</div>"""


def results_leaderboard(*, event: dict, ranked: list[dict],
                        is_published: bool, user_role: str | None) -> str:
    """Render the official competition scoreboard."""
    if not is_published and user_role not in ("organizer", "admin"):
        return f"""<div class="panel" style="max-width:620px;margin:40px auto;text-align:center;padding:32px">
  <div class="stamp" style="margin-bottom:14px">EMBARGOED</div>
  <h2>Official Results Pending</h2>
  <p class="lede">Final scores and awards are scheduled for release at:<br>
     <strong>{ui.format_iso(event.get("results_publish_at"))}</strong></p>
  <p class="dim tiny">Only organizers may view pre-publication standings.</p>
</div>"""

    embargo_warning = ""
    if not is_published:
        embargo_warning = ui.callout(
            "These results are currently embargoed from participants and the public. "
            "You are viewing them under organizer clearance.",
            title="Pre-Publication Preview", variant="warn")

    rows = []
    for r in ranked:
        rank_num = r.get("published_rank") or "—"
        medal = ""
        if rank_num == 1:
            medal = " 🥇"
        elif rank_num == 2:
            medal = " 🥈"
        elif rank_num == 3:
            medal = " 🥉"

        flags = " ".join(f'<span class="badge badge--draft">{esc(f)}</span>' for f in r.get("flags", []))
        rows.append(f"""<tr>
  <td class="num"><strong>{rank_num}{medal}</strong></td>
  <td>
    <a href="/gallery/{esc(r.get('project_id'))}"><strong>{esc(r.get('title'))}</strong></a>
    <div class="tiny dim">{esc(r.get('team_name'))} · {esc(r.get('track') or 'General')}</div>
  </td>
  <td class="num">{ui.format_score(r.get('raw_mean'))}</td>
  <td class="num"><strong>{ui.format_score(r.get('normalized_mean'))}</strong></td>
  <td class="num">{r.get('review_count', 0)}</td>
  <td>{flags}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="6" class="center dim">No completed evaluations.</td></tr>'

    return f"""<div class="stack stack--lg">
  {embargo_warning}
  <header>
    <div class="kicker kicker--red">Official Ledger</div>
    <h1 class="headline--lg">{esc(event.get("name"))} — Final Standings</h1>
    <p class="lede">Z-score normalized judge consensus. Scores scaled to 0–100.</p>
  </header>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th style="width:60px" class="num">Rank</th>
          <th>Project / Team</th>
          <th class="num">Raw Mean</th>
          <th class="num">Normalized</th>
          <th class="num">Reviews</th>
          <th>Flags</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
    </table>
  </div>
</div>"""


def signin_form(*, csrf_token: str, next_url: str = "") -> str:
    """Render the simple email/password login form."""
    return f"""<div class="panel" style="max-width:440px;margin:40px auto">
  <div class="panel__head">
    <h2>Sign In</h2>
    <span class="chip">Credentials</span>
  </div>
  <div class="panel__body">
    <form method="POST" action="/signin" class="form-stack">
      <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
      <input type="hidden" name="next" value="{esc(next_url)}">

      <div class="field">
        <label for="email">Email Address</label>
        <input type="email" id="email" name="email" required autofocus class="input">
      </div>

      <div class="field">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" required class="input">
      </div>

      <button type="submit" class="btn btn--block" style="margin-top:8px">Authenticate</button>
    </form>
    <div class="tiny dim" style="margin-top:14px;text-align:center">
      Staff demo: <code>organizer@dogfood.test</code> (pwd: <code>dogfood-demo-2026</code>)
    </div>
  </div>
</div>"""


