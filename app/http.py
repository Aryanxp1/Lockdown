"""Minimal HTTP layer: request parsing, responses, routing, guards.

`http.server` gives us a socket and a handler class; everything above that —
routing, JSON, cookies, CSRF, authorization — is in this file and in
`server.py`. The API is deliberately small so the whole request path can be
read in one sitting.
"""

from __future__ import annotations

import json
import re
import urllib.parse


class Problem(Exception):
    """An expected failure. Rendered as JSON for /api, HTML for pages."""

    def __init__(self, status: int, code: str, message: str = "", detail: str = "",
                 headers: dict | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()
        self.detail = detail
        self.headers = headers or {}


class Redirect(Exception):
    def __init__(self, location: str, status: int = 303):
        super().__init__(location)
        self.location = location
        self.status = status


def _parse_cookies(header: str) -> dict:
    cookies = {}
    for chunk in (header or "").split(";"):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        cookies[key.strip()] = urllib.parse.unquote(value.strip())
    return cookies


class Headers(dict):
    """Case-insensitive header mapping.

    HTTP header names are not case sensitive, and different clients prove it:
    browsers send `X-CSRF-Token`, urllib lowercases it to `X-csrf-token`, curl
    sends whatever the user typed. Keys are stored lowercase so a lookup finds
    all three.
    """

    def __init__(self, items=None):
        super().__init__()
        source = items.items() if hasattr(items, "items") else (items or ())
        for key, value in source:
            self[key] = value

    def __setitem__(self, key, value):
        super().__setitem__(str(key).lower(), value)

    def __getitem__(self, key):
        return super().__getitem__(str(key).lower())

    def __delitem__(self, key):
        return super().__delitem__(str(key).lower())

    def __contains__(self, key):
        return super().__contains__(str(key).lower())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


class Request:
    def __init__(self, method: str, target: str, headers, body: bytes, client_ip: str):
        self.method = method.upper()
        self.target = target
        split = urllib.parse.urlsplit(target)
        self.path = urllib.parse.unquote(split.path or "/")
        if len(self.path) > 1:
            self.path = self.path.rstrip("/") or "/"
        self.raw_query = split.query
        self.query = urllib.parse.parse_qs(split.query, keep_blank_values=True)
        self.headers = Headers(headers)
        self.body = body or b""
        self.client_ip = client_ip
        self.params: dict[str, str] = {}
        # Debugging breadcrumbs for a request that blows up mid-dispatch; the
        # server appends to this before turning the exception into a 500.
        self.audit_notes: list[str] = []
        self.cookies = _parse_cookies(headers.get("Cookie", ""))
        self.route = None
        self.user = None
        self.session = None
        self._form = None
        self._json = None
        self._json_error = None
        self._text = None

    def q(self, name: str, default=None):
        values = self.query.get(name)
        if not values:
            return default
        return values[0]

    def q_all(self, name: str) -> list[str]:
        return list(self.query.get(name, []))

    def q_bool(self, name: str, default: bool = False) -> bool:
        raw = self.q(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

    @property
    def form(self) -> dict:
        if self._form is None:
            parsed = {}
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type in ("application/x-www-form-urlencoded", ""):
                text = self.body.decode("utf-8", "replace")
                for key, values in urllib.parse.parse_qs(text, keep_blank_values=True).items():
                    parsed[key] = values[0]
            self._form = parsed
        return self._form

    @property
    def json_payload(self):
        if self._json is None and self._json_error is None:
            content_type = (self.headers.get("Content-Type") or "")
            if "json" in content_type.lower() and self.body:
                try:
                    self._json = json.loads(self.body.decode("utf-8", "replace"))
                except ValueError as exc:
                    self._json_error = str(exc)
        return self._json

    @property
    def json_error(self):
        _ = self.json_payload
        return self._json_error

    @property
    def raw_text(self) -> str:
        if self._text is None:
            self._text = self.body.decode("utf-8", "replace")
        return self._text

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Request %s %s>" % (self.method, self.path)


    def val(self, name: str, default: str = "") -> str:
        """Precedence: query string, then JSON body, then form fields."""
        if name in self.query:
            return self.q(name, default)
        payload = self.json_payload
        if isinstance(payload, dict) and name in payload:
            value = payload[name]
            return "" if value is None else str(value)
        return self.form.get(name, default)

    def field(self, name: str, default: str = "") -> str:
        """Form-first lookup: HTML pages post forms, API clients post JSON."""
        if name in self.form:
            return self.form.get(name, default)
        payload = self.json_payload
        if isinstance(payload, dict) and name in payload:
            value = payload[name]
            return "" if value is None else str(value)
        return self.q(name, default)

    def field_list(self, name: str) -> list[str]:
        payload = self.json_payload
        if name in self.form:
            return [self.form[name]]
        if isinstance(payload, dict) and isinstance(payload.get(name), list):
            return [str(item) for item in payload[name]]
        return self.q_all(name)

    def checkbox(self, name: str, default: bool = False) -> bool:
        payload = self.json_payload
        if name in self.form:
            return True
        if isinstance(payload, dict) and name in payload:
            return str(payload[name]).lower() in ("1", "true", "yes", "on")
        if name in self.query:
            return self.q_bool(name, default)
        return default

    # --- negotiation ----------------------------------------------------
    @property
    def is_api(self) -> bool:
        return self.path.startswith("/api/")

    @property
    def wants_json(self) -> bool:
        if self.is_api:
            return True
        if self.route is not None and getattr(self.route, "json_only", False):
            return True
        accept = (self.headers.get("Accept") or "").lower()
        return "application/json" in accept and "text/html" not in accept

    def bearer_token(self) -> str:
        header = self.headers.get("Authorization") or ""
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return ""

    def csrf_candidate(self) -> str:
        token = (self.headers.get("X-CSRF-Token") or
                 self.headers.get("X-CSRFToken") or "").strip()
        if token:
            return token
        payload = self.json_payload
        for source in (self.form, payload if isinstance(payload, dict) else {}):
            value = source.get("_csrf") or source.get("csrf_token")
            if value:
                return str(value)
        return self.q("_csrf", "") or ""


class Response:
    def __init__(self, status: int = 200, body: bytes = b"", headers=None,
                 content_type: str = "text/html; charset=utf-8"):
        self.status = status
        self.body = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.headers = {"Content-Type": content_type}
        if headers:
            self.headers.update(headers)
        self.cookies: list[tuple[str, str, dict]] = []

    def set_cookie(self, name: str, value: str, **options) -> "Response":
        self.cookies.append((name, value, options))
        return self

    def header(self, name: str, value: str) -> "Response":
        self.headers[name] = value
        return self

    @classmethod
    def html(cls, body: str, status: int = 200, headers=None) -> "Response":
        return cls(status, body, headers, "text/html; charset=utf-8")

    @classmethod
    def text(cls, body: str, status: int = 200, headers=None) -> "Response":
        return cls(status, body, headers, "text/plain; charset=utf-8")

    @classmethod
    def json(cls, payload, status: int = 200, headers=None) -> "Response":
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return cls(status, body, headers, "application/json; charset=utf-8")

    @classmethod
    def csv(cls, body: str, filename: str = "", status: int = 200) -> "Response":
        extra = {"Content-Disposition": 'attachment; filename="%s"' % (filename or "export.csv")}
        return cls(status, body, extra, "text/csv; charset=utf-8")

    @classmethod
    def redirect(cls, location: str, status: int = 303) -> "Response":
        return cls(status, b"", {"Location": location}, "text/plain; charset=utf-8")

    @classmethod
    def no_content(cls) -> "Response":
        return cls(204, b"", None, "text/plain; charset=utf-8")



class Route:
    """One address. Carries its own authorization and documentation metadata."""

    def __init__(self, method: str, pattern: str, handler, roles=None, csrf: bool = False,
                 tags=(), summary: str = "", public: bool = False, json_only: bool = False,
                 request_body=None, description: str = "", hidden: bool = False):
        self.method = method.upper()
        self.pattern = pattern
        self.handler = handler
        # roles=None or public=True means "anyone, including visitors"
        self.roles = None if (roles is None or public) else frozenset(roles)
        self.csrf = csrf
        self.tags = list(tags or ())
        doc = (handler.__doc__ or "").strip()
        self.summary = summary or (doc.splitlines()[0] if doc else "")
        self.description = description or doc
        self.json_only = json_only
        self.request_body = request_body
        self.hidden = hidden
        pattern_regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        self.regex = re.compile("^" + pattern_regex + "$")
        self.param_names = tuple(re.findall(r"\{(\w+)\}", pattern))

    def match(self, path: str):
        found = self.regex.match(path)
        if not found:
            return None
        return found.groupdict()

    def url(self, **params) -> str:
        url = self.pattern
        for key, value in params.items():
            url = url.replace("{" + key + "}", urllib.parse.quote(str(value)))
        return url

    def __repr__(self) -> str:  # pragma: no cover
        return "<Route %s %s>" % (self.method, self.pattern)


class Router:
    def __init__(self):
        self.routes: list[Route] = []

    def add(self, method: str, pattern: str, handler, **meta) -> Route:
        route = Route(method, pattern, handler, **meta)
        for existing in self.routes:
            if existing.method == route.method and existing.pattern == route.pattern:
                raise ValueError("duplicate route %s %s" % (method, pattern))
        self.routes.append(route)
        return route

    def get(self, pattern: str, handler, **meta):
        return self.add("GET", pattern, handler, **meta)

    def post(self, pattern: str, handler, **meta):
        return self.add("POST", pattern, handler, **meta)

    def match(self, method: str, path: str):
        """Return (route, params) or (None, None); 405 when only the verb is wrong."""
        wrong_verb = []
        for route in self.routes:
            params = route.match(path)
            if params is None:
                continue
            if route.method == method or (method == "HEAD" and route.method == "GET"):
                return route, params
            wrong_verb.append(route.method)
        if wrong_verb:
            allowed = ", ".join(sorted(set(wrong_verb)))
            raise Problem(405, "method_not_allowed",
                          "That address does not accept %s." % method,
                          "Allowed: " + allowed,
                          headers={"Allow": allowed})
        return None, None


def require(value, code: str, message: str, status: int = 400) -> str:
    text = (value or "").strip()
    if not text:
        raise Problem(status, code, message)
    return text
