# Note to team leads — usage answers, inside the assistant

Hi all — you asked to see your team's AI usage without leaving the assistant.
It's live: open Gemini CLI and just ask.

## What you can now ask

- "How much did my team use last month?"
- "Who used the most last week?"
- "Is web-search on for my group?"

Weeks (`2026-W38`), months (`2026-09`), "last 7/30 days" all work. Numbers cover
both Claude and Gemini, tokens and cost.

## What you cannot see (and why)

- **Only your own group.** You'll get a clear "permission denied" for anyone
  else's numbers — that's deliberate: usage data is sensitive, and leads see
  their own team only. Platform admins (IT Platform) can see every group.
- **Changing on/off switches is IT-only in prod.** If something your team needs
  is disabled (e.g. the usage connector itself), ask IT Platform to enable it —
  they can flip it for your group in seconds.
- **Data runs to 28 Sep 2026** in this rollout window; "last month" means the
  last 30 days of that window.

## How to ask for more

Reply to this thread with the group + capability you need (e.g. "enable
code-execution for Medical Writing for the Q4 pilot") and we'll action or
explain the constraint. Broader access (cross-group reporting for
multi-team leads) is on the roadmap — tell us your use case and we'll scope it.
