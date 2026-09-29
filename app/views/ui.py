"""Modern UI component primitives for Lockdown.

Every helper produces safe, well-formed HTML without external template engines.
"""

from __future__ import annotations

import html
from typing import Any


def esc(value: Any) -> str:
    """HTML-escape a value, converting None to an empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def attr(name: str, value: Any) -> str:
    """Render an HTML attribute if value is truthy, empty string otherwise."""
    if value is None or value is False:
        return ""
    if value is True:
        return f" {name}"
    return f' {name}="{esc(value)}"'


def badge(label: str, variant: str = "default") -> str:
    """Render a status badge: open, closed, upcoming, published, draft, submitted."""
    cls = f"badge badge--{variant}" if variant != "default" else "badge"
    return f'<span class="{cls}">{esc(label)}</span>'


def chip(label: str, *, red: bool = False, solid: bool = False,
         soft: bool = False) -> str:
    """Render a meta chip."""
    classes = ["chip"]
    if red:
        classes.append("chip--red")
    if solid:
        classes.append("chip--solid")
    if soft:
        classes.append("chip--soft")
    return f'<span class="{" ".join(classes)}">{esc(label)}</span>'


def stamp(text: str) -> str:
    """Render a high-tech classified/status stamp."""
    return f'<span class="stamp">{esc(text)}</span>'


def button(label: str, *, href: str | None = None, variant: str = "default",
           size: str = "default", type_: str = "submit",
           name: str | None = None, value: str | None = None,
           confirm: str | None = None, block: bool = False) -> str:
    """Render a styled button or anchor styled as a button."""
    classes = ["btn"]
    if variant in ("ghost", "danger", "primary"):
        classes.append(f"btn--{variant}")
    if size == "sm":
        classes.append("btn--sm")
    if block:
        classes.append("btn--block")
    cls_attr = f'class="{" ".join(classes)}"'
    conf_attr = f' data-confirm="{esc(confirm)}"' if confirm else ""

    if href:
        return f'<a href="{esc(href)}" {cls_attr}{conf_attr}>{esc(label)}</a>'

    name_attr = f' name="{esc(name)}"' if name else ""
    val_attr = f' value="{esc(value)}"' if value is not None else ""
    return f'<button type="{esc(type_)}"{name_attr}{val_attr} {cls_attr}{conf_attr}>{esc(label)}</button>'


def callout(content: str, *, title: str | None = None,
            variant: str = "default") -> str:
    """Render an informative callout box."""
    cls = f"callout callout--{variant}" if variant != "default" else "callout"
    head = f"<h4>{esc(title)}</h4>" if title else ""
    return f'<div class="{cls}">{head}<p>{content}</p></div>'


def empty_state(title: str, body: str = "", *, action_label: str = "",
                action_href: str = "") -> str:
    """Render an empty state placeholder."""
    action = f'<p class="u-mt-16"><a href="{esc(action_href)}" class="btn btn--sm btn--primary">{esc(action_label)} &rarr;</a></p>' if action_href else ""
    body_p = f'<p class="empty__body">{esc(body)}</p>' if body else ""
    return f"""<div class="empty">
  <div class="u-fs-16 u-mb-10 u-text-ink-3" aria-hidden="true">&#9671;</div>
  <h3 class="empty__title">{esc(title)}</h3>
  {body_p}
  {action}
</div>"""


def stat_card(label: str, value: Any, *, red: bool = False,
              hint: str = "") -> str:
    """Render a single high-impact metric tile with crisp typographic hierarchy."""
    cls = "stat stat--red" if red else "stat"
    hint_span = f'<div class="stat__hint">{esc(hint)}</div>' if hint else ""
    return f"""<div class="{cls}">
  <div class="stat__value">{esc(value)}</div>
  <div class="stat__label">{esc(label)}</div>
  {hint_span}
</div>"""


def stage_rail(stages: list[dict], current_code: str = "") -> str:
    """Render a horizontal timeline of competition stages."""
    steps = []
    for idx, stage in enumerate(stages, start=1):
        is_cur = stage.get("code") == current_code or stage.get("is_current")
        is_past = stage.get("is_past")
        cls = "rail__step"
        status_symbol = ""
        if is_cur:
            cls += " rail__step--current"
            status_symbol = ' <span class="rail__indicator">&bull; Active</span>'
        elif is_past:
            cls += " rail__step--past"
            status_symbol = ' <span class="rail__indicator rail__indicator--done">&#10003;</span>'
        else:
            cls += " rail__step--future"

        steps.append(f"""<div class="{cls}">
  <span class="rail__num">Stage {idx}{status_symbol}</span>
  <span class="rail__label">{esc(stage.get("name", ""))}</span>
  <span class="rail__dates">{esc(stage.get("date_range", ""))}</span>
