"""Layout shell and base navigation for Lockdown."""

from __future__ import annotations

from typing import Any

from .ui import esc
from .. import config


def render_shell(*, title: str, content: str, user: dict | None = None,
                 current_path: str = "", csrf_token: str = "",
                 notice: str | None = None, error: str | None = None,
                 event: dict | None = None) -> str:
    """Render the full HTML5 shell with modern dark tech aesthetic."""
    role = user.get("role") if user else None
    nav_links = _nav_links(role, current_path)

    notice_markup = f'<div class="notice notice--success">{esc(notice)}</div>' if notice else ""
    error_markup = f'<div class="notice notice--error">{esc(error)}</div>' if error else ""

    # User profile badge in masthead
    if user:
        display_name = user.get("name") or user.get("email", "User")
        initial = (display_name[:1] or "U").upper()
        role_label = (role or "user").upper()
        user_info = f"""<div class="user-pill">
          <span class="user-avatar">{esc(initial)}</span>
          <span class="user-name">{esc(display_name)}</span>
          <span class="role-tag">{esc(role_label)}</span>
        </div>"""
    else:
        user_info = '<a href="/signin" class="btn btn--sm btn--ghost">Sign in</a>'

    # The one-click demo sign-in is only advertised (and only works) when the
    # operator set PORTAL_FAST_LOGIN=1; see app/routes.py:handle_fast_login.
    fast_login_markup = """<div class="fast-login-wrapper">
      <button type="button" class="fast-login-btn" id="fastLoginToggle" aria-expanded="false" aria-haspopup="true">
        Fast login
      </button>
      <div class="fast-login-dropdown" id="fastLoginDropdown" aria-label="Demo Accounts Menu" hidden>
        <div class="fast-login-header">
          <span class="fast-login-badge">DEMO ACCOUNTS</span>
          <p class="fast-login-desc">Quick sign-in for testing Sample Hack &amp; Dogfood.</p>
          <a href="/events" class="fast-login-guide">Platform guide &amp; sitemap &rarr;</a>
        </div>
        <div class="fast-login-divider"></div>
        <div class="fast-login-accounts">
          <form method="POST" action="/fast-login" class="fast-login-form">
            <input type="hidden" name="account" value="organizer">
            <button type="submit" class="demo-account-item">
              <span class="demo-account-role">Organizer</span>
              <span class="demo-account-meta">Mira Halvorsen &middot; Demo admin</span>
            </button>
          </form>

          <form method="POST" action="/fast-login" class="fast-login-form">
            <input type="hidden" name="account" value="judge_sample">
            <button type="submit" class="demo-account-item">
              <span class="demo-account-role">Judge (Sample Hack)</span>
              <span class="demo-account-meta">Tomas Varga &middot; Review queue &amp; duels</span>
            </button>
          </form>

          <form method="POST" action="/fast-login" class="fast-login-form">
            <input type="hidden" name="account" value="judge_dogfood">
            <button type="submit" class="demo-account-item">
              <span class="demo-account-role">Judge (Dogfood)</span>
              <span class="demo-account-meta">Wei Lindqvist &middot; Active queue &amp; duels</span>
            </button>
          </form>

          <form method="POST" action="/fast-login" class="fast-login-form">
            <input type="hidden" name="account" value="builder_sample">
            <button type="submit" class="demo-account-item">
              <span class="demo-account-role">Builder (Sample Hack)</span>
              <span class="demo-account-meta">Priya Raut &middot; Team NorthKiln workspace</span>
            </button>
          </form>

          <form method="POST" action="/fast-login" class="fast-login-form">
            <input type="hidden" name="account" value="builder_dogfood">
            <button type="submit" class="demo-account-item">
              <span class="demo-account-role">Builder (Dogfood)</span>
              <span class="demo-account-meta">Ines Falk &middot; Team Loose Threads workspace</span>
            </button>
          </form>

          <form method="POST" action="/fast-login" class="fast-login-form">
            <input type="hidden" name="account" value="admin">
            <button type="submit" class="demo-account-item">
              <span class="demo-account-role">Platform Admin</span>
              <span class="demo-account-meta">Rune Adel &middot; Root administrator</span>
            </button>
          </form>
        </div>
      </div>
    </div>"""

    if not config.FAST_LOGIN_ENABLED:
        fast_login_markup = ""

    event_sub = f' <span class="event-context-tag">{esc(event["name"])}</span>' if event else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} — Lockdown</title>
  <link rel="stylesheet" href="/static/app.css">
  <script defer src="/static/app.js"></script>
  <script defer src="/static/globe.js"></script>
  <script defer src="/static/boxes_ripple.js"></script>
  <script defer src="/static/canvas_text.js"></script>
