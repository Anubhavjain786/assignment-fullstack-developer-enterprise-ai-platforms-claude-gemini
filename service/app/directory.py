"""Load the directory (users/groups) — stands in for the identity provider."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "starter-kit" / "data" / "directory"


def data_dir() -> Path:
    return Path(os.environ.get("DIRECTORY_DIR", str(DEFAULT_DATA_DIR)))


@lru_cache(maxsize=1)
def _users_doc() -> dict:
    with open(data_dir() / "users.json") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _groups_doc() -> dict:
    with open(data_dir() / "groups.json") as f:
        return json.load(f)


def users() -> list[dict]:
    return _users_doc()["users"]


def groups() -> list[dict]:
    return _groups_doc()["groups"]


def user_by_email(email: str) -> dict | None:
    email = email.strip().lower()
    for u in users():
        if u["email"].lower() == email:
            return u
    return None


def user_by_id(user_id: str) -> dict | None:
    for u in users():
        if u["user_id"] == user_id:
            return u
    return None


def group_by_id(group_id: str) -> dict | None:
    for g in groups():
        if g["group_id"] == group_id:
            return g
    return None


def group_ids() -> list[str]:
    return [g["group_id"] for g in groups()]


def rbac_to_group(rbac_id: str) -> str | None:
    for g in groups():
        if g["claude_rbac_group_id"] == rbac_id:
            return g["group_id"]
    return None


def project_to_group(project_id: str) -> str | None:
    for g in groups():
        if g["gcp_project_id"] == project_id:
            return g["group_id"]
    return None
