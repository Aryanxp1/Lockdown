"""Time helpers.

Every timestamp in the database is an ISO-8601 UTC string ending in `Z`:
`2026-03-01T18:00:00Z`. That format sorts lexicographically, which means SQL
comparisons (`WHERE submissions_close < ?`) are exact and no timezone library
is needed.
"""

from __future__ import annotations

import datetime as _dt

UTC = _dt.timezone.utc
FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now() -> _dt.datetime:
    return _dt.datetime.now(UTC).replace(microsecond=0)


def iso(value: _dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(FORMAT)


def now_iso() -> str:
    return iso(now())


def parse(value):
    """Parse an ISO-8601 timestamp. Returns None when it cannot be parsed."""
    if not value:
        return None
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_or(value, fallback: _dt.datetime):
    return parse(value) or fallback


def days_from_now(days: float) -> str:
    return iso(now() + _dt.timedelta(days=days))


# --- presentation -------------------------------------------------------

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def human(value, with_time: bool = True, fallback: str = "--") -> str:
    parsed = parse(value)
    if parsed is None:
        return fallback
    text = "%d %s %d" % (parsed.day, MONTHS[parsed.month - 1], parsed.year)
    if with_time:
        text += " %02d:%02d UTC" % (parsed.hour, parsed.minute)
    return text


def human_date(value, fallback: str = "--") -> str:
    return human(value, with_time=False, fallback=fallback)


def machine(value, fallback: str = "") -> str:
    parsed = parse(value)
    if parsed is None:
        return fallback
    return iso(parsed)


def relative(value, now_dt: _dt.datetime | None = None) -> str:
    """`in 3 days` / `2 hours ago` — coarse on purpose, never precise-looking."""
    parsed = parse(value)
    if parsed is None:
        return "--"
    reference = now_dt or now()
    delta = parsed - reference
    seconds = int(delta.total_seconds())
    future = seconds >= 0
    seconds = abs(seconds)
    if seconds < 90:
        text = "%d seconds" % seconds
    elif seconds < 5400:
        text = "%d minutes" % round(seconds / 60)
    elif seconds < 172800:
        text = "%d hours" % round(seconds / 3600)
    elif seconds < 7776000:
        text = "%d days" % round(seconds / 86400)
    else:
        text = "%d months" % round(seconds / 2592000)
    return ("in " + text) if future else (text + " ago")


def countdown_parts(value, now_dt: _dt.datetime | None = None) -> dict:
    """Structured countdown for the client-side clock."""
    parsed = parse(value)
    reference = now_dt or now()
    if parsed is None:
        return {"target": "", "state": "unknown", "seconds": 0,
                "days": 0, "hours": 0, "minutes": 0, "days_label": "--"}
    seconds = int((parsed - reference).total_seconds())
    future = max(seconds, 0)
    return {
        "target": machine(value),
        "state": "open" if seconds > 0 else "closed",
        "seconds": max(seconds, 0),
        "days": future // 86400,
        "hours": (future % 86400) // 3600,
        "minutes": (future % 3600) // 60,
        "days_label": relative(value, reference) if seconds > 0 else relative(value, reference),
    }


def from_form(value: str):
    """Accept `2026-03-01T18:00` (datetime-local) and `2026-03-01` from forms."""
    text = (value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        text += "T00:00"
    parsed = parse(text)
    return iso(parsed) if parsed else None
