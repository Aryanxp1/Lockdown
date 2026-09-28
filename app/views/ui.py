"""Editorial UI component primitives for Lockdown.

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
    """Render a newsprint-style rubber stamp."""
    return f'<span class="stamp">{esc(text)}</span>'


def button(label: str, *, href: str | None = None, variant: str = "default",
           size: str = "default", type_: str = "submit",
           name: str | None = None, value: str | None = None,
           confirm: str | None = None, block: bool = False) -> str:
    """Render a styled button or anchor styled as a button."""
    classes = ["btn"]
    if variant in ("ghost", "danger"):
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
    """Render an editorial callout box."""
    cls = f"callout callout--{variant}" if variant != "default" else "callout"
    head = f"<h4>{esc(title)}</h4>" if title else ""
    return f'<div class="{cls}">{head}<p>{content}</p></div>'


def empty_state(title: str, body: str = "", *, action_label: str = "",
                action_href: str = "") -> str:
    """Render an empty state placeholder."""
    action = f'<p><a href="{esc(action_href)}" class="btn btn--sm">{esc(action_label)}</a></p>' if action_href else ""
    body_p = f'<p class="empty__body">{esc(body)}</p>' if body else ""
    return f"""<div class="empty">
  <h3 class="empty__title">{esc(title)}</h3>
  {body_p}
  {action}
</div>"""


def stat_card(label: str, value: Any, *, red: bool = False,
              hint: str = "") -> str:
    """Render a single high-impact metric."""
    cls = "stat stat--red" if red else "stat"
    hint_span = f'<div class="tiny dim">{esc(hint)}</div>' if hint else ""
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
        if is_cur:
            cls += " rail__step--current"
        elif is_past:
            cls += " rail__step--past"
        else:
            cls += " rail__step--future"
        steps.append(f"""<div class="{cls}">
  <span class="rail__num">Stage {idx}</span>
  <span class="rail__label">{esc(stage.get("name", ""))}</span>
  <span class="rail__dates">{esc(stage.get("date_range", ""))}</span>
</div>""")
    return f'<div class="rail">{"".join(steps)}</div>'


def progress_bar(value: int, total: int, *, red: bool = False,
                 label: str = "") -> str:
    """Render an accessible progress bar."""
    pct = 0 if total <= 0 else min(100, max(0, round(value * 100 / total)))
    cls = "bar bar--red" if red else "bar"
    label_markup = (f'<div class="spread tiny dim"><span>{esc(label)}</span>'
                    f'<span>{value}/{total} ({pct}%)</span></div>') if label else ""
    return f"""<div class="stack" style="gap:4px">
  {label_markup}
  <div class="{cls}" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">
    <div class="bar__fill" style="width: {pct}%"></div>
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
        return ""
    return dt_str.replace("T", " ").replace("Z", "")[:16]


def format_score(score: float | int | None) -> str:
    """Format scores cleanly: 84.5 -> "84.50", None -> "-"."""
    if score is None:
        return "—"
    try:
        return f"{float(score):.2f}"
    except (ValueError, TypeError):
        return "—"


# --- event context ------------------------------------------------------
#
# Every event-scoped page wears the same breadcrumb and every hackathon is
# introduced by the same card, so browsing the archive looks the same wherever
# a visitor arrives from.

TONE_LABELS = {
    "ink": "Archive",
    "red": "Flagship",
    "blue": "Live",
    "green": "Community",
    "amber": "Seasonal",
}


def event_cover(event: dict) -> str:
    """The letterpress cover band: a glyph, a tone, and what kind of event it is."""
    glyph = (event.get("banner") or "").strip()[:4]
    if not glyph:
        glyph = "".join(part[0] for part in (event.get("name") or "?").split()[:2]).upper()
    tone = (event.get("cover_tone") or "ink").strip().lower()
    if tone not in TONE_LABELS:
        tone = "ink"
    return (f'<div class="cover cover--{tone}" aria-hidden="true">'
            f'<span class="cover__glyph mono">{esc(glyph)}</span>'
            f'<span class="cover__tone mono">{esc(TONE_LABELS[tone])}</span>'
            f"</div>")


