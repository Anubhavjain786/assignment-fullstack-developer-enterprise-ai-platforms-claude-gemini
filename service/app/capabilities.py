"""Persisted per-group capability controls.

Capabilities: usage-connector, web-search, code-execution.
Store: JSON file (CAPABILITY_STORE, default service/data/capabilities.json),
seeded from the environment's capability_defaults on first start.
When usage-connector is disabled for the effective group, every tool denies.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .permissions import env_config

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = REPO_ROOT / "service" / "data" / "capabilities.json"

CAPABILITIES = ["usage-connector", "web-search", "code-execution"]


def store_path() -> Path:
    return Path(os.environ.get("CAPABILITY_STORE", str(DEFAULT_STORE)))


def _seed_defaults() -> dict:
    cfg = env_config()
    from . import directory as d

    defaults = cfg.get("capability_defaults", {})
    state: dict = {}
    for g in d.group_ids():
        state[g] = {}
        for cap in CAPABILITIES:
            spec = defaults.get(cap, "enabled")
            if isinstance(spec, dict) and "enabled_for" in spec:
                enabled = g in spec["enabled_for"]
            else:
                enabled = spec == "enabled"
            state[g][cap] = {
                "enabled": enabled,
                "updated_at": None,
                "updated_by": None,
            }
    return state


def load_state() -> dict:
    p = store_path()
    if p.exists():
        with open(p) as f:
            return json.load(f)
    state = _seed_defaults()
    save_state(state)
    return state


def save_state(state: dict) -> None:
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(state, f, indent=2)


def reset_for_env() -> dict:
    """Re-seed from current APP_ENV defaults (used in tests/provisioning)."""
    state = _seed_defaults()
    save_state(state)
    return state


def status_for_group(group: str) -> list[dict]:
    state = load_state()
    rows = []
    for cap in CAPABILITIES:
        entry = state.get(group, {}).get(
            cap, {"enabled": True, "updated_at": None, "updated_by": None}
        )
        rows.append(
            {
                "group": group,
                "capability": cap,
                "enabled": entry["enabled"],
                "updated_at": entry["updated_at"],
                "updated_by": entry["updated_by"],
            }
        )
    return rows


def set_capability(group: str, capability: str, enabled: bool, updated_by: str) -> dict:
    if capability not in CAPABILITIES:
        raise ValueError(f"Unknown capability: {capability}")
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    state.setdefault(group, {}).setdefault(
        capability, {"enabled": True, "updated_at": None, "updated_by": None}
    )
    state[group][capability] = {
        "enabled": enabled,
        "updated_at": now,
        "updated_by": updated_by,
    }
    save_state(state)
    return {
        "group": group,
        "capability": capability,
        "enabled": enabled,
        "updated_at": now,
        "updated_by": updated_by,
    }


def usage_connector_enabled(group: str) -> bool:
    state = load_state()
    entry = state.get(group, {}).get("usage-connector")
    if entry is None:
        # Fall back to env defaults without writing.
        seed = _seed_defaults()
        return seed.get(group, {}).get("usage-connector", {}).get("enabled", True)
    return entry["enabled"]
