"""Pure helper functions shared by the MyPolaris integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

MONTHS_NUM_RO = {
    1: "ianuarie",
    2: "februarie",
    3: "martie",
    4: "aprilie",
    5: "mai",
    6: "iunie",
    7: "iulie",
    8: "august",
    9: "septembrie",
    10: "octombrie",
    11: "noiembrie",
    12: "decembrie",
}


def build_cookie_header(session_cookie: str) -> str:
    """Normalize the configured cookie into an HTTP Cookie header value."""
    ck = (session_cookie or "").strip().rstrip(";")
    if "=" in ck:
        return ck
    return f"ASP.NET_SessionId={ck}"


def parse_money(raw: Any) -> float | None:
    """Parse Romanian-style monetary strings into floats."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace("\xa0", "").replace(" ", "")
    s = s.replace("RON", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def year_from_dmy(raw: Any) -> int | None:
    """Extract the year from a ``DD.MM.YYYY`` string."""
    if not raw:
        return None
    parts = str(raw).split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def format_ron(value: float | int | None) -> str:
    """Format a numeric value using Romanian decimal separators."""
    if value is None:
        return "0,00"
    return f"{float(value):.2f}".replace(".", ",")


def month_from_dmy(raw: Any) -> int | None:
    """Extract the month from a ``DD.MM.YYYY`` string."""
    if not raw:
        return None
    parts = str(raw).split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def month_name(raw: Any) -> str:
    """Return the Romanian month name from a ``DD.MM.YYYY`` string."""
    month = month_from_dmy(raw)
    return MONTHS_NUM_RO.get(month, "necunoscut") if month else "necunoscut"


def sort_by_dmy(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Sort rows by a ``DD.MM.YYYY`` field, keeping invalid dates first."""

    def _parse(item: dict[str, Any]) -> datetime:
        raw = item.get(key) or ""
        parts = str(raw).split(".")
        if len(parts) != 3:
            return datetime.min
        try:
            return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, TypeError):
            return datetime.min

    return sorted(items, key=_parse)


def slug_for_entity_id(value: str) -> str:
    """Slugify a string for use inside an entity_id."""
    out: list[str] = []
    for ch in (value or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "/", "(", ")"):
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "loc"


def localize_access_source(source: str | None) -> str | None:
    """Translate internal access-source identifiers into Romanian labels."""
    if source is None:
        return None
    return {
        "keepalive": "mentinere sesiune",
        "login": "autentificare",
        "refresh": "actualizare",
    }.get(source, source)