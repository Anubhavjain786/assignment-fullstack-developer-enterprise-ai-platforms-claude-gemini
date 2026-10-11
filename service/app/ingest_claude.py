"""Ingest the Claude Enterprise Analytics exports into UsageRecords.

Sources (native shapes, see starter-kit README):
- user_usage_report.json: one row per user x day x product x model, token fields.
- user_cost_report.json: same buckets + cost_type; amount/list_amount are
  DECIMAL STRINGS IN CENTS ("88.900050" = $0.889).

Mapping decisions (also documented in README):
- input_tokens = uncached + cache_read + cache_creation(5m + 1h). Verified on
  the fixture: input + output == total_tokens on all 1346 rows.
- Cost join key = (user_id, starting_at, product, model). tokens rows join 1:1
  with usage rows; web_search rows share the same key space (subset) and are
  ADDED to the row cost. cost_usd = sum(amount)/100.
- Group = directory lookup of rbac_group_id (validated against the user's own
  group; fixture has 0 mismatches). User identity = actor.user_id/email.
- Day bucket = starting_at date (UTC).
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from . import directory as directory_mod
from .model import UsageRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLAUDE_DIR = REPO_ROOT / "starter-kit" / "data" / "claude"


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_DIR", str(DEFAULT_CLAUDE_DIR)))


def cents_str_to_usd(amount: str) -> float:
    """Decimal string in cents -> float USD. '88.900050' -> 0.8890005."""
    return float(Decimal(amount) / Decimal(100))


def load_claude_records() -> list[UsageRecord]:
    with open(claude_dir() / "user_usage_report.json") as f:
        usage_rows = json.load(f)["data"]
    with open(claude_dir() / "user_cost_report.json") as f:
        cost_rows = json.load(f)["data"]

    # Aggregate cost per join key (tokens + web_search summed).
    cost_by_key: dict[tuple, float] = {}
    for r in cost_rows:
        key = (
            r["actor"]["user_id"],
            r["starting_at"],
            r["product"],
            r["model"],
        )
        cost_by_key[key] = cost_by_key.get(key, 0.0) + cents_str_to_usd(r["amount"])

    records: list[UsageRecord] = []
    for r in usage_rows:
        actor = r["actor"]
        user = directory_mod.user_by_id(actor["user_id"])
        group_id = directory_mod.rbac_to_group(r["rbac_group_id"])
        if user is None or group_id is None:
            # Unknown identity: skip but keep honest — fixture has none.
            continue
        input_tokens = (
            r["uncached_input_tokens"]
            + r["cache_read_input_tokens"]
            + r["cache_creation"]["ephemeral_5m_input_tokens"]
            + r["cache_creation"]["ephemeral_1h_input_tokens"]
        )
        output_tokens = r["output_tokens"]
        key = (actor["user_id"], r["starting_at"], r["product"], r["model"])
        records.append(
            UsageRecord(
                date=r["starting_at"][:10],
                user_id=actor["user_id"],
                email=actor["email"],
                name=user["name"],
                group_id=group_id,
                platform="claude",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=r["total_tokens"],
                cost_usd=round(cost_by_key.get(key, 0.0), 6),
                requests=r["requests"],
                model=r["model"],
                detail=r["product"],
            )
        )
    return records