</head>
<body>
  <a href="#main" class="skip">Skip to main content</a>
  <div class="shell">
    <header class="masthead" role="banner">
      <div class="masthead__row">
        <div class="masthead__brand">
          <div class="masthead__logo-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div>
            <h1 class="masthead__title"><a href="/">LOCKDOWN<span class="masthead__title-glow">.DEV</span></a></h1>
          </div>
          {event_sub}
        </div>
        <div class="masthead__meta">
          <span class="status-indicator"><span class="status-dot"></span> LOCAL ENCLAVE</span>
          {user_info}
          {fast_login_markup}
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
      <div><strong>Lockdown</strong> &middot; Competition &amp; Judging Infrastructure Platform</div>
      <div class="mono tiny dim">BUILD: 2026.09 &middot; DETERMINISTIC OFFLINE ENGINE</div>
    </footer>
  </div>
</body>
</html>"""


def _nav_links(role: str | None, current_path: str) -> str:
    # Core public discovery links
    core_links = [
        ("/", "Home"),
        ("/events", "Hackathons"),
        ("/gallery", "Gallery"),
        ("/results", "Results")
    ]

    parts = []
    for href, label in core_links:
        is_cur = current_path == href or (href != "/" and current_path.startswith(href))
        cur_attr = ' aria-current="page"' if is_cur else ""
        parts.append(f'<a href="{href}"{cur_attr}>{esc(label)}</a>')

    # Role-specific workspaces - clean, subtle divider and badge
    if role in ("organizer", "admin"):
        parts.append('<span class="nav__divider" aria-hidden="true"></span>')
        org_links = [
            ("/organizer", "My Hackathons"),
            ("/organizer/submissions", "Submissions"),
            ("/organizer/judges", "Judges"),
            ("/organizer/audit", "Audit Log"),
        ]
        for href, label in org_links:
            is_cur = current_path == href or (href != "/organizer" and current_path.startswith(href))
            cur_attr = ' aria-current="page"' if is_cur else ""
            parts.append(f'<a href="{href}"{cur_attr}>{esc(label)}</a>')

    elif role == "judge":
        parts.append('<span class="nav__divider" aria-hidden="true"></span>')
        is_cur = current_path == "/judge" or current_path.startswith("/judge")
        cur_attr = ' aria-current="page"' if is_cur else ""
        parts.append(f'<a href="/judge"{cur_attr}>Evaluation Queue</a>')

    elif role == "participant":
        parts.append('<span class="nav__divider" aria-hidden="true"></span>')
        is_cur = current_path == "/participant" or current_path.startswith("/participant")
        cur_attr = ' aria-current="page"' if is_cur else ""
        parts.append(f'<a href="/participant"{cur_attr}>My Project Workspace</a>')

    return "\n      ".join(parts)


def _auth_links(user: dict | None, csrf_token: str) -> str:
    if not user:
        return '<a href="/signin" class="btn btn--sm btn--primary">Sign In</a>'
    return f"""<form method="POST" action="/signout" class="nav__form">
      <input type="hidden" name="csrf_token" value="{esc(csrf_token)}">
      <button type="submit" class="btn btn--sm btn--ghost">Sign Out</button>
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

    details_p = f'<pre class="mono tiny dim error__detail">{esc(det)}</pre>' if det else ""
    content = f"""<div class="panel error__panel">
  <div class="panel__head">
    <div class="error__head">
      <span class="role-tag error__status">STATUS {status}</span>
      <h2>{esc(title)}</h2>
    </div>
  </div>
  <div class="panel__body">
    <p class="lede">{esc(desc)}</p>
    {details_p}
    <div class="error__actions">
      <a href="/" class="btn btn--sm btn--ghost">&larr; Return to Dashboard</a>
    </div>
  </div>
</div>"""
    return render_shell(title=f"Error {status}", content=content, user=user, csrf_token=csrf)
