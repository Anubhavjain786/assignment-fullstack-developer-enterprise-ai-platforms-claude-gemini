"""Meridian usage service — unified model over Claude + Gemini exports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class UsageRecord:
    date: str  # YYYY-MM-DD (UTC day bucket)
    user_id: str
    email: str
    name: str
    group_id: str
    platform: Literal["claude", "gemini"]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    requests: int | None  # None for Gemini (billing export has no request counts)
    model: str
    detail: str  # product (claude) or SKU description (gemini)
