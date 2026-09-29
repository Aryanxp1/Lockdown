"""Public event views: the hackathon directory, one hackathon, and results."""

from __future__ import annotations

from . import ui
from .ui import esc


def event_directory(events: list[dict], *, title: str = "Hackathons",
                    kicker: str = "COMPETITION ARCHIVE", lede: str = "",
                    empty_action: str = "") -> str:
    """Every published hackathon, each introduced by a modern visual card."""
    if not events:
        return ui.empty_state(
            "No hackathons published yet",
            "An organizer has to publish an event before it appears in the public index.",
            action_label="Sign in as an organizer" if empty_action else "",
            action_href=empty_action)
    cards = []
    for item in events:
        event, metrics = item["event"], item.get("metrics") or {}
        cards.append(ui.event_card(
            event, counts=metrics,
            status_label=_status_label(event, metrics),
            status_variant=_status_variant(event, metrics),
            links=[("Gallery", "/events/%s/gallery" % event["slug"]),
                   ("Results", "/events/%s/results" % event["slug"])]))
    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker">{esc(kicker)}</div>
    <h1 class="headline--xl">{esc(title)}</h1>
    <p class="lede">{esc(lede or "Explore active and upcoming competitions, track deadlines, inspect team submissions and review official scored standings.")}</p>
  </header>
  <div class="grid grid--2">{''.join(cards)}</div>
</div>"""


def _status_label(event: dict, metrics: dict) -> str:
    if event.get("status") == "draft":
        return "Draft"
    if metrics.get("results_published"):
        return "Published"
    return metrics.get("stage") or event.get("status", "published")


def _status_variant(event: dict, metrics: dict) -> str:
    if event.get("status") == "draft":
        return "draft"
    if metrics.get("results_published"):
        return "submitted"
    return "open"


def results_directory(events: list[dict], *, user_role: str | None = None) -> str:
    """`/results` is an index first: pick a competition, then read its official standings."""
    if not events:
        return ui.empty_state("No results available",
                              "No hackathon results have been officially published on this portal.")
    cards = []
    for item in events:
        event, metrics = item["event"], item.get("metrics") or {}
        if metrics.get("results_published"):
            action, label, variant = "View Results", "Published", "submitted"
        elif user_role in ("organizer", "admin"):
            action, label, variant = "Preview Standings", "In progress", "open"
        else:
            action, label, variant = "View Hackathon", "In progress", "draft"
        cards.append(ui.event_card(
            event, counts=metrics, action_label=action,
            action_href="/events/%s/results" % event["slug"],
            status_label=label, status_variant=variant))
    return f"""<div class="stack stack--lg">
  <header>
    <div class="kicker">OFFICIAL COMPETITION RECORDS</div>
    <h1 class="headline--xl">Results Directory</h1>
    <p class="lede">Standings are verified and published per hackathon. Select an event to inspect its official normalized leaderboard.</p>
  </header>
  <div class="grid grid--2">{''.join(cards)}</div>
  <p class="tiny dim footnote-text">Competitions without an immutable revision have no public standings yet. Organizers can preview live consensus numbers from inside their management console.</p>
