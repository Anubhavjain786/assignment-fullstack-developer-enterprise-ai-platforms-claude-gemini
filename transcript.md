# Part B transcript — meridian-usage on Gemini CLI (prod rules)

Service: `APP_ENV=prod uvicorn app.main:app --port 8001` (data window ends 2026-09-28).
Connector: `connector/dist/index.js` over real MCP stdio (`connector/driver.mjs`).
Identity per run: `MERIDIAN_USER_EMAIL`. Gemini CLI install/link commands are the
documented ones; the tool calls below are exactly what the assistant would send
once the extension is linked (`gemini extensions link ./gemini-extension`).

## 1. Allowed read — team lead, own group

Lead Priya Nair (clinical-operations) asks: "how much did my team use last month?"
→ `usage_summary(period="2026-09")` (group defaults to caller's own).

```
### usage_summary as priya.nair@meridianls.example [prod]
isError: false
{
  "group": "clinical-operations",
  "period": { "start": "2026-09-01", "end_exclusive": "2026-10-01" },
  "platforms": [
    { "platform": "claude", "requests": 1087, "input_tokens": 4411485,
      "output_tokens": 661995, "total_tokens": 5073480, "cost_usd": 67.95 },
    { "platform": "gemini", "requests": null, "input_tokens": 5001153,
      "output_tokens": 1525880, "total_tokens": 6527033, "cost_usd": 9.72 }
  ],
  "totals": { "total_tokens": 11600513, "cost_usd": 77.67 }
}
```

Assistant reply: "Clinical Operations used ~11.6M tokens in September ($77.67) —
~5.1M Claude, ~6.5M Gemini."

## 2. Denied cross-group read — same lead, another group

"How much did Finance use?" → `usage_summary(group="finance", period="last_30_days")`.
Denied **in the connector before any service call** (no HTTP request made):

```
### usage_summary as priya.nair@meridianls.example [prod]
isError: true
{
  "error": "permission_denied",
  "reason": "Group 'finance' is outside your access. Team leads may only see their own group.",
  "required_scope": "usage:read"
}
```

No usage data is returned. Rephrasing cannot work around it — enforcement is in
`connector/src/policy.ts` + `service/app/permissions.py`, not the prompt.

## 3. Denied write — team lead tries to toggle a control in prod

"Turn off web-search for my group" →
`set_capability(group="clinical-operations", capability="web-search", enabled=false)`:

```
### set_capability as priya.nair@meridianls.example [prod]
isError: true
{
  "error": "permission_denied",
  "reason": "Role 'team_lead' may not change capability controls in environment 'prod'.",
  "required_scope": "capabilities:write"
}
```

In prod only `platform_admin` may change controls (staging/dev allow leads for
their own group — see `provisioning/rendered/*/permissions.json`).

## Registration (Gemini CLI)

```bash
gemini extensions link ./gemini-extension
gemini extensions config meridian-usage   # MERIDIAN_USER_EMAIL=<you>@meridianls.example
# per-env host config: provisioning/rendered/<env>/gemini-settings.json
gemini mcp list                           # meridian-usage: CONNECTED
```

Reproduce any run: start the service, then
`MERIDIAN_SERVICE_URL=http://localhost:8001 APP_ENV=prod
MERIDIAN_USER_EMAIL=<email> node connector/driver.mjs <tool> '<json-args>'`.
