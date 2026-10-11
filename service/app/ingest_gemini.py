"""Ingest the Gemini (Google Cloud billing export) rows into UsageRecords.

Native shape: one JSON object per line, one project x day x SKU row.
- sku.description gives model + direction, e.g.
  "Gemini 2.5 Flash Text Input Tokens - Predictions".
- usage.amount (unit "count") is the token count; cost is USD (number).
- Attribution: labels.owner (email) -> user; project.id -> group.
- Day bucket = usage_start_time date ("YYYY-MM-DD HH:MM:SS UTC" -> YYYY-MM-DD).

Mapping decisions:
- Each billing row becomes one record with either input_tokens or
  output_tokens set (the other 0); aggregation sums them. requests=None
  (billing has no request counts) — totals report requests only for Claude.
- Model normalised from the labels.model value when present, else parsed
  from the SKU description.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import directory as directory_mod
from .model import UsageRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GEMINI_FILE = (
    REPO_ROOT
    / "starter-kit"
    / "data"
    / "gemini"
    / "gcp_billing_export_v1_01A2B3_C4D5E6_F7A8B9.jsonl"
)

SKU_RE = re.compile(r"^(Gemini [\d.]+ \w+).*?(Input|Output) Tokens", re.IGNORECASE)


def gemini_file() -> Path:
    return Path(os.environ.get("GEMINI_FILE", str(DEFAULT_GEMINI_FILE)))


def parse_sku(description: str) -> tuple[str, str]:
    """Return (model_slug, direction) e.g. ('gemini-2.5-flash', 'input')."""
    m = SKU_RE.search(description or "")
    if not m:
        raise ValueError(f"Unrecognised SKU description: {description!r}")
    model_part = m.group(1).lower().replace(" ", "-")  # gemini-2.5-flash
    direction = m.group(2).lower()  # input | output
    return model_part, direction


def load_gemini_records() -> list[UsageRecord]:
    records: list[UsageRecord] = []
    with open(gemini_file()) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            labels = {item["key"]: item["value"] for item in r.get("labels", [])}
            owner_email = labels.get("owner", "")
            user = directory_mod.user_by_email(owner_email)
            group_id = project_to_group_safe(r["project"]["id"])
            if user is None or group_id is None:
                continue
            model_slug, direction = parse_sku(r["sku"]["description"])
            model = labels.get("model", model_slug)
            tokens = int(float(r["usage"]["amount"]))
            input_tokens = tokens if direction == "input" else 0
            output_tokens = tokens if direction == "output" else 0
            records.append(
                UsageRecord(
                    date=r["usage_start_time"][:10],
                    user_id=user["user_id"],
                    email=user["email"],
                    name=user["name"],
                    group_id=group_id,
                    platform="gemini",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    cost_usd=round(float(r["cost"]), 6),
                    requests=None,
                    model=model,
                    detail=r["sku"]["description"],
                )
            )
    return records


def project_to_group_safe(project_id: str) -> str | None:
    return directory_mod.project_to_group(project_id)
