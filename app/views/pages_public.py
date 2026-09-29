"""Public views for Lockdown: Landing, Gallery, Project Detail, Results, Auth."""

from __future__ import annotations

from typing import Any

from . import ui
from .ui import esc


def landing(event: dict | None, stats: dict, recent_projects: list[dict],
            stages: list[dict], current_stage: str) -> str:
    """Render the flagship homepage with editorial asymmetric hero and 3D globe."""
    stage_bar = ui.stage_rail(stages, current_stage) if stages else ""

    recent_cards = [ui.project_card(p) for p in recent_projects]
    cards_html = "".join(recent_cards) or ui.empty_state("No submissions yet", "Check back soon as teams publish their entries.")

    event_banner = ""
    if event:
        status_badge = ui.badge(event.get("status", "draft"), "open" if event.get("status") == "published" else "default")
        event_slug = esc(event.get("slug"))
        event_name = esc(event.get("name"))
        event_desc = esc(event.get("description", ""))
        event_banner = f"""<section class="spotlight-section">
  <div class="spotlight-card">
    <div class="spotlight-card__header">
      <div class="spotlight-card__title-wrap">
        <span class="editorial-kicker">FLAGSHIP IN PROGRESS</span>
        <h2 class="spotlight-card__title"><a href="/events/{event_slug}">{event_name}</a></h2>
      </div>
      {status_badge}
    </div>
    <div class="spotlight-card__body">
      <p class="spotlight-card__desc">{event_desc}</p>
      {stage_bar}
      <div class="spotlight-card__meta">
        <div class="meta-item">
          <span class="meta-lbl">Submissions Close</span>
          <span class="meta-val">{ui.format_iso(event.get("submissions_close"))}</span>
        </div>
        <div class="meta-divider" aria-hidden="true">&middot;</div>
        <div class="meta-item">
          <span class="meta-lbl">Judging Closes</span>
          <span class="meta-val">{ui.format_iso(event.get("judging_close"))}</span>
        </div>
        <div class="meta-divider" aria-hidden="true">&middot;</div>
        <div class="meta-item">
          <span class="meta-lbl">Results Published</span>
          <span class="meta-val">{ui.format_iso(event.get("results_publish_at"))}</span>
        </div>
        <div class="spotlight-card__cta">
          <a href="/events/{event_slug}" class="btn btn--sm btn--primary">View Competition &rarr;</a>
        </div>
      </div>
    </div>
  </div>
</section>"""

    return f"""<div class="landing-page">
  <!-- Asymmetric Editorial Hero with Aceternity Boxes Ripple & Canvas Text -->
  <section class="editorial-hero">
    <canvas id="boxes-ripple-canvas" class="boxes-ripple-canvas" aria-hidden="true"></canvas>
    <div class="editorial-hero__grid">
      <div class="editorial-hero__col-left">
        <div class="editorial-kicker">
          <span class="status-dot"></span>
          <span>COMPETITION &amp; JUDGING INFRASTRUCTURE</span>
        </div>
        <div class="hero-statement-wrap">
          <canvas id="hero-canvas-text" class="hero-canvas-text" aria-hidden="true"></canvas>
          <h1 class="editorial-statement">
            Run.<br>
            Judge.<br>
            <span class="editorial-statement__accent">Ship.</span>
          </h1>
        </div>
        <p class="editorial-lead">
          Lockdown is the deterministic competition substrate for high-stakes hackathons.
          Automated double-blind evaluation queues, Z-score consensus scoring, and cryptographic non-repudiation for engineering squads worldwide.
        </p>
        <div class="editorial-actions">
          <a href="/events" class="btn btn--primary btn--hero">Explore Hackathons &rarr;</a>
          <a href="/gallery" class="btn btn--ghost btn--hero">View Project Gallery</a>
        </div>
        <div class="telemetry-bar">
          <div class="telemetry-item">
            <span class="telemetry-val">{stats.get("projects", 0)}</span>
            <span class="telemetry-lbl">Submissions</span>
          </div>
          <div class="telemetry-sep" aria-hidden="true">&middot;</div>
          <div class="telemetry-item">
            <span class="telemetry-val">{stats.get("teams", 0)}</span>
            <span class="telemetry-lbl">Active Teams</span>
          </div>
          <div class="telemetry-sep" aria-hidden="true">&middot;</div>
          <div class="telemetry-item">
            <span class="telemetry-val">{stats.get("reviews", 0)}</span>
            <span class="telemetry-lbl">Evaluations</span>
          </div>
          <div class="telemetry-sep" aria-hidden="true">&middot;</div>
          <div class="telemetry-item">
            <span class="telemetry-val">{stats.get("votes", 0)}</span>
            <span class="telemetry-lbl">Peer Upvotes</span>
          </div>
        </div>
      </div>

      <div class="editorial-hero__col-right">
        <div class="globe-stage">
          <div class="globe-stage__canvas-wrap">
            <canvas id="lockdown-globe" class="globe-canvas" width="560" height="560" aria-label="Interactive 3D network globe visualization"></canvas>
          </div>
          <div class="globe-card">
            <div class="globe-card__eyebrow">
              <span class="status-dot"></span>
              <span>GLOBAL CONSENSUS NETWORK</span>
            </div>
            <div class="globe-card__title">Decentralized Evaluation Matrix</div>
            <p class="globe-card__desc">
              Synchronizing teams, projects, and judges across 14 international hubs with live consensus telemetry and variance dampening.
            </p>
            <div class="globe-card__stats">
              <span>14 Active Hubs</span>
              <span aria-hidden="true">&middot;</span>
              <span>11 Consensus Arcs</span>
              <span aria-hidden="true">&middot;</span>
              <span>Normalized Z-Scores</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  {event_banner}

  <!-- Exhibition Section -->
  <section class="exhibition-section">
    <div class="section-header">
      <div>
        <div class="editorial-kicker">PUBLIC EXHIBITION</div>
        <h2 class="section-title">Recent Submissions</h2>
      </div>
      <a href="/gallery" class="btn btn--sm btn--ghost">View All Submissions &rarr;</a>
    </div>
    <div class="grid grid--3">
      {cards_html}
    </div>
  </section>
</div>"""


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

    filter_form = f"""<form method="GET" action="/gallery" class="panel panel--sunk gallery-filter" data-autosubmit>
  <div class="grid grid--3 grid--tight">
    <div class="field">
      <label for="q">Search Submissions</label>
      <input type="search" id="q" name="q" value="{esc(query)}" placeholder="Search by title, team, stack..." class="input">
    </div>
    <div class="field">
      <label for="track">Track Filter</label>
      <select id="track" name="track" class="select">{"".join(track_options)}</select>
    </div>
    <div class="field">
      <label for="sort">Sort Order</label>
      <select id="sort" name="sort" class="select">{"".join(sort_markup)}</select>
    </div>
  </div>
  <div class="spread gallery-filter__footer">
    <span class="mono tiny dim">Showing <strong class="cyan-val">{len(projects)}</strong> of {total_count} projects</span>
    <button type="submit" class="btn btn--sm">Apply Filters</button>
  </div>
</form>"""

    cards = [ui.project_card(p) for p in projects]
    grid = f'<div class="grid grid--3">{"".join(cards)}</div>' if cards else ui.empty_state("No submissions match", "Try broadening your query or selecting another competition track.")

    pager_html = ui.pager(page, total_pages, lambda p: f"/gallery?page={p}&track={esc(selected_track)}&q={esc(query)}&sort={esc(sort)}")

    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker">DISCOVERY &amp; EXHIBITION</div>
    <h1 class="headline--xl">Project Gallery</h1>
    <p class="lede">Browse verified candidate projects, examine software architecture, and support teams with peer upvotes.</p>
  </header>
  {filter_form}
  {grid}
  {pager_html}