def event_card(event: dict, *, counts: dict | None = None, blurb: str = "",
               action_label: str = "View Hackathon", action_href: str = "",
               status_label: str = "", status_variant: str = "default",
               links: list | None = None) -> str:
    """One hackathon in the archive: cover, identity, numbers, one clear way in."""
    counts = counts or {}
    blurb = blurb or event.get("tagline") or (event.get("description") or "")[:150]
    if len(blurb) > 170:
        blurb = blurb[:167].rstrip() + "\u2026"
    href = action_href or "/events/%s" % esc(event.get("slug"))
    metrics = []
    if counts.get("projects") is not None:
        metrics.append("%s projects" % counts["projects"])
    if counts.get("teams") is not None:
        metrics.append("%s teams" % counts["teams"])
    if counts.get("tracks") is not None:
        metrics.append("%s tracks" % counts["tracks"])
    meta = " \u00b7 ".join(str(item) for item in metrics)
    stage = counts.get("stage")
    closes = (event.get("submissions_close") or event.get("results_publish_at") or "")[:10]
    extra_links = "".join(
        '<a class="btn btn--sm btn--ghost" href="%s">%s</a>' % (esc(link_href), esc(link_label))
        for link_label, link_href in (links or []))
    stage_markup = ('<span>Stage: %s</span>' % esc(stage)) if stage else ""
    close_markup = ('<span>Closes %s</span>' % esc(closes)) if closes else ""
    return f"""<article class="event-card">
  {event_cover(event)}
  <div class="event-card__body">
    <div class="spread">
      <h3 class="event-card__title"><a href="{href}">{esc(event.get("name"))}</a></h3>
      {badge(status_label or event.get("status", "draft"), status_variant)}
    </div>
    <p class="event-card__blurb">{esc(blurb)}</p>
    <div class="event-card__meta tiny mono dim">
      <span>{meta}</span>
      {stage_markup}
      {close_markup}
    </div>
    <div class="event-card__foot">
      <a class="btn btn--sm" href="{href}">{esc(action_label)} &rarr;</a>
      {extra_links}
    </div>
  </div>
</article>"""


def breadcrumb(trail: list) -> str:
    """`LOCKDOWN / SAMPLE HACK 2026 / RESULTS`. The last item is the current page."""
    if not trail:
        return ""
    parts = []
    for index, (label, href) in enumerate(trail):
        is_last = index == len(trail) - 1
        if is_last or not href:
            parts.append('<span class="crumb crumb--here" aria-current="page">%s</span>'
                         % esc(label))
        else:
            parts.append('<a class="crumb" href="%s">%s</a>' % (esc(href), esc(label)))
    return ('<nav class="crumbs mono" aria-label="Breadcrumb">%s</nav>' % "".join(parts))


def timeline(rows: list) -> str:
    """A dated list of the things an entrant needs to know, in order."""
    if not rows:
        return ""
    items = []
    for row in rows:
        state = row.get("state", "")
        css = {"open": "is-open", "past": "is-past", "closed": "is-past"}.get(state, "is-next")
        items.append("""<li class="timeline__item %s">
  <span class="timeline__when mono">%s</span>
  <span class="timeline__label">%s</span>
  <span class="timeline__state tiny mono">%s</span>
</li>""" % (css, esc((row.get("at") or "")[:10] or "--"), esc(row.get("label", "")),
            esc(row.get("state_label") or state)))
    return '<ol class="timeline">%s</ol>' % "".join(items)


def spec_list(pairs: list) -> str:
    """A two-column spec table: label on the left, value on the right."""
    rows = "".join(
        '<div class="spec"><dt class="tiny mono dim">%s</dt><dd>%s</dd></div>'
        % (esc(label), value) for label, value in pairs)
    return '<dl class="spec-list">%s</dl>' % rows

