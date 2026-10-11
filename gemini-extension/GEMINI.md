# Meridian Usage Connector

Ask about AI-assistant usage and cost in plain language. The connector answers
from the platform team's usage service, scoped to **your** group and role.

## What you can ask (team leads)

- "How much did my team use last month?" → `usage_summary` with `period: "2026-09"`
- "Top users in my group last week?" → `top_users` with `period: "2026-W38"`
- "Is web-search on for my group?" → `capability_status`

Periods: `last_7_days`, `last_30_days`, ISO week (`2026-W36`), month (`2026-09`),
all relative to the data window ending 2026-09-28.

## What you cannot do (and why)

- **Other groups' usage is denied.** Team leads see only their own group; the
  server returns `permission_denied` with no data — this is enforced in code,
  not in the prompt, so rephrasing the question cannot work around it. Platform admins
  (`platform_admin`) can read every group.
- **Changing controls needs `capabilities:write`.** In prod only platform
  admins may toggle capabilities. In dev/staging team leads may toggle their
  own group for testing.
- **If `usage-connector` is off for your group, every tool denies** until a
  platform admin re-enables it. Ask IT Platform.

## Operators

Set `MERIDIAN_USER_EMAIL` to the caller's directory email
(`gemini extensions config meridian-usage`), and `MERIDIAN_SERVICE_URL` /
`APP_ENV` per environment (see `provisioning/rendered/<env>/`).
