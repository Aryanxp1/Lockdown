"""Small helpers that do not belong to any one layer."""

from __future__ import annotations

import re
import secrets
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_WORD = re.compile(r"[a-z0-9]+")


def new_id(prefix: str) -> str:
    """`prj_9f3c1a7d2b04` — prefixed ids keep logs and CSVs readable."""
    return "%s_%s" % (prefix, secrets.token_hex(6))


def slugify(value: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    slug = _NON_SLUG.sub("-", text.lower()).strip("-")
    return slug[:60] or fallback


def words(value: str) -> set[str]:
    return set(_WORD.findall((value or "").lower()))


def truncate(value: str, limit: int) -> str:
    text = (value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def as_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def as_float(value, default=None):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def percent(value: float | None, total: float) -> float:
    if not total:
        return 0.0
    return round(100.0 * (value or 0.0) / total, 1)


def csv_cell(value) -> str:
    """Quote a cell only when it needs it (keeps exports readable)."""
    text = "" if value is None else str(value)
    if any(ch in text for ch in ',"\r\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def csv_row(cells) -> str:
    return ",".join(csv_cell(cell) for cell in cells)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    if count == 1:
        return "%d %s" % (count, singular)
    return "%d %s" % (count, plural_form or singular + "s")


def hours_between(start: str, end: str) -> float:
    from . import timeutil
    first, last = timeutil.parse(start), timeutil.parse(end)
    if not first or not last:
        return 0.0
    return round((last - first).total_seconds() / 3600.0, 1)


def group_by(rows, key):
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped


def tags_to_list(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = re.split(r"[,\n]", value or "")
    cleaned, seen = [], set()
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned[:12]


def safe_next(target: str, fallback: str = "/dashboard") -> str:
    """Only allow same-origin relative redirects (no open redirect)."""
    text = (target or "").strip()
    if text.startswith("/") and not text.startswith("//") and "\\" not in text:
        return text
    return fallback
