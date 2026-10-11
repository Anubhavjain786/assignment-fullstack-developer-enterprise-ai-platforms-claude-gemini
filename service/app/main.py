"""Meridian usage + admin service (Part A).

Identity is simulated: pass X-User-Email header (or ?as=email for browsers).
Role from the directory decides visibility; enforced in code per request.
"""
from __future__ import annotations

from typing import Optional, Union
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import capabilities as caps
from . import directory as d
from . import permissions as perm
from . import store
from .periods import PERIOD_RE, resolve_period

app = FastAPI(title="Meridian Usage Service", version="1.0.0")


def caller_from(request: Request, x_user_email: Optional[str]) -> Union[dict, JSONResponse, None]:
    email = x_user_email or request.query_params.get("as", "")
    if not email:
        return JSONResponse(
            status_code=401,
            content=perm.denial(
                "No identity supplied. Pass X-User-Email header (or ?as=email)."
            ),
        )
    user = d.user_by_email(email)
    if user is None:
        return JSONResponse(
            status_code=401, content=perm.denial(f"Unknown user: {email}")
        )
    return user


def deny_if_connector_off(group: str) -> Optional[dict]:
    if not caps.usage_connector_enabled(group):
        return perm.denial(
            f"usage-connector is disabled for group '{group}'. Ask a platform admin to re-enable it."
        )
    return None


@app.get("/api/me")
def me(request: Request, x_user_email: Optional[str] = Header(default=None)):
    caller = caller_from(request, x_user_email)
    if isinstance(caller, JSONResponse):
        return caller
    return {
        "user_id": caller["user_id"],
        "email": caller["email"],
        "name": caller["name"],
        "role": caller["role"],
        "group_ids": caller["group_ids"],
        "environment": perm.app_env(),
    }


@app.get("/api/usage/summary")
def usage_summary(
    request: Request,
    period: str = Query(...),
    group: Optional[str] = Query(default=None),
    x_user_email: Optional[str] = Header(default=None),
):
    caller = caller_from(request, x_user_email)
    if isinstance(caller, JSONResponse):
        return caller
    if not PERIOD_RE.match(period or ""):
        return JSONResponse(status_code=400, content={"error": "invalid_period"})
    eff_group = group or caller["group_ids"][0]
    denied = perm.check_group_access(caller, eff_group, "usage:read")
    if denied:
        return JSONResponse(status_code=403, content=denied)
    denied = deny_if_connector_off(eff_group)
    if denied:
        return JSONResponse(status_code=403, content=denied)
    try:
        start, end = resolve_period(period)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_period"})
    records = store.filter_records(group=eff_group, start=start, end_exclusive=end)
    s = store.summarize(records)
    return {
        "group": eff_group,
        "period": {"start": start, "end_exclusive": end},
        "platforms": s["platforms"],
        "totals": s["totals"],
    }


@app.get("/api/usage/top-users")
def usage_top_users(
    request: Request,
    period: str = Query(...),
    group: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
    x_user_email: Optional[str] = Header(default=None),
):
    caller = caller_from(request, x_user_email)
    if isinstance(caller, JSONResponse):
        return caller
    if not PERIOD_RE.match(period or ""):
        return JSONResponse(status_code=400, content={"error": "invalid_period"})
    eff_group = group or caller["group_ids"][0]
    denied = perm.check_group_access(caller, eff_group, "usage:read")
    if denied:
        return JSONResponse(status_code=403, content=denied)
    denied = deny_if_connector_off(eff_group)
    if denied:
        return JSONResponse(status_code=403, content=denied)
    try:
        start, end = resolve_period(period)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_period"})
    records = store.filter_records(group=eff_group, start=start, end_exclusive=end)
    return store.top_users(records, limit)


@app.get("/api/usage/by-week")
def usage_by_week(
    request: Request,
    period: str = Query(...),
    group: Optional[str] = Query(default=None),
    x_user_email: Optional[str] = Header(default=None),
):
    """Usage and cost by week (admin page grouping)."""
    caller = caller_from(request, x_user_email)
    if isinstance(caller, JSONResponse):
        return caller
    if not PERIOD_RE.match(period or ""):
        return JSONResponse(status_code=400, content={"error": "invalid_period"})
    eff_group = group or caller["group_ids"][0]
    denied = perm.check_group_access(caller, eff_group, "usage:read")
    if denied:
        return JSONResponse(status_code=403, content=denied)
    denied = deny_if_connector_off(eff_group)
    if denied:
        return JSONResponse(status_code=403, content=denied)
    try:
        start, end = resolve_period(period)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_period"})
    records = store.filter_records(group=eff_group, start=start, end_exclusive=end)
    return {
        "group": eff_group,
        "period": {"start": start, "end_exclusive": end},
        "weeks": store.weekly_buckets(records),
    }


@app.get("/api/capabilities")
def capability_status(
    request: Request,
    group: Optional[str] = Query(default=None),
    x_user_email: Optional[str] = Header(default=None),
):
    caller = caller_from(request, x_user_email)
    if isinstance(caller, JSONResponse):
        return caller
    eff_group = group or caller["group_ids"][0]
    denied = perm.check_group_access(caller, eff_group, "usage:read")
    if denied:
        return JSONResponse(status_code=403, content=denied)
    denied = deny_if_connector_off(eff_group)
    if denied:
        return JSONResponse(status_code=403, content=denied)
    return caps.status_for_group(eff_group)


@app.put("/api/capabilities/{group}/{capability}")
def set_capability(
    group: str,
    capability: str,
    body: dict,
    request: Request,
    x_user_email: Optional[str] = Header(default=None),
):
    caller = caller_from(request, x_user_email)
    if isinstance(caller, JSONResponse):
        return caller
    denied = perm.check_write_access(caller, group)
    if denied:
        return JSONResponse(status_code=403, content=denied)
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return JSONResponse(
            status_code=400, content={"error": "body must be {enabled: boolean}"}
        )
    # usage-connector disabled denies every tool — except the call that
    # re-enables it (otherwise no one could ever re-enable).
    if not (capability == "usage-connector" and enabled is True):
        blocked = deny_if_connector_off(group)
        if blocked:
            return JSONResponse(status_code=403, content=blocked)
    try:
        return caps.set_capability(group, capability, enabled, caller["email"])
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "unknown_capability"})


ADMIN_HTML = (Path(__file__).parent / "admin.html").read_text()


@app.get("/", response_class=HTMLResponse)
def admin_page():
    return ADMIN_HTML