</div>"""


def results_scope_note(*, event: dict, publication: dict | None) -> str:
    """The line that keeps a standings table honest about which event it is."""
    revision = (publication or {}).get("revision_no")
    stamp = ui.format_iso((publication or {}).get("published_at")) if publication else ""
    detail = ("Published revision %s on %s" % (revision, stamp)) if publication \
        else "Not published yet"
    return (f'<div class="callout callout--context"><p class="mono tiny dim">Competition Context: <strong class="cyan-val">{esc(event["name"])}</strong> &middot; <span class="ink-val">{esc(detail)}</span></p></div>')


def event_page(*, event: dict, metrics: dict, stages: list[dict], timeline_rows: list[dict],
               tracks: list[dict], prizes: list[dict], can_manage: bool = False,
               gallery_visible: bool = True, results_visible: bool = True,
               gallery_count: int = 0) -> str:
    """One hackathon's own cover page: identity, stage, dates, tracks, prizes."""
    stage_block = ui.stage_rail(stages, metrics.get("stage_key", "")) if stages else ""
    track_rows = "".join(
        '<li class="track"><span class="track__name">%s</span>'
        '<span class="track__desc tiny dim">%s</span></li>'
        % (esc(row["name"]), esc(row["description"] or "Open track focus"))
        for row in tracks) or '<li class="dim tiny">No tracks configured yet.</li>'
    prize_rows = "".join(
        '<li class="prize"><div class="spread"><span class="prize__rank mono">#%s</span>'
        '<span class="prize__title">%s</span>'
        '<span class="prize__value tiny mono cyan-val font-bold">%s</span></div>'
        '<div class="tiny dim prize-desc">%s</div></li>'
        % (esc(row["rank"]), esc(row["title"]),
           esc(row.get("value") or ""), esc(row.get("description") or ""))
        for row in prizes) or '<li class="dim tiny">No prizes announced yet.</li>'

    actions = []
    if gallery_visible:
        actions.append('<a class="btn" href="/events/%s/gallery">Project Gallery (%d) &rarr;</a>'
                       % (esc(event["slug"]), gallery_count))
    if results_visible:
        label = "Official Results" if metrics.get("results_published") else "Results (Pending)"
        actions.append('<a class="btn btn--ghost" href="/events/%s/results">%s</a>'
                       % (esc(event["slug"]), label))
    if can_manage:
        actions.append('<a class="btn btn--ghost" href="/organizer/events/%s">Manage Event</a>'
                       % esc(event["id"]))

    registration = ("Registration is open" if metrics.get("stage_key") == "registration"
                    else "Stage: %s" % (metrics.get("stage") or "In Progress"))
    if metrics.get("results_published"):
        results_line = "Published, Revision %d" % metrics.get("results_revision", 0)
    else:
        results_line = "Results Pending Release"

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("Hackathons", "/events"), (event["name"], "")])}
  <header class="event-hero">
    {ui.event_cover(event)}
    <div class="event-hero__body">
      <div class="spread hero-spread">
        <div class="kicker">{esc(metrics.get("stage") or event.get("status", "HACKATHON"))}</div>
        {ui.badge(event.get("status", "published"), "open" if event.get("status") == "published" else "default")}
      </div>
      <h1 class="headline--xl">{esc(event["name"])}</h1>
      <p class="lede">{esc(event.get("tagline") or "")}</p>
      <div class="event-card__meta event-hero-meta">
        <span class="chip chip--solid">{esc(event.get("location") or "Global / Online")}</span>
        <span class="chip">{esc(registration)}</span>
        <span class="chip">{metrics.get("teams", 0)} Teams</span>
        <span class="chip">{metrics.get("projects", 0)} Projects</span>
        <span class="chip">{metrics.get("tracks", 0)} Tracks</span>
      </div>
      <div class="cluster hero-actions-cluster">{''.join(actions)}</div>
    </div>
  </header>

  <div class="grid grid--sidebar">
    <div class="stack">
      <section class="panel">
        <div class="panel__head"><h3>About this Hackathon</h3></div>
        <div class="panel__body">
          <div class="prose-description">
            {esc(event.get("description") or "No description has been written yet.")}
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Competition Rules</h3></div>
        <div class="panel__body">
          <div class="prose-description">
            {esc(event.get("rules") or "Standard competition guidelines apply.")}
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Tracks &amp; Focus Areas</h3></div>
        <div class="panel__body"><ul class="plain-list">{track_rows}</ul></div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Prizes &amp; Awards</h3></div>
        <div class="panel__body"><ul class="plain-list">{prize_rows}</ul></div>
      </section>
    </div>

    <aside class="stack">
      <div class="panel">
        <div class="panel__head"><h3>Competition Stage</h3></div>
        <div class="panel__body">
          {stage_block or '<p class="tiny dim">No stages configured.</p>'}
        </div>
      </div>
      <div class="panel">
        <div class="panel__head"><h3>Schedule &amp; Deadlines</h3></div>
        <div class="panel__body">{ui.timeline(timeline_rows)}</div>
      </div>
      <div class="panel">
        <div class="panel__head"><h3>Evaluation Progress</h3></div>
        <div class="panel__body stack tiny mono">
          <div><span class="dim">Reviews Completed</span><br>
               <strong class="cyan-val font-lg">{metrics.get("reviews_submitted", 0)}</strong> of
               {metrics.get("judging_total", 0)} assigned</div>
          <div><span class="dim">Results Status</span><br><strong class="ink-val">{esc(results_line)}</strong></div>
        </div>
      </div>
    </aside>
  </div>
</div>"""
