import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "service"))

os.environ.setdefault("APP_ENV", "dev")

from app import capabilities as caps  # noqa: E402
from app import directory as d  # noqa: E402
from app import permissions as perm  # noqa: E402
from app.ingest_claude import cents_str_to_usd, load_claude_records  # noqa: E402
from app.ingest_gemini import load_gemini_records, parse_sku  # noqa: E402
from app.main import app  # noqa: E402
from app.periods import resolve_period  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPABILITY_STORE", str(tmp_path / "caps.json"))
    monkeypatch.setenv("APP_ENV", "dev")
    perm.env_config.cache_clear()
    caps.reset_for_env()
    with TestClient(app) as c:
        yield c


def hdr(email):
    return {"X-User-Email": email}


LEAD = "priya.nair@meridianls.example"  # clinical-operations lead
OTHER_LEAD = "mei.chen@meridianls.example"  # regulatory-affairs lead
ADMIN = "chloe.dubois@meridianls.example"
MEMBER = "daniel.okafor@meridianls.example"


def test_cents_to_usd():
    assert cents_str_to_usd("88.900050") == pytest.approx(0.8890005)
    assert cents_str_to_usd("1.000000") == pytest.approx(0.01)


def test_claude_input_sum_matches_total():
    recs = load_claude_records()
    assert len(recs) == 1346
    for r in recs:
        assert r.input_tokens + r.output_tokens == r.total_tokens
    # web_search cost folded in: spot check a row has cost > 0
    assert sum(r.cost_usd for r in recs) > 0


def test_gemini_sku_parse():
    assert parse_sku("Gemini 2.5 Flash Text Input Tokens - Predictions") == (
        "gemini-2.5-flash",
        "input",
    )
    assert parse_sku("Gemini 2.5 Pro Text Output Tokens - Predictions") == (
        "gemini-2.5-pro",
        "output",
    )


def test_gemini_attribution_covers_all_users():
    recs = load_gemini_records()
    assert len(recs) == 990
    owners = {r.email for r in recs}
    assert len(owners) == 22
    assert all(r.group_id in d.group_ids() for r in recs)


def test_periods_anchor():
    assert resolve_period("last_7_days") == ("2026-09-21", "2026-09-28")
    assert resolve_period("last_30_days") == ("2026-08-29", "2026-09-28")
    assert resolve_period("2026-W36") == ("2026-08-31", "2026-09-07")
    assert resolve_period("2026-09") == ("2026-09-01", "2026-10-01")


def test_summary_shape_and_totals(client):
    r = client.get(
        "/api/usage/summary", params={"group": "clinical-operations", "period": "last_30_days"}, headers=hdr(ADMIN)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["group"] == "clinical-operations"
    assert set(body["period"]) == {"start", "end_exclusive"}
    plats = {p["platform"]: p for p in body["platforms"]}
    assert set(plats) <= {"claude", "gemini"}
    for p in body["platforms"]:
        assert p["input_tokens"] + p["output_tokens"] == p["total_tokens"]
    assert body["totals"]["total_tokens"] == sum(p["total_tokens"] for p in body["platforms"])


def test_team_lead_cannot_read_other_group_in_prod(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    perm.env_config.cache_clear()
    caps.reset_for_env()
    r = client.get(
        "/api/usage/summary",
        params={"group": "finance", "period": "last_30_days"},
        headers=hdr(LEAD),
    )
    assert r.status_code == 403
    assert r.json()["error"] == "permission_denied"


def test_member_denied_in_prod_but_allowed_in_dev(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    perm.env_config.cache_clear()
    caps.reset_for_env()
    r = client.get(
        "/api/usage/summary",
        params={"group": "clinical-operations", "period": "last_30_days"},
        headers=hdr(MEMBER),
    )
    assert r.status_code == 403
    monkeypatch.setenv("APP_ENV", "dev")
    perm.env_config.cache_clear()
    caps.reset_for_env()
    r = client.get(
        "/api/usage/summary",
        params={"group": "clinical-operations", "period": "last_30_days"},
        headers=hdr(MEMBER),
    )
    assert r.status_code == 200


def test_set_capability_needs_admin_in_prod(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    perm.env_config.cache_clear()
    caps.reset_for_env()
    r = client.put(
        "/api/capabilities/finance/web-search",
        json={"enabled": False},
        headers=hdr(OTHER_LEAD),
    )
    assert r.status_code == 403
    assert r.json()["required_scope"] == "capabilities:write"
    # finance has usage-connector disabled by default in prod: the escape hatch
    # is enabling usage-connector itself, then other toggles work.
    r = client.put(
        "/api/capabilities/finance/usage-connector",
        json={"enabled": True},
        headers=hdr(ADMIN),
    )
    assert r.status_code == 200
    r = client.put(
        "/api/capabilities/finance/web-search",
        json={"enabled": False},
        headers=hdr(ADMIN),
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_connector_disabled_denies_reads(client):
    client.put(
        "/api/capabilities/clinical-operations/usage-connector",
        json={"enabled": False},
        headers=hdr(ADMIN),
    )
    r = client.get(
        "/api/usage/summary",
        params={"group": "clinical-operations", "period": "last_30_days"},
        headers=hdr(LEAD),
    )
    assert r.status_code == 403
    assert "usage-connector" in r.json()["reason"]