</div>"""


def project_detail(*, project: dict, team: dict, members: list[dict],
                   versions: list[dict], comments: list[dict],
                   user_has_voted: bool, user: dict | None,
                   csrf_token: str, superseded_by: dict | None = None,
                   duplicate_of: dict | None = None) -> str:
    """Render the full project dossier."""
    tags = "".join(f'<span class="badge badge--tag">{esc(t)}</span>' for t in (project.get("tags") or []))

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
    member_items = "".join(f"<li class='member-item'><span>{esc(m.get('name'))}</span> <span class='chip'>{esc(m.get('role', 'member'))}</span></li>" for m in members)

    # Comments thread
    comment_blocks = []
    for c in comments:
        comment_blocks.append(f"""<div class="panel panel--sunk comment-block">
  <div class="spread tiny mono dim comment-meta">
    <span class="cyan-val">{esc(c.get("author_name", "Anonymous"))}</span>
    <span>{ui.format_iso(c.get("created_at"))}</span>
  </div>
  <div class="comment-body">{esc(c.get("body"))}</div>
</div>""")
    comments_html = "".join(comment_blocks) or "<p class='dim tiny'>No discussion comments posted yet.</p>"

    # Comment form (authenticated)
    comment_form = ""
    if user:
        comment_form = f"""<form method="POST" action="/gallery/{esc(project['id'])}/comment" class="comment-form">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <div class="field">
    <label for="body">Post Technical Feedback or Question</label>
    <textarea id="body" name="body" required rows="3" class="textarea" placeholder="Constructive feedback, technical questions, or architecture review..."></textarea>
  </div>
  <button type="submit" class="btn btn--sm">Post Comment</button>
