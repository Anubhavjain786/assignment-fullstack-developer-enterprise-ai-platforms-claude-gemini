# Meridian Usage Connector — Fullstack Assignment

**Assignment ID: Fullstack-ClaudeGemini-UsageConnector-v1**

Platform usage (Claude + Gemini) ingested into one model, served by an admin
service (Part A), exposed inside the assistant as a scoped MCP connector
packaged for **Gemini CLI** (Part B).

## Quick setup

Prereqs: Python 3.11+, Node 22+.

```bash
# 1. service (Part A)
python -m pip install -r service/requirements.txt
APP_ENV=dev python -m uvicorn app.main:app --app-dir service --port 8000
# admin page: http://localhost:8000/  (switch identity via dropdown)

# 2. connector (Part B) — new terminal, service still running
cd connector && npm install && npm run build && npm test

# 3. provisioning (one command renders + validates all three envs)
python provisioning/render.py --all
python provisioning/render.py --all --check   # what CI runs

# 4. try the connector over real stdio (prod rules)
MERIDIAN_SERVICE_URL=http://localhost:8000 APP_ENV=prod \
  MERIDIAN_USER_EMAIL=priya.nair@meridianls.example \
  node connector/driver.mjs usage_summary '{"period":"2026-09"}'

# 5. full test suite
python -m pytest service/tests -q
npm test --prefix connector
```

Gemini CLI registration (no paid account needed to validate shapes):

```bash
# local dev against this repo (extension manifest at gemini-extension/)
gemini extensions link ./gemini-extension
gemini extensions config meridian-usage   # sets MERIDIAN_USER_EMAIL etc.
# per-env host configs: provisioning/rendered/<env>/gemini-settings.json
```

## Architecture

```
starter-kit/data ──► service (Python/FastAPI, Part A) ◄── admin page (/, X-User-Email)
  directory/            ingest: claude + gemini → UsageRecord
  claude/               enforce: role/visibility/connector-flag per request
  gemini/               persist: service/data/capabilities.json
      ▲
      │ HTTP + X-User-Email passthrough
      │
connector (TS MCP stdio, Part B) ──► Gemini CLI (extension + settings)
  policy.ts: local scope/visibility check BEFORE any fetch
  4 tools → Part A; 403s mapped to contract Denial, never partial data
provisioning/render.py ──► rendered/{dev,staging,prod}/{permissions.json, gemini-settings.json}
```

Data flow for a read: MCP tool → local `checkRead` (role + visibility) →
`GET /api/...` with `X-User-Email` → service re-checks (role, visibility,
`usage-connector` flag) → aggregated JSON. Either layer can deny; denials carry
`{error: "permission_denied", reason, required_scope?}` and no data.

## Mapping decisions (two exports → one model)

Unified record: `{date, user_id, email, name, group_id, platform,
input_tokens, output_tokens, total_tokens, cost_usd, requests, model, detail}`.

- **Claude usage report** (per user×day×product×model): `input_tokens =
  uncached + cache_read + cache_creation(5m + 1h)`. Verified on the fixture:
  `input + output == total_tokens` on all 1346 rows, so we store the reported
  `total_tokens` with confidence. `requests` kept; `detail` = product
  (`chat`/`claude_code`/`cowork`).