</div>""")
    return f'<div class="rail">{"".join(steps)}</div>'


def progress_bar(value: int, total: int, *, red: bool = False,
                 label: str = "") -> str:
    """Render an accessible progress bar."""
    pct = 0 if total <= 0 else min(100, max(0, round(value * 100 / total)))
    cls = "bar bar--red" if red else "bar"
    label_markup = (f'<div class="spread tiny dim u-mb-4"><span>{esc(label)}</span>'
                    f'<span class="mono u-text-ink">{value}/{total} ({pct}%)</span></div>') if label else ""
    return f"""<div class="stack u-gap-2">
  {label_markup}
  <div class="{cls}" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100"
       data-bar-pct="{pct}">
    <div class="bar__fill" data-bar-pct="{pct}"></div>
  </div>
</div>"""


def pager(current: int, total_pages: int, url_fn) -> str:
    """Render pagination controls."""
    if total_pages <= 1:
        return ""
    items = []
    if current > 1:
        items.append(f'<a href="{esc(url_fn(current - 1))}" aria-label="Previous">&larr;</a>')
    for p in range(1, total_pages + 1):
        if p == current:
            items.append(f'<span aria-current="page">{p}</span>')
        elif p == 1 or p == total_pages or abs(p - current) <= 2:
            items.append(f'<a href="{esc(url_fn(p))}">{p}</a>')
        elif items and not items[-1].endswith('ellipsis">…</span>'):
            items.append('<span class="pager__ellipsis">…</span>')
    if current < total_pages:
        items.append(f'<a href="{esc(url_fn(current + 1))}" aria-label="Next">&rarr;</a>')
    return f'<nav class="pager" aria-label="Pagination">{"".join(items)}</nav>'


def format_iso(dt_str: str | None) -> str:
    """Clean ISO timestamp for display."""
    if not dt_str:
        return "—"
    return dt_str.replace("T", " ").replace("Z", "")[:16]


def format_score(score: float | int | None) -> str:
    """Format scores cleanly: 84.5 -> "84.50", None -> "-"."""
    if score is None:
        return "—"
    try:
        return f"{float(score):.2f}"
    except (ValueError, TypeError):
        return "—"


# --- Deterministic Visual Generation ---------------------------------------

TONE_LABELS = {
    "ink": "Flagship",
    "red": "High Stakes",
    "blue": "Open",
    "green": "Sprint",
    "amber": "Invitational",
}


def event_cover(event: dict) -> str:
    """The modern hackathon visual cover: clean architectural header."""
    glyph = (event.get("banner") or "").strip()[:4]
    if not glyph:
        glyph = "".join(part[0] for part in (event.get("name") or "?").split()[:2]).upper()
    tone = (event.get("cover_tone") or "blue").strip().lower()
    if tone not in TONE_LABELS:
        tone = "blue"

    return (f'<div class="cover cover--{tone}" aria-hidden="true">'
            f'<div class="cover__grid"></div>'
            f'<span class="cover__glyph mono">{esc(glyph)}</span>'
            f'<span class="cover__tone mono">{esc(TONE_LABELS[tone])}</span>'
            f"</div>")


def event_card(event: dict, *, counts: dict | None = None, blurb: str = "",
               action_label: str = "Explore Hackathon", action_href: str = "",
               status_label: str = "", status_variant: str = "default",
               links: list | None = None) -> str:
    """Modern hackathon event card: clean typographic hierarchy, metadata strip, and clear CTA."""
    counts = counts or {}
    blurb = blurb or event.get("tagline") or (event.get("description") or "")[:150]
    if len(blurb) > 160:
        blurb = blurb[:157].rstrip() + "…"
    href = action_href or "/events/%s" % esc(event.get("slug"))

    stage = counts.get("stage")
    closes = (event.get("submissions_close") or event.get("results_publish_at") or "")[:10]
    
    projects_cnt = counts.get("projects", 0)
    teams_cnt = counts.get("teams", 0)
    tracks_cnt = counts.get("tracks", 0)

    extra_links = "".join(
        '<a class="btn btn--sm btn--ghost" href="%s">%s</a>' % (esc(link_href), esc(link_label))
        for link_label, link_href in (links or []))

    stage_part = f'<span>Stage: <strong class="cyan-val">{esc(stage)}</strong></span>' if stage else ""
    close_part = f'<span class="dim">Closes {esc(closes)}</span>' if closes else ""

    return f"""<article class="event-card">
  {event_cover(event)}
  <div class="event-card__body">
    <div class="spread">
      <h3 class="event-card__title"><a href="{href}">{esc(event.get("name"))}</a></h3>
      {badge(status_label or event.get("status", "draft"), status_variant)}
    </div>
    <p class="event-card__blurb">{esc(blurb)}</p>
    <div class="event-card__meta">
      <span><strong class="mono ink-val">{projects_cnt}</strong> Projects</span>
      <span class="meta-dot">&middot;</span>
      <span><strong class="mono ink-val">{teams_cnt}</strong> Teams</span>
      <span class="meta-dot">&middot;</span>
      <span><strong class="mono ink-val">{tracks_cnt}</strong> Tracks</span>
      {f'<span class="meta-dot">&middot;</span> {stage_part}' if stage_part else ''}
      {f'<span class="meta-dot">&middot;</span> {close_part}' if close_part else ''}
    </div>
    <div class="event-card__foot">
      <a class="btn btn--sm btn--primary" href="{href}">{esc(action_label)} &rarr;</a>
      <div class="cluster">{extra_links}</div>
    </div>
  </div>
