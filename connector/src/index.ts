#!/usr/bin/env node
/** Meridian usage MCP connector (Part B) — stdio server with 4 tools.
 *
 * Identity: MERIDIAN_USER_EMAIL (server starts as this user).
 * Enforcement: local scope/visibility checks (policy.ts) + service-side
 * re-enforcement; any 403 becomes the contract Denial shape with NO data.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  CAPABILITIES,
  GROUPS,
  caller,
  checkRead,
  checkWrite,
  denial,
  effectiveGroup,
  type Denial,
} from "./policy.js";
import { serviceGet, servicePut } from "./serviceClient.js";

const Period = z
  .string()
  .regex(/^(last_7_days|last_30_days|\d{4}-W\d{2}|\d{4}-\d{2})$/, "Invalid period");
const GroupArg = z.enum(GROUPS as unknown as [string, ...string[]]).optional();
const CapabilityArg = z.enum(CAPABILITIES as unknown as [string, ...string[]]);

function denialResult(d: Denial) {
  // Contract: denial is an error result carrying the Denial shape, no data.
  return {
    content: [{ type: "text" as const, text: JSON.stringify(d) }],
    isError: true,
  };
}

function okResult(body: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(body) }] };
}

function mapService(status: number, body: any) {
  if (status === 403 && body?.error === "permission_denied") {
    return denialResult(body as Denial);
  }
  if (status >= 400) {
    return {
      content: [
        { type: "text" as const, text: JSON.stringify(body) },
      ],
      isError: true,
    };
  }
  return okResult(body);
}

export function createServer() {
  const me = caller();
  const server = new McpServer({
    name: "meridian-usage",
    version: "1.0.0",
  });

  server.tool(
    "usage_summary",
    "Usage and cost by platform for a group and period. Group defaults to the caller's own group.",
    { group: GroupArg, period: Period },
    async ({ group, period }) => {
      const g = effectiveGroup(me, group);
      const blocked = checkRead(me, g);
      if (blocked) return denialResult(blocked);
      const { status, body } = await serviceGet("/api/usage/summary", {
        group: g,
        period,
      });
      return mapService(status, body);
    },
  );

  server.tool(
    "top_users",
    "Top users by total tokens for a group and period. Group defaults to the caller's own group.",
    {
      group: GroupArg,
      period: Period,
      limit: z.number().int().min(1).max(25).default(10),
    },
    async ({ group, period, limit }) => {
      const g = effectiveGroup(me, group);
      const blocked = checkRead(me, g);
      if (blocked) return denialResult(blocked);
      const { status, body } = await serviceGet("/api/usage/top-users", {
        group: g,
        period,
        limit,
      });
      return mapService(status, body);
    },
  );

  server.tool(
    "capability_status",
    "Current enable/disable state of each capability for a group.",
    { group: GroupArg },
    async ({ group }) => {
      const g = effectiveGroup(me, group);
      const blocked = checkRead(me, g);
      if (blocked) return denialResult(blocked);
      const { status, body } = await serviceGet("/api/capabilities", {
        group: g,
      });
      return mapService(status, body);
    },
  );

  server.tool(
    "set_capability",
    "Enable or disable a capability for a group. Needs capabilities:write scope.",
    { group: z.enum(GROUPS as unknown as [string, ...string[]]), capability: CapabilityArg, enabled: z.boolean() },
    async ({ group, capability, enabled }) => {
      const blocked = checkWrite(me, group);
      if (blocked) return denialResult(blocked);
      const { status, body } = await servicePut(
        `/api/capabilities/${group}/${capability}`,
        { enabled },
      );
      return mapService(status, body);
    },
  );

  return server;
}

async function main() {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(
    `meridian-usage connector up (env=${process.env.APP_ENV ?? "dev"})`,
  );
}

// Only auto-run when executed directly, not when imported by tests.
const isDirect = process.argv[1]?.endsWith("index.ts") || process.argv[1]?.endsWith("index.js");
if (isDirect) {
  main().catch((err) => {
    console.error(denial(`Connector failed to start: ${String(err)}`));
    process.exit(1);
  });
}
