"""Layout shell and base navigation for Lockdown."""

from __future__ import annotations

from typing import Any

from .ui import esc


def render_shell(*, title: str, content: str, user: dict | None = None,
                 current_path: str = "", csrf_token: str = "",
                 notice: str | None = None, error: str | None = None,
                 event: dict | None = None) -> str:
    """Render the full HTML5 shell."""
    role = user.get("role") if user else None
    nav_links = _nav_links(role, current_path)

    notice_markup = f'<div class="notice notice--success">{esc(notice)}</div>' if notice else ""
    error_markup = f'<div class="notice notice--error">{esc(error)}</div>' if error else ""

    # User badge in masthead
    if user:
        user_info = (f'<span>{esc(user.get("name", user.get("email")))}</span>'
                     f'<span class="chip chip--solid">{esc(role)}</span>')
    else:
        user_info = '<a href="/signin">Sign In</a>'

    event_sub = f' · {esc(event["name"])}' if event else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} — Lockdown</title>
  <link rel="stylesheet" href="/static/app.css">
  <script defer src="/static/app.js"></script>
</head>
<body>
  <a href="#main" class="skip">Skip to main content</a>
  <div class="shell">
    <header class="masthead" role="banner">
      <div class="masthead__row">
        <div>
          <h1 class="masthead__title"><a href="/">Lockdown</a></h1>
          <div class="masthead__tagline">The Competition Record{event_sub}</div>
        </div>
        <div class="masthead__meta">
          <span class="mono">STATUS: LOCAL/OFFLINE</span>
          {user_info}
        </div>
      </div>
    </header>

    <nav class="nav" role="navigation" aria-label="Main Navigation">
      {nav_links}
      <div class="nav__spacer"></div>
      {_auth_links(user, csrf_token)}
    </nav>

    {notice_markup}
    {error_markup}

    <main id="main" class="main" role="main">
      {content}
    </main>

    <footer class="footer" role="contentinfo">
      <div>Lockdown · Zero-dependency offline competition harness</div>
      <div class="mono">VER: 2026.09 · ALL DATA LOCAL</div>
    </footer>
  </div>
</body>
</html>"""


def _nav_links(role: str | None, current_path: str) -> str:
    links = [("/", "Home"), ("/gallery", "Gallery"), ("/results", "Results")]
    if role in ("organizer", "admin"):
        links.extend([
            ("/organizer", "Command Center"),
            ("/organizer/submissions", "Submissions"),
            ("/organizer/judges", "Judges"),
            ("/organizer/audit", "Audit Log"),
        ])
    elif role == "judge":
        links.extend([
            ("/judge", "Evaluation Queue"),
        ])
    elif role == "participant":
        links.extend([
            ("/participant", "My Project"),
        ])

    parts = []
    for href, label in links:
        is_cur = current_path == href or (href != "/" and current_path.startswith(href))
        cur_attr = ' aria-current="page"' if is_cur else ""
        parts.append(f'<a href="{href}"{cur_attr}>{esc(label)}</a>')
    return "\n      ".join(parts)


def _auth_links(user: dict | None, csrf_token: str) -> str:
    if not user:
        return '<a href="/signin" class="nav__cta">Sign In</a>'
    return f"""<form method="POST" action="/signout" class="nav__form">
      <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
      <button type="submit">Sign Out</button>
    </form>"""


def error_page(request_or_status, problem_or_title=None,
               description: str | None = None, details: str | None = None) -> str:
    """Render a standalone error page supporting both error_page(request, problem) and error_page(status, title, desc)."""
    if hasattr(request_or_status, "path"):
        # Called as error_page(request, problem)
        req = request_or_status
        prob = problem_or_title
        status = getattr(prob, "status", 500)
        title = getattr(prob, "message", "Error")
        desc = getattr(prob, "code", "error")
        det = getattr(prob, "detail", "")
        csrf = req.session.get("csrf_token", "") if getattr(req, "session", None) else ""
        user = getattr(req, "user", None)
    else:
        status = request_or_status
        title = problem_or_title or "Error"
        desc = description or ""
        det = details or ""
        csrf = ""
        user = None

    details_p = f'<pre class="mono tiny dim" style="margin-top:14px;white-space:pre-wrap">{esc(det)}</pre>' if det else ""
    content = f"""<div class="panel" style="max-width:620px;margin:40px auto">
  <div class="panel__head">
    <h2>{status} · {esc(title)}</h2>
    <span class="chip chip--red">ERR_{status}</span>
  </div>
  <div class="panel__body">
    <p class="lede">{esc(desc)}</p>
    {details_p}
    <div style="margin-top:20px">
      <a href="/" class="btn btn--sm">&larr; Return Home</a>
    </div>
  </div>
</div>"""
    return render_shell(title=f"Error {status}", content=content, user=user, csrf_token=csrf)
