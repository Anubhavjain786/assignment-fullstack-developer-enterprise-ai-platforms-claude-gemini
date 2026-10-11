"""Aggregation over the unified UsageRecords."""
from __future__ import annotations

from functools import lru_cache

from . import directory as d
from .ingest_claude import load_claude_records
from .ingest_gemini import load_gemini_records
from .model import UsageRecord
from .periods import in_period, iso_week_of


@lru_cache(maxsize=1)
def all_records() -> list[UsageRecord]:
    return load_claude_records() + load_gemini_records()


def filter_records(
    group: str | None = None,
    start: str | None = None,
    end_exclusive: str | None = None,
    user_id: str | None = None,
) -> list[UsageRecord]:
    out = []
    for r in all_records():
        if group is not None and r.group_id != group:
            continue
        if user_id is not None and r.user_id != user_id:
            continue
        if start is not None and not in_period(r.date, start, end_exclusive or "9999-12-31"):
            continue
        out.append(r)
    return out


def summarize(records: list[UsageRecord]) -> dict:
    """Per-platform totals + grand totals (contract PlatformTotals shape)."""
    by_platform: dict[str, dict] = {}
    for r in records:
        b = by_platform.setdefault(
            r.platform,
            {
                "platform": r.platform,
                "requests": 0,
                "has_requests": False,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        b["input_tokens"] += r.input_tokens
        b["output_tokens"] += r.output_tokens
        b["total_tokens"] += r.total_tokens
        b["cost_usd"] += r.cost_usd
        if r.requests is not None:
            b["requests"] += r.requests
            b["has_requests"] = True
    platforms = []
    for key in ("claude", "gemini"):
        if key not in by_platform:
            continue
        b = by_platform[key]
        platforms.append(
            {
                "platform": key,
                "requests": b["requests"] if b["has_requests"] else None,
                "input_tokens": b["input_tokens"],
                "output_tokens": b["output_tokens"],
                "total_tokens": b["total_tokens"],
                "cost_usd": round(b["cost_usd"], 2),
            }
        )
    totals = {
        "total_tokens": sum(p["total_tokens"] for p in platforms),
        "cost_usd": round(sum(p["cost_usd"] for p in platforms), 2),
    }
    return {"platforms": platforms, "totals": totals}


def top_users(records: list[UsageRecord], limit: int = 10) -> list[dict]:
    agg: dict[str, dict] = {}
    for r in records:
        a = agg.setdefault(
            r.user_id,
            {
                "user_id": r.user_id,
                "name": r.name,
                "email": r.email,
                "group": r.group_id,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        a["total_tokens"] += r.total_tokens
        a["cost_usd"] += r.cost_usd
    rows = sorted(agg.values(), key=lambda a: a["total_tokens"], reverse=True)[:limit]
    for row in rows:
        row["cost_usd"] = round(row["cost_usd"], 2)
    return rows


def weekly_buckets(records: list[UsageRecord]) -> list[dict]:
    buckets: dict[str, list[UsageRecord]] = {}
    for r in records:
        buckets.setdefault(iso_week_of(r.date), []).append(r)
    out = []
    for week in sorted(buckets):
        s = summarize(buckets[week])
        out.append(
            {
                "week": week,
                "total_tokens": s["totals"]["total_tokens"],
                "cost_usd": s["totals"]["cost_usd"],
                "platforms": s["platforms"],
            }
        )
    return out
