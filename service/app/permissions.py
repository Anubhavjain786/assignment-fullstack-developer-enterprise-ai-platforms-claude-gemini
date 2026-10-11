"""Environment-scoped permission model.

Reads starter-kit/environments/{dev,staging,prod}.yaml (APP_ENV selects).
Enforced in code on every request — never in the prompt/UI.

|                   | dev                        | staging      | prod           |
| usage:read roles  | member, lead, admin        | lead, admin  | lead, admin    |
| group visibility  | all                        | own (admins all) | own (admins all) |
| capabilities:write| lead, admin                | lead, admin  | admin only     |
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_DIR = REPO_ROOT / "starter-kit" / "environments"

VALID_ROLES = {"member", "team_lead", "platform_admin"}


def app_env() -> str:
    return os.environ.get("APP_ENV", "dev")


def env_dir() -> Path:
    return Path(os.environ.get("ENVIRONMENTS_DIR", str(DEFAULT_ENV_DIR)))


@lru_cache(maxsize=8)
def env_config(env: str | None = None) -> dict:
    env = env or app_env()
    with open(env_dir() / f"{env}.yaml") as f:
        return yaml.safe_load(f)


def denial(reason: str, required_scope: str | None = None) -> dict:
    body: dict = {"error": "permission_denied", "reason": reason}
    if required_scope:
        body["required_scope"] = required_scope
    return body


def can_read_role(role: str, env: str | None = None) -> bool:
    cfg = env_config(env)
    return role in cfg["scopes"]["usage:read"]["roles"]


def can_write_role(role: str, env: str | None = None) -> bool:
    cfg = env_config(env)
    return role in cfg["scopes"]["capabilities:write"]["roles"]


def group_visibility(env: str | None = None) -> str:
    return env_config(env)["scopes"]["usage:read"]["group_visibility"]


def visible_groups(caller: dict, env: str | None = None) -> list[str] | None:
    """None means all groups (admin with own_group visibility, or dev 'all')."""
    from . import directory as d

    if not can_read_role(caller["role"], env):
        return []
    vis = group_visibility(env)
    if vis == "all":
        return None
    if caller["role"] == "platform_admin":
        return None
    return list(caller["group_ids"])


def check_group_access(
    caller: dict, group_id: str, scope: str, env: str | None = None
) -> dict | None:
    """Return denial dict if access must be refused, else None."""
    from . import directory as d

    if d.group_by_id(group_id) is None:
        return denial(f"Unknown group: {group_id}", scope)
    if not can_read_role(caller["role"], env):
        return denial(
            f"Role '{caller['role']}' may not read usage in environment '{env or app_env()}'.",
            scope,
        )
    vis = visible_groups(caller, env)
    if vis is not None and group_id not in vis:
        return denial(
            f"Group '{group_id}' is outside your access. Team leads may only see their own group.",
            scope,
        )
    return None


def check_write_access(
    caller: dict, group_id: str, env: str | None = None
) -> dict | None:
    from . import directory as d

    if d.group_by_id(group_id) is None:
        return denial("Unknown group: {0}".format(group_id), "capabilities:write")
    if not can_write_role(caller["role"], env):
        return denial(
            f"Role '{caller['role']}' may not change capability controls in environment '{env or app_env()}'.",
            "capabilities:write",
        )
    # Non-admin writers are confined to their own group even where visibility is wider.
    if caller["role"] != "platform_admin" and group_id not in caller["group_ids"]:
        return denial(
            f"Group '{group_id}' is outside your access. You may only change your own group.",
            "capabilities:write",
        )
    return None
