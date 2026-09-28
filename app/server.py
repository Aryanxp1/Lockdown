"""HTTP server and request dispatch.

The whole request path is: route match -> session resolution -> authorization
(role, then CSRF for state-changing verbs) -> handler -> response. Guards live
here once, so a new endpoint cannot accidentally skip them: a route has to
declare `roles=` and `csrf=True` explicitly, and unauthenticated access is only
possible when a route declares `public=True`.

Security headers are applied to every response, including errors.
"""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import audit, auth, config, db, http as httpx, seed as fixtures_seed, boot
from .routes import build_routes

ROUTER = None
MAX_BODY = 2 * 1024 * 1024  # 2 MiB is plenty for JSON, forms and pasted CSV

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")

STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
}


def router():
    global ROUTER
    if ROUTER is None:
        ROUTER = build_routes()
    return ROUTER


class PortalHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Lockdown/1.0"
    sys_version = ""

    # --- verbs ----------------------------------------------------------
    def do_GET(self):
        self.dispatch("GET")

    def do_HEAD(self):
        self.dispatch("HEAD")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    # --- pipeline -------------------------------------------------------
    def read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        if length > MAX_BODY:
            raise httpx.Problem(413, "payload_too_large",
                                "That request body is larger than this portal accepts.",
                                "Limit is %d bytes." % MAX_BODY)
        return self.rfile.read(length)

    def dispatch(self, method: str) -> None:
        request = None
        try:
            request = httpx.Request(method=method, target=self.path,
                                    headers=dict(self.headers.items()),
                                    body=self.read_body(),
                                    client_ip=self.client_address[0])
        except httpx.Problem as problem:
            self.write(httpx.Response.json({"error": problem.code, "message": problem.message},
                                           status=problem.status))
            return
        except Exception as exc:  # pragma: no cover - malformed socket input
            self.write(httpx.Response.text("400 Bad Request: %s" % exc, status=400))
            return

        try:
            response = self.handle_request(request)
        except httpx.Redirect as redirect:
            response = httpx.Response.redirect(redirect.location, redirect.status)
        except httpx.Problem as problem:
            response = error_response(request, problem)
        except Exception as exc:  # pragma: no cover - unexpected bug
            traceback.print_exc(file=sys.stderr)
            request.audit_notes.append(str(exc))
            audit.record(action="request.error", entity_type="route", entity_id=request.path,
                         summary="%s %s raised %s" % (method, request.path, type(exc).__name__),
                         outcome="error", request=request, meta={"error": str(exc)})
            response = error_response(request, httpx.Problem(
                500, "internal_error", "Something went wrong handling that request.",
                "%s: %s" % (type(exc).__name__, exc)))
        finally:
            db.release()

        if method == "HEAD":
            response.body = b""
        if "Content-Length" not in response.headers:
            response.headers["Content-Length"] = str(len(response.body))
        self.write(response)

    def write(self, response: httpx.Response) -> None:
        try:
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            for name, value, options in response.cookies:
                self.send_header("Set-Cookie", cookie_header(name, value, options))
            for name, value in security_headers().items():
                self.send_header(name, value)
            self.end_headers()
            if response.body:
                self.wfile.write(response.body)
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
            pass

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Static assets are files, not routes: they are served before matching so
        # a stylesheet can never be shadowed by a page route.
        if request.path.startswith("/static/"):
            return serve_static(request)

        route, params = router().match(request.method, request.path)
        if route is None:
            raise httpx.Problem(404, "not_found", "No such page or endpoint.",
                                "Nothing is registered at %s." % request.path)
        request.route = route
        request.params = params
        from . import seed as _seed_guard  # noqa: F401  (keeps import order stable)
        auth.resolve(request)

        if route.roles is not None:
            guard_roles(request, route)
        if route.csrf and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            guard_csrf(request, route)

        return route.handler(request)

    def log_message(self, fmt, *args):  # noqa: A003 - base class signature
        return

    def log_error(self, fmt, *args):  # pragma: no cover
        print("[http] %s %s" % (self.address_string(), fmt % args), file=sys.stderr)

