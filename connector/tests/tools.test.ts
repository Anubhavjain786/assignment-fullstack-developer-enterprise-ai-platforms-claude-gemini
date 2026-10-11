import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createServer } from "../src/index.js";
import { checkRead, checkWrite, loadEnvConfig, loadUsers } from "../src/policy.js";

const LEAD = "priya.nair@meridianls.example"; // clinical-operations
const ADMIN = "chloe.dubois@meridianls.example";
const MEMBER = "daniel.okafor@meridianls.example";

const SUMMARY = {
  group: "clinical-operations",
  period: { start: "2026-08-29", end_exclusive: "2026-09-28" },
  platforms: [],
  totals: { total_tokens: 1, cost_usd: 0.01 },
};

function stubFetch(handler: (url: string) => { status: number; body: any }) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const r = handler(url);
      return { status: r.status, json: async () => r.body };
    }),
  );
  return calls;
}

async function linkedClient() {
  const server = createServer();
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: "test", version: "0.0.0" });
  await Promise.all([server.connect(st), client.connect(ct)]);
  return client;
}

beforeEach(() => {
  process.env.APP_ENV = "prod";
  process.env.MERIDIAN_SERVICE_URL = "http://test-service";
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.MERIDIAN_USER_EMAIL;
});

describe("policy", () => {
  it("loads all three environments", () => {
    for (const env of ["dev", "staging", "prod"]) {
      const cfg = loadEnvConfig(env);
      expect(cfg.scopes["usage:read"].roles).toContain("platform_admin");
    }
  });

  it("denies cross-group read for team lead (no data)", () => {
    const me = loadUsers().find((u) => u.email === LEAD)!;
    const d = checkRead(me, "finance");
    expect(d).not.toBeNull();
    expect(d!.error).toBe("permission_denied");
    expect(d!.required_scope).toBe("usage:read");
  });

  it("denies member reads in prod", () => {
    const me = loadUsers().find((u) => u.email === MEMBER)!;
    expect(checkRead(me, "clinical-operations")?.error).toBe("permission_denied");
  });

  it("denies set_capability for leads in prod with write scope", () => {
    const me = loadUsers().find((u) => u.email === LEAD)!;
    const d = checkWrite(me, "clinical-operations");
    expect(d?.error).toBe("permission_denied");
    expect(d?.required_scope).toBe("capabilities:write");
  });
});

describe("tools over in-memory transport", () => {
  it("allowed read returns service data", async () => {
    process.env.MERIDIAN_USER_EMAIL = LEAD;
    stubFetch(() => ({ status: 200, body: SUMMARY }));
    const client = await linkedClient();
    const res: any = await client.callTool({
      name: "usage_summary",
      arguments: { period: "last_30_days" },
    });
    expect(res.isError).toBeFalsy();
    expect(JSON.parse(res.content[0].text).group).toBe("clinical-operations");
  });

  it("cross-group read denied with no service call and no data", async () => {
    process.env.MERIDIAN_USER_EMAIL = LEAD;
    const calls = stubFetch(() => ({ status: 200, body: SUMMARY }));
    const client = await linkedClient();
    const res: any = await client.callTool({
      name: "usage_summary",
      arguments: { group: "finance", period: "last_30_days" },
    });
    expect(res.isError).toBe(true);
    const body = JSON.parse(res.content[0].text);
    expect(body.error).toBe("permission_denied");
    expect(body.required_scope).toBe("usage:read");
    expect("platforms" in body).toBe(false); // no data leaks
    expect(calls).toHaveLength(0); // denied before any fetch
  });

  it("denied write names the admin scope", async () => {
    process.env.MERIDIAN_USER_EMAIL = LEAD;
    const calls = stubFetch(() => ({ status: 200, body: {} }));
    const client = await linkedClient();
    const res: any = await client.callTool({
      name: "set_capability",
      arguments: { group: "clinical-operations", capability: "web-search", enabled: false },
    });
    expect(res.isError).toBe(true);
    expect(JSON.parse(res.content[0].text).required_scope).toBe(
      "capabilities:write",
    );
    expect(calls).toHaveLength(0);
  });

  it("service 403 (connector disabled) maps to Denial", async () => {
    process.env.MERIDIAN_USER_EMAIL = ADMIN;
    stubFetch(() => ({
      status: 403,
      body: { error: "permission_denied", reason: "usage-connector is disabled for group 'hr'." },
    }));
    const client = await linkedClient();
    const res: any = await client.callTool({
      name: "capability_status",
      arguments: { group: "hr" },
    });
    expect(res.isError).toBe(true);
    expect(JSON.parse(res.content[0].text).error).toBe("permission_denied");
  });

  it("rejects limit > 25 without calling the service", async () => {
    process.env.MERIDIAN_USER_EMAIL = ADMIN;
    const calls = stubFetch(() => ({ status: 200, body: [] }));
    const client = await linkedClient();
    const res: any = await client.callTool({
      name: "top_users",
      arguments: { group: "hr", period: "last_7_days", limit: 26 },
    });
    expect(res.isError).toBe(true);
    expect(calls).toHaveLength(0);
  });
});