</form>"""
    else:
        comment_form = '<p class="tiny dim footnote-text"><a href="/signin">Sign in</a> to leave a comment or join the discussion.</p>'

    # Vote button
    voted_cls = " btn--voted" if user_has_voted else ""
    vote_action = f"""<form method="POST" action="/gallery/{esc(project['id'])}/vote">
  <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
  <button type="submit" class="btn {'btn--ghost' if user_has_voted else ''} btn--block{voted_cls}">
    {'★ Upvoted by You' if user_has_voted else '☆ Cast Community Upvote'} ({project.get('vote_count', 0)})
  </button>
</form>""" if user else f'<a href="/signin" class="btn btn--ghost btn--block">Sign in to Vote ({project.get("vote_count", 0)})</a>'

    return f"""<div class="stack stack--lg">
  {superseded_banner}
  <div class="grid grid--sidebar">
    <article>
      <div class="kicker">{esc(project.get("track") or "General Track")}</div>
      <h1 class="headline--xl">{esc(project.get("title"))}</h1>
      <p class="lede">{esc(project.get("summary") or "")}</p>
      <div class="cluster project-tags">{tags}</div>

      <div class="rule rule--thick"></div>

      <div class="stack">
        <h3>System Overview &amp; Architecture</h3>
        <div class="project-overview-prose">{esc(project.get("description") or "No detailed description provided.")}</div>
      </div>

      <div class="rule"></div>

      <div class="stack">
        <h3>Engineering Discussion ({len(comments)})</h3>
        {comments_html}
        {comment_form}
      </div>
    </article>

    <aside class="stack">
      <div class="panel">
        <div class="panel__head"><h3>Community Support</h3></div>
        <div class="panel__body">
          {vote_action}
        </div>
      </div>

      <div class="panel">
        <div class="panel__head"><h3>Team Roster</h3></div>
        <div class="panel__body">
          <div class="team-title">{esc(team.get("name"))}</div>
          <ul class="plain-list">{member_items}</ul>
        </div>
      </div>

      <div class="panel">
        <div class="panel__head"><h3>External Links</h3></div>
        <div class="panel__body stack">
          {f'<div><span class="dim tiny mono">SOURCE CODE</span><br><a href="{esc(project.get("repo_url"))}" target="_blank" rel="noopener" class="external-repo-link">{esc(project.get("repo_url"))} &nearr;</a></div>' if project.get("repo_url") else ''}
          {f'<div><span class="dim tiny mono">DEPLOYMENT DEMO</span><br><a href="{esc(project.get("demo_url"))}" target="_blank" rel="noopener" class="external-repo-link">{esc(project.get("demo_url"))} &nearr;</a></div>' if project.get("demo_url") else ''}
          {"" if (project.get("repo_url") or project.get("demo_url")) else '<span class="tiny dim">No external links registered.</span>'}
        </div>
      </div>
    </aside>
  </div>
</div>"""


def results_leaderboard(*, event: dict, ranked: list[dict],
                        is_published: bool, user_role: str | None) -> str:
    """Render the official competition scoreboard with authoritative presentation."""
    if not is_published and user_role not in ("organizer", "admin"):
        return f"""<div class="panel panel--embargo">
  <div class="stamp stamp--embargo">EMBARGOED STANDINGS</div>
  <h2>Official Results Pending</h2>
  <p class="lede">Final consensus scores and awards are scheduled for release at:<br>
     <strong class="cyan-val">{ui.format_iso(event.get("results_publish_at"))}</strong></p>
  <p class="dim tiny footnote-text">Evaluations are currently undergoing judge normalization.</p>
