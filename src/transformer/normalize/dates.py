"""Dates -> 'YYYY-MM', and a year extractor for education end-years.

Why hand-written patterns instead of dateutil's fuzzy parser: dateutil fills
missing fields from *today's date*, so "2020" would become e.g. "2020-06"
depending on when you run it — non-deterministic and invented. We only accept
formats that actually carry a month, and we refuse to guess one.
"""

from __future__ import annotations

import re

# First three letters uniquely identify every month, so we key on that and
# accept both abbreviations and full names ("Jan", "January", "Sept").
_MON3 = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# An ongoing role: caller maps these to a null end-date, not a parse failure.
_PRESENT = {"present", "current", "now", "ongoing", "to date", "till date", "todate"}

_YEAR_MONTH = re.compile(r"^(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?$")   # 2020-03, 2020/03/15
_MONTH_YEAR = re.compile(r"^(\d{1,2})[-/.](\d{4})$")                     # 03/2020
_NAME_YEAR = re.compile(r"^([a-z]{3,9})[\s\-/.]+(\d{4})$")               # Jan 2020
_YEAR_NAME = re.compile(r"^(\d{4})[\s\-/.]+([a-z]{3,9})$")               # 2020 Jan
_ANY_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def to_year_month(raw: object) -> str | None:
    """Parse to 'YYYY-MM', or None. Year-only input returns None on purpose:
    we will not invent a month (honestly-empty beats wrong-but-confident)."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in _PRESENT:
        return None

    m = _YEAR_MONTH.match(s)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)))

    m = _MONTH_YEAR.match(s)
    if m:
        return _fmt(int(m.group(2)), int(m.group(1)))

    m = _NAME_YEAR.match(s)
    if m and m.group(1)[:3] in _MON3:
        return _fmt(int(m.group(2)), _MON3[m.group(1)[:3]])

    m = _YEAR_NAME.match(s)
    if m and m.group(2)[:3] in _MON3:
        return _fmt(int(m.group(1)), _MON3[m.group(2)[:3]])

    return None


def to_year(raw: object) -> int | None:
    """First 4-digit year found, for education end-years (where month is not
    part of the schema, so a bare year is legitimate)."""
    if raw is None:
        return None
    m = _ANY_YEAR.search(str(raw))
    return int(m.group(0)) if m else None


def _fmt(year: int, month: int) -> str | None:
    return f"{year:04d}-{month:02d}" if 1 <= month <= 12 else None
