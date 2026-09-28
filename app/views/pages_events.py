"""Public event views: the hackathon directory, one hackathon, and results.

Three pages, one idea: a Lockdown install is an archive of competitions. The
directory lists what is on the shelf, the event page is one competition's own
cover, and the results directory is the same shelf with the standings unlocked.
Nothing here decides what a visitor may see -- the handlers filter the rows
before they arrive.
"""

from __future__ import annotations

from . import ui
from .ui import esc


def event_directory(events: list[dict], *, title: str = "Hackathons",
                    kicker: str = "The Lockdown Archive", lede: str = "",
                    empty_action: str = "") -> str:
    """Every published hackathon, each introduced by its own card."""
    if not events:
        return ui.empty_state(
            "No hackathons published yet",
            "An organizer has to publish one before it appears here.",
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
    <div class="kicker kicker--red">{esc(kicker)}</div>
    <h1 class="headline--xl">{esc(title)}</h1>
    <p class="lede">{esc(lede or "Every hackathon hosted on this install, with its own "
                                 "teams, judging and results.")}</p>
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
    """`/results` is an index first: pick a competition, then read its ledger."""
    if not events:
        return ui.empty_state("No results yet",
                              "No hackathon has been published on this install.")
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
    <div class="kicker kicker--red">Official Ledger</div>
    <h1 class="headline--xl">Results</h1>
    <p class="lede">Standings are published per hackathon. Pick a competition to read its
      final table.</p>
  </header>
  <div class="grid grid--2">{''.join(cards)}</div>
  <p class="tiny dim">A hackathon with no published revision has no standings yet.
    Organizers can still preview its live numbers from inside the event.</p>
</div>"""


def results_scope_note(*, event: dict, publication: dict | None) -> str:
    """The line that keeps a standings table honest about which event it is."""
    revision = (publication or {}).get("revision_no")
    stamp = ui.format_iso((publication or {}).get("published_at")) if publication else ""
    detail = ("Published revision %s on %s" % (revision, stamp)) if publication \
        else "Not published yet"
    return ('<p class="mono tiny dim">Event: <strong>%s</strong> &middot; %s</p>'
            % (esc(event["name"]), esc(detail)))



def event_page(*, event: dict, metrics: dict, stages: list[dict], timeline_rows: list[dict],
               tracks: list[dict], prizes: list[dict], can_manage: bool = False,
               gallery_visible: bool = True, results_visible: bool = True,
               gallery_count: int = 0) -> str:
    """One hackathon's own cover page: identity, stage, dates, tracks, prizes."""
    stage_block = ui.stage_rail(stages, metrics.get("stage_key", "")) if stages else ""
    track_rows = "".join(
        '<li class="track"><span class="track__name">%s</span>'
        '<span class="track__desc tiny dim">%s</span></li>'
        % (esc(row["name"]), esc(row["description"] or ""))
        for row in tracks) or '<li class="dim tiny">No tracks configured yet.</li>'
    prize_rows = "".join(
        '<li class="prize"><span class="prize__rank mono">#%s</span>'
        '<span class="prize__title">%s</span>'
        '<span class="prize__value tiny dim">%s</span></li>'
        % (esc(row["rank"]), esc(row["title"]),
           esc(row["value"] or row["description"] or ""))
        for row in prizes) or '<li class="dim tiny">No prizes announced yet.</li>'

    actions = []
    if gallery_visible:
        actions.append('<a class="btn" href="/events/%s/gallery">Gallery (%d projects)</a>'
                       % (esc(event["slug"]), gallery_count))
    if results_visible:
        label = "Results" if metrics.get("results_published") else "Results (pending)"
        actions.append('<a class="btn btn--ghost" href="/events/%s/results">%s</a>'
                       % (esc(event["slug"]), label))
    if can_manage:
        actions.append('<a class="btn btn--ghost" href="/organizer/events/%s">Manage</a>'
                       % esc(event["id"]))

    registration = ("Registration is open" if metrics.get("stage_key") == "registration"
                    else "Registration status: %s" % (metrics.get("stage") or "unset"))
    if metrics.get("results_published"):
        results_line = "Published, revision %d" % metrics.get("results_revision", 0)
    else:
        results_line = "Not published yet"

    return f"""<div class="stack stack--lg">
  {ui.breadcrumb([("Lockdown", "/"), ("Hackathons", "/events"), (event["name"], "")])}
  <header class="event-hero">
    {ui.event_cover(event)}
    <div class="event-hero__body">
      <div class="kicker kicker--red">{esc(metrics.get("stage") or event.get("status", ""))}</div>
      <h1 class="headline--xl">{esc(event["name"])}</h1>
      <p class="lede">{esc(event.get("tagline") or "")}</p>
      <div class="cluster cluster--loose tiny mono dim">
        <span>{esc(event.get("location") or "Online")}</span>
        <span>{esc(registration)}</span>
        <span>{metrics.get("teams", 0)} teams</span>
        <span>{metrics.get("projects", 0)} projects</span>
        <span>{metrics.get("tracks", 0)} tracks</span>
      </div>
      <div class="cluster" style="margin-top:14px">{''.join(actions)}</div>
    </div>
  </header>

  <div class="grid grid--sidebar">
    <div class="stack">
      <section class="panel">
        <div class="panel__head"><h3>About this hackathon</h3></div>
        <div class="panel__body">
          <div style="white-space:pre-wrap;line-height:1.6">
            {esc(event.get("description") or "No description has been written yet.")}
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Rules</h3></div>
        <div class="panel__body">
          <div style="white-space:pre-wrap;line-height:1.6">
            {esc(event.get("rules") or "No additional rules were published.")}
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Tracks</h3></div>
        <div class="panel__body"><ul class="plain-list">{track_rows}</ul></div>
      </section>

      <section class="panel">
        <div class="panel__head"><h3>Prizes</h3></div>
        <div class="panel__body"><ul class="plain-list">{prize_rows}</ul></div>
      </section>
    </div>

    <aside class="stack">
      <div class="panel">
        <div class="panel__head"><h3>Stage</h3></div>
        <div class="panel__body">
          {stage_block or '<p class="tiny dim">No stages configured.</p>'}
        </div>
      </div>
      <div class="panel">
        <div class="panel__head"><h3>Key dates</h3></div>
        <div class="panel__body">{ui.timeline(timeline_rows)}</div>
      </div>
      <div class="panel">
        <div class="panel__head"><h3>Judging</h3></div>
        <div class="panel__body stack tiny mono">
          <div><span class="dim">Reviews completed</span><br>
               <strong>{metrics.get("reviews_submitted", 0)}</strong> of
               {metrics.get("judging_total", 0)} handed out</div>
          <div><span class="dim">Results</span><br><strong>{esc(results_line)}</strong></div>
        </div>
      </div>
    </aside>
  </div>
</div>"""