</article>"""


def project_card(p: dict) -> str:
    """Render a modern project card with clean metadata and direct CTA."""
    tags = "".join(f'<span class="meta-tag">{esc(t)}</span>' for t in (p.get("tags") or [])[:3])
    summary = esc(p.get("summary") or p.get("description", ""))
    if len(summary) > 130:
        summary = summary[:127] + "…"
    team_name = esc(p.get("team_name") or "Solo")
    pid = esc(p.get("id"))
    title = esc(p.get("title"))
    track = esc(p.get("track") or "General Track")
    votes = p.get("vote_count", 0)

    return f"""<article class="card card--project">
  <div class="card__header">
    <span class="mono tiny kicker-tight">{track}</span>
    <span class="mono tiny vote-counter">&uarr; {votes}</span>
  </div>
  <h3 class="card__title"><a href="/gallery/{pid}">{title}</a></h3>
  <div class="card__team mono tiny dim">BY {team_name}</div>
  <div class="card__body">{summary}</div>
  <div class="card__foot">
    <div class="cluster">{tags}</div>
    <a href="/gallery/{pid}" class="btn btn--sm btn--ghost">View Project &rarr;</a>
  </div>
</article>"""


def breadcrumb(trail: list) -> str:
    """Render modern breadcrumb trail."""
    if not trail:
        return ""
    parts = []
    for index, (label, href) in enumerate(trail):
        is_last = index == len(trail) - 1
        if is_last or not href:
            parts.append(f'<span class="crumb crumb--here" aria-current="page">{esc(label)}</span>')
        else:
            parts.append(f'<a class="crumb" href="{esc(href)}">{esc(label)}</a>')
    return f'<nav class="crumbs" aria-label="Breadcrumb">{"".join(parts)}</nav>'


def timeline(rows: list) -> str:
    """A modern dated list of competition stages and deadlines."""
    if not rows:
        return ""
    items = []
    for row in rows:
        state = row.get("state", "")
        css = {"open": "is-open", "past": "is-past", "closed": "is-past"}.get(state, "is-next")
        items.append(f"""<li class="timeline__item {css}">
  <span class="timeline__when mono">{esc((row.get("at") or "")[:10] or "--")}</span>
  <span class="timeline__label">{esc(row.get("label", ""))}</span>
  <span class="timeline__state mono tiny">{esc(row.get("state_label") or state)}</span>
</li>""")
    return f'<ol class="timeline">{"".join(items)}</ol>'


def spec_list(pairs: list) -> str:
    """A two-column spec table: label on the left, value on the right."""
    rows = "".join(
        f'<div class="spec"><dt class="tiny mono dim">{esc(label)}</dt><dd class="spec__val">{value}</dd></div>'
        for label, value in pairs)
    return f'<dl class="spec-list">{rows}</dl>'
