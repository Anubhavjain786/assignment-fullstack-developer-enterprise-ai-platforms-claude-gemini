"""Period resolution. Anchor = end of data window 2026-09-28 (exclusive end).

- last_7_days  -> [2026-09-21, 2026-09-28)
- last_30_days -> [2026-08-29, 2026-09-28)
- 2026-W36     -> ISO week Mon..Sun
- 2026-09      -> calendar month
"""
from __future__ import annotations

import re
from datetime import date, timedelta

ANCHOR = date(2026, 9, 28)  # end_exclusive of the fixture window

PERIOD_RE = re.compile(r"^(last_7_days|last_30_days|\d{4}-W\d{2}|\d{4}-\d{2})$")


def resolve_period(period: str) -> tuple[str, str]:
    """Return (start, end_exclusive) as YYYY-MM-DD strings. Raises ValueError."""
    if period == "last_7_days":
        return ((ANCHOR - timedelta(days=7)).isoformat(), ANCHOR.isoformat())
    if period == "last_30_days":
        return ((ANCHOR - timedelta(days=30)).isoformat(), ANCHOR.isoformat())
    m = re.fullmatch(r"(\d{4})-W(\d{2})", period)
    if m:
        year, week = int(m.group(1)), int(m.group(2))
        start = date.fromisocalendar(year, week, 1)
        return (start.isoformat(), (start + timedelta(days=7)).isoformat())
    m = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        return (start.isoformat(), end.isoformat())
    raise ValueError(f"Invalid period: {period!r}")


def in_period(day: str, start: str, end_exclusive: str) -> bool:
    return start <= day < end_exclusive


def iso_week_of(day: str) -> str:
    d = date.fromisoformat(day)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"