</div>"""

    embargo_warning = ""
    if not is_published:
        embargo_warning = ui.callout(
            "These results are currently embargoed from participants and the public. "
            "You are viewing them under organizer clearance.",
            title="Pre-Publication Embargo Preview", variant="warn")

    # Podium cards for top 3
    podium_markup = ""
    if ranked and len(ranked) >= 3:
        p1, p2, p3 = ranked[0], ranked[1], ranked[2]
        podium_markup = f"""<div class="grid grid--3 podium-grid">
  <div class="card card--podium card--silver">
    <div class="spread">
      <span class="chip chip--silver">🥈 2ND PLACE</span>
      <span class="mono tiny dim">SCORE: {ui.format_score(p2.get('normalized_mean'))}</span>
    </div>
    <h3 class="podium-title"><a href="/gallery/{esc(p2.get('project_id'))}">{esc(p2.get('title'))}</a></h3>
    <div class="tiny dim">Team: {esc(p2.get('team_name'))}</div>
  </div>

  <div class="card card--podium card--gold">
    <div class="spread">
      <span class="chip chip--gold">🥇 1ST PLACE WINNER</span>
      <span class="mono tiny font-bold cyan-val">SCORE: {ui.format_score(p1.get('normalized_mean'))}</span>
    </div>
    <h3 class="podium-title podium-title--gold"><a href="/gallery/{esc(p1.get('project_id'))}">{esc(p1.get('title'))}</a></h3>
    <div class="tiny dim">Team: {esc(p1.get('team_name'))}</div>
  </div>

  <div class="card card--podium card--bronze">
    <div class="spread">
      <span class="chip chip--bronze">🥉 3RD PLACE</span>
      <span class="mono tiny dim">SCORE: {ui.format_score(p3.get('normalized_mean'))}</span>
    </div>
    <h3 class="podium-title"><a href="/gallery/{esc(p3.get('project_id'))}">{esc(p3.get('title'))}</a></h3>
    <div class="tiny dim">Team: {esc(p3.get('team_name'))}</div>
  </div>
</div>"""

    rows = []
    for r in ranked:
        rank_num = r.get("published_rank") or "—"
        medal = ""
        tr_cls = ""
        if rank_num == 1:
            medal = " 🥇"
            tr_cls = ' class="rank-1"'
        elif rank_num == 2:
            medal = " 🥈"
            tr_cls = ' class="rank-2"'
        elif rank_num == 3:
            medal = " 🥉"
            tr_cls = ' class="rank-3"'

        flags = " ".join(f'<span class="badge badge--draft">{esc(f)}</span>' for f in r.get("flags", []))
        rows.append(f"""<tr{tr_cls}>
  <td class="num font-bold rank-cell"><strong>{rank_num}{medal}</strong></td>
  <td>
    <a href="/gallery/{esc(r.get('project_id'))}" class="project-title-link">{esc(r.get('title'))}</a>
    <div class="tiny dim">{esc(r.get('team_name'))} &middot; {esc(r.get('track') or 'General')}</div>
  </td>
  <td class="num">{ui.format_score(r.get('raw_mean'))}</td>
  <td class="num score-final">{ui.format_score(r.get('normalized_mean'))}</td>
  <td class="num">{r.get('review_count', 0)}</td>
  <td>{flags}</td>
</tr>""")

    tbody = "".join(rows) if rows else '<tr><td colspan="6" class="center dim empty-cell">No completed evaluations recorded yet.</td></tr>'

    return f"""<div class="stack stack--lg">
  {embargo_warning}
  <header>
    <div class="kicker">OFFICIAL COMPETITION LEDGER</div>
    <h1 class="headline--xl">{esc(event.get("name"))} — Final Standings</h1>
    <p class="lede">Z-score normalized consensus across judging panels. Scores standardized to 0–100 scale.</p>
  </header>

  {podium_markup}

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th class="num rank-header">Rank</th>
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
    """Render the email/password login form with dark tech styling."""
    return f"""<div class="panel auth-panel">
  <div class="panel__head">
    <h2>Sign In</h2>
    <span class="chip chip--solid">Authentication</span>
  </div>
  <div class="panel__body">
    <form method="POST" action="/signin" class="form-stack">
      <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
      <input type="hidden" name="next" value="{esc(next_url)}">

      <div class="field">
        <label for="email">Email Address</label>
        <input type="email" id="email" name="email" required autofocus class="input" placeholder="you@domain.com">
      </div>

      <div class="field">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" required class="input" placeholder="••••••••">
      </div>

      <button type="submit" class="btn btn--block u-mt-10">Sign In to Lockdown</button>
    </form>
    <div class="tiny dim u-mt-18 center u-pt-14 u-rule-top">
      Demo organizer account: <code>organizer@dogfood.test</code><br>
      Password: <code>dogfood-demo-2026</code>
    </div>
  </div>
</div>"""
