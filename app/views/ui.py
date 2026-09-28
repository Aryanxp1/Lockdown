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