- **Claude cost report**: `amount`/`list_amount` are **decimal strings in
  cents** → `cost_usd = amount/100` (e.g. `"88.900050"` = $0.8890005). Join key
  `(user_id, starting_at, product, model)` matches usage rows **1:1** for
  `cost_type=tokens`; the 492 `web_search` rows share the same key space and
  are **added** to the row's cost. Group = directory lookup of `rbac_group_id`
  (0 mismatches vs users' own groups in the fixture).
- **Gemini billing export** (per project×day×SKU): `sku.description` parsed for
  model + direction (`Gemini 2.5 Flash … Input Tokens` → `gemini-2.5-flash`,
  input); `usage.amount` = tokens; `cost` already USD. Each row becomes a
  record with input *or* output set; aggregation sums pairs. Attribution:
  `labels.owner` (email) → user, `project.id` → group (via `groups.json`).
  `requests = null` — billing has no request counts, so `requests` in
  `PlatformTotals` is the Claude sum, `null` for Gemini-only slices.
- **Timestamps**: Claude `starting_at` (RFC 3339) → date; Gemini
  `usage_start_time` (`YYYY-MM-DD HH:MM:SS UTC`) → date. All buckets UTC days.
- **Periods** anchored at the fixture window end **2026-09-28** (exclusive):
  `last_7_days` = 09-21…09-28, `last_30_days` = 08-29…09-28, `2026-W36` = ISO
  Mon–Sun, `2026-09` = calendar month. Unknown identities/SKUs/groups are
  skipped at ingest (fixture has none) and rejected at request time.

## Permission model (and where it is enforced)

Source of truth: `starter-kit/environments/{dev,staging,prod}.yaml`, read at
runtime (`APP_ENV` selects). Matrix:

| | dev | staging | prod |
|---|---|---|---|
| `usage:read` | member, lead, admin; **any group** | lead, admin; **own group** (admins: all) | lead, admin; **own group** (admins: all) |
| `capabilities:write` | lead, admin | lead, admin | **admin only** |
| defaults | all enabled | code-execution off | usage-connector only for it-platform + clinical-operations; code-execution off |

Rules enforced **in code, twice** (never in prompts/UI):

1. **Connector** (`connector/src/policy.ts`): `checkRead`/`checkWrite` run
   *before* any service fetch — a cross-group read never hits the network
   (proven in tests: fetch mock uncalled) and returns the Denial shape.
2. **Service** (`service/app/permissions.py` + routers): re-checks role,
   visibility, and the `usage-connector` flag per request, so direct HTTP
   callers get the same denials. Non-admin writers are confined to their own
   group even in dev.

`usage-connector` disabled for the effective group ⇒ **every tool denies** —
the one exception is the `set_capability` call that re-enables
`usage-connector` itself (otherwise no one could ever recover; documented and
tested). `set_capability` persists `{enabled, updated_at, updated_by}` to
`service/data/capabilities.json`, seeded from the env defaults on first start.

## Platform built for + what ran

**Gemini CLI only** (per scope choice; no Claude packaging in this repo).

- Extension: `gemini-extension/gemini-extension.json` (name `meridian-usage`,
  stdio `mcpServers` with `${extensionPath}`, `settings[]` for
  `MERIDIAN_USER_EMAIL`/`MERIDIAN_SERVICE_URL`, no `trust` key — forbidden in
  extensions) + `GEMINI.md` context file.
- Host registration per env: `provisioning/rendered/<env>/gemini-settings.json`
  (`command: node`, `args`, `cwd`, `env`, `timeout`; merge into
  `~/.gemini/settings.json` or `<project>/.gemini/settings.json`).
- Ran: service on `localhost:8000/8001` (uvicorn), connector as compiled
  `connector/dist/index.js` over real MCP stdio via `connector/driver.mjs`,
  `gemini extensions link/config` shapes validated against docs (Gemini CLI
  binary itself not installed in this sandbox — install/link commands listed in
  transcript). See `transcript.md` for the allowed-read / denied-read /
  denied-write runs.

## Key technical decisions (and why)

- **Python (FastAPI) service + TypeScript connector**, as the brief invites:
  ingest/aggregation is Python-shaped work; the MCP server must be TS for the
  Gemini/Node ecosystem. A shared HTTP contract keeps them honest.
- **MCP SDK v1** (`@modelcontextprotocol/sdk@1.x`, `McpServer.tool` +
  `StdioServerTransport`): stable, documented, Gemini-compatible. v2 was
  evaluated and skipped (newer spec, churn risk for an interview build).
- **Denials as `isError` results with the Denial JSON**, never throws/partials:
  matches the tool contract and is trivially assertable in tests.
- **File-backed capability store** (JSON, not SQLite): zero setup, diffable,
  sufficient for single-instance; the seam (`capabilities.py`) is one module
  to swap for Postgres later.
- **Provisioning as one Python script, stdlib + PyYAML**: renders *and*
  validates; `--check` keeps CI honest about stale hand-edits. Terraform was
  skipped deliberately (local providers add bulk with no real infra here).
- **No ORM / no DB**: the fixture is 2336 records fully in memory; ingest at
  import (~100 ms) beats migrations for this scale.

## Engineering standards

Followed: typed boundaries (dataclasses, zod schemas), contract tests on both
sides of the HTTP seam, permission tests hardest (cross-group, role×env
matrix, connector-off, input validation), CI green on all three jobs, no
hand-edited generated files (`--check` enforces), honest READMEs over clever
code. Skipped (acknowledged): authN beyond the simulated header (see below),
pagination on list endpoints, request logging/PII redaction, multi-instance
store locking, API versioning.

## AI-tool usage

Used AI research agents for Gemini-CLI extension conventions and MCP TS SDK
shapes (both move fast; docs verified, then pinned to what I installed), and
completion-style help for boilerplate (routers, admin JS, zod schemas). I
overruled defaults twice: SDK v2 → v1 for stability, and a proposed
per-row Gemini input+output pre-merge — kept raw rows + aggregate-time sums so
ingest stays lossless. All permission logic and mapping math I wrote and
verified by execution, not by review.

## What I'd do with more time

Real OIDC (header → JWT `sub`), Postgres + Alembic for capabilities/audit log,
per-tool rate limits, `by-week`/`by-group` rollup endpoints with pagination,
extension icons + preinstall capability seeding, `gemini extensions install`
from a versioned git URL in CI, and a second packaging pass for Claude Desktop.

## In the real enterprise version

- **Identity**: directory stub → IdP (Okta/Entra) via OIDC group claims; the
  `X-User-Email` header becomes a verified JWT; `rbac_group_id`/`project.id`
  mappings become SCIM-synced attributes with drift alerts.
- **Connector registry**: side-loaded extension → org-level registry with
  allow-listed servers, signed manifests, per-team enablement, and centrally
  managed `MERIDIAN_USER_EMAIL` binding (no self-assertion).
- **Real usage APIs**: fixture ingest → scheduled pull (Claude Admin API with
  pagination/backfill; BigQuery billing export tail) into a warehouse table;
  anchor "now" replaces the fixed 2026-09-28 window; cost uses contracted rates.
- **Real infra**: file store → Postgres + audit trail; Terraform for service,
  scheduler, and secret bindings; per-env deploy pipelines with the same
  `render --check` gate promoted to policy-as-code (OPA/Conftest).