def security_headers() -> dict:
    return {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": CSP,
        "Cache-Control": "no-store",
    }


def cookie_header(name: str, value: str, options: dict) -> str:
    parts = ["%s=%s" % (name, value)]
    if options.get("path"):
        parts.append("Path=%s" % options["path"])
    else:
        parts.append("Path=/")
    if options.get("max_age") is not None:
        parts.append("Max-Age=%d" % int(options["max_age"]))
    if options.get("httponly"):
        parts.append("HttpOnly")
    if options.get("samesite"):
        parts.append("SameSite=%s" % options["samesite"])
    if options.get("secure"):
        parts.append("Secure")
    return "; ".join(parts)


def guard_roles(request: httpx.Request, route) -> None:
    """Role gate for a route. Admin passes everything; nobody else is implied."""
    if request.user is None:
        audit.refused(request, "access.denied", "no session for %s %s" % (
            route.method, route.pattern))
        if request.wants_json:
            raise httpx.Problem(401, "authentication_required",
                                "Sign in to continue.",
                                "This endpoint needs a session cookie or a bearer token.")
        raise httpx.Redirect("/login?next=%s" % request.path, 303)
    if not auth.role_allows(request.user["role"], route.roles):
        audit.refused(request, "access.denied", "%s tried %s (needs %s)" % (
            request.user["email"], route.pattern, ",".join(sorted(route.roles))),
            entity_type="route", entity_id=route.pattern)
        raise httpx.Problem(403, "forbidden",
                            "Your account does not have access to this.",
                            "Required role: %s. Your role: %s." % (
                                ", ".join(sorted(route.roles)),
                                auth.ROLE_LABEL.get(request.user["role"], "visitor")))


def guard_csrf(request: httpx.Request, route) -> None:
    """Cookie sessions must prove they sent the request themselves."""
    if auth.csrf_ok(request):
        return
    audit.refused(request, "csrf.rejected", "missing or wrong CSRF token for %s" % (
        route.pattern), entity_type="route", entity_id=route.pattern)
    raise httpx.Problem(403, "csrf_failed",
                        "That form could not be verified as coming from this portal.",
                        "Send the session's CSRF token in the X-CSRF-Token header or "
                        "the _csrf field.")


def error_response(request: httpx.Request, problem: httpx.Problem) -> httpx.Response:
    payload = {"error": problem.code, "message": problem.message,
               "status": problem.status, "path": request.path}
    if problem.detail:
        payload["detail"] = problem.detail
    headers = dict(problem.headers)
    if request.wants_json:
        return httpx.Response.json(payload, status=problem.status, headers=headers)
    from .views import layout
    return httpx.Response.html(
        layout.error_page(request, problem), status=problem.status, headers=headers)


def serve_static(request: httpx.Request) -> httpx.Response:
    name = request.path[len("/static/"):]
    if "/" in name or "\\" in name or ".." in name:
        raise httpx.Problem(404, "not_found", "No such asset.")
    target = (config.STATIC_DIR / name).resolve()
    if not str(target).startswith(str(config.STATIC_DIR.resolve())) or not target.is_file():
        raise httpx.Problem(404, "not_found", "No such asset.")
    body = target.read_bytes()
    content_type = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return httpx.Response(200, body, {"Cache-Control": "public, max-age=300"}, content_type)


def build_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host or config.HOST, port or config.PORT), PortalHandler)
    httpd.daemon_threads = True
    return httpd


def serve(*, host=None, port=None, announce: bool = True) -> None:
    httpd = build_server(host, port)
    if announce:
        print("lockdown portal listening on %s:%d" % httpd.server_address[:2], flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        print("\nshutting down", flush=True)
    finally:
        httpd.server_close()

