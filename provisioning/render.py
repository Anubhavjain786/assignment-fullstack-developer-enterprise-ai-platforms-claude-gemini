#!/usr/bin/env python3
"""One-command provisioning: render + validate per-environment configs.

Usage:
    python provisioning/render.py --all            # render dev/staging/prod + validate
    python provisioning/render.py --all --check    # validate only; fail if stale/invalid (CI)

Reads:  starter-kit/environments/{dev,staging,prod}.yaml (+ directory groups)
Writes: provisioning/rendered/{env}/permissions.json      (permissions manifest)
        provisioning/rendered/{env}/gemini-settings.json  (Gemini CLI host registration)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / "starter-kit" / "environments"
OUT_DIR = ROOT / "provisioning" / "rendered"
ENVS = ["dev", "staging", "prod"]

KNOWN_ROLES = {"member", "team_lead", "platform_admin"}
KNOWN_CAPS = {"usage-connector", "web-search", "code-execution"}

SERVICE_URLS = {
    "dev": "http://localhost:8000",
    "staging": "https://meridian-usage-staging.internal.example",
    "prod": "https://meridian-usage.internal.example",
}


def load_groups() -> list[str]:
    with open(ROOT / "starter-kit" / "data" / "directory" / "groups.json") as f:
        return [g["group_id"] for g in json.load(f)["groups"]]


def resolve_cap_defaults(cfg: dict, groups: list[str]) -> dict:
    defaults = cfg.get("capability_defaults", {})
    matrix = {}
    for g in groups:
        matrix[g] = {}
        for cap in sorted(KNOWN_CAPS):
            spec = defaults.get(cap, "enabled")
            if isinstance(spec, dict) and "enabled_for" in spec:
                matrix[g][cap] = g in spec["enabled_for"]
            else:
                matrix[g][cap] = spec == "enabled"
    return matrix


def render_env(env: str, groups: list[str]) -> dict[str, dict]:
    with open(ENV_DIR / f"{env}.yaml") as f:
        cfg = yaml.safe_load(f)
    server_name = cfg.get("host", {}).get("server_name", f"meridian-usage-{env}")
    permissions = {
        "environment": env,
        "server_name": server_name,
        "scopes": cfg["scopes"],
        "capability_matrix": resolve_cap_defaults(cfg, groups),
    }
    settings = {
        "$comment": (
            f"Gemini CLI host registration for meridian-usage ({env}). "
            "Merge mcpServers into ~/.gemini/settings.json (user) or "
            "<project>/.gemini/settings.json (project). "
            "Each operator sets MERIDIAN_USER_EMAIL to their own directory email; "
            "the connector takes groups/role from the directory for that email."
        ),
        "mcpServers": {
            "meridian-usage": {
                "command": "node",
                "args": ["<CONNECTOR_INSTALL_DIR>/dist/index.js"],
                "cwd": "<CONNECTOR_INSTALL_DIR>",
                "env": {
                    "APP_ENV": env,
                    "MERIDIAN_SERVICE_URL": SERVICE_URLS[env],
                    "MERIDIAN_USER_EMAIL": "$MERIDIAN_USER_EMAIL",
                },
                "timeout": 30000,
            }
        },
    }
    return {"permissions.json": permissions, "gemini-settings.json": settings}


def validate(env: str, docs: dict[str, dict], groups: list[str]) -> list[str]:
    errors = []
    perms = docs["permissions.json"]
    scopes = perms.get("scopes", {})
    for scope in ("usage:read", "capabilities:write"):
        roles = scopes.get(scope, {}).get("roles", [])
        if not roles:
            errors.append(f"{env}: {scope} has no roles")
        for r in roles:
            if r not in KNOWN_ROLES:
                errors.append(f"{env}: unknown role '{r}' in {scope}")
    vis = scopes.get("usage:read", {}).get("group_visibility")
    if vis not in ("all", "own_group"):
        errors.append(f"{env}: bad group_visibility '{vis}'")
    matrix = perms.get("capability_matrix", {})
    if set(matrix) != set(groups):
        errors.append(f"{env}: capability_matrix groups {sorted(matrix)} != {groups}")
    for g, caps in matrix.items():
        if set(caps) != KNOWN_CAPS:
            errors.append(f"{env}/{g}: capabilities {sorted(caps)} != {sorted(KNOWN_CAPS)}")
        for cap, val in caps.items():
            if not isinstance(val, bool):
                errors.append(f"{env}/{g}/{cap}: not a boolean")
    if not perms.get("server_name"):
        errors.append(f"{env}: missing host.server_name")
    mcp = docs["gemini-settings.json"].get("mcpServers", {}).get("meridian-usage", {})
    if mcp.get("command") != "node" or not mcp.get("args"):
        errors.append(f"{env}: mcpServers.meridian-usage needs command=node + args")
    for var in ("APP_ENV", "MERIDIAN_SERVICE_URL", "MERIDIAN_USER_EMAIL"):
        if var not in mcp.get("env", {}):
            errors.append(f"{env}: mcpServers env missing {var}")
    if mcp.get("env", {}).get("APP_ENV") != env:
        errors.append(f"{env}: mcpServers APP_ENV mismatch")
    if "trust" in mcp:
        errors.append(f"{env}: 'trust' must not be set (extensions forbid it)")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="render all environments")
    ap.add_argument("--check", action="store_true", help="validate only; fail if stale")
    ap.add_argument("--env", choices=ENVS, help="render a single environment")
    args = ap.parse_args()
    envs = [args.env] if args.env else ENVS
    groups = load_groups()
    failures: list[str] = []
    for env in envs:
        docs = render_env(env, groups)
        failures.extend(validate(env, docs, groups))
        out = OUT_DIR / env
        if args.check:
            for name, doc in docs.items():
                p = out / name
                if not p.exists():
                    failures.append(f"{env}/{name}: missing rendered file")
                    continue
                with open(p) as f:
                    if json.load(f) != doc:
                        failures.append(
                            f"{env}/{name}: stale — re-run render.py --all"
                        )
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, doc in docs.items():
                with open(out / name, "w") as f:
                    json.dump(doc, f, indent=2)
                    f.write("\n")
                print(f"rendered {out / name}")
    if failures:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in failures:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("provisioning OK:", ", ".join(envs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
