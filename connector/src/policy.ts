/** Local policy enforcement: directory + per-environment scopes.
 * Identity is simulated: the server starts as MERIDIAN_USER_EMAIL and takes
 * that user's groups/role from the directory. Enforced here, not in prompts.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";

export const GROUPS = [
  "clinical-operations",
  "regulatory-affairs",
  "finance",
  "hr",
  "medical-writing",
  "it-platform",
] as const;
export type GroupId = (typeof GROUPS)[number];

export const CAPABILITIES = [
  "usage-connector",
  "web-search",
  "code-execution",
] as const;
export type Capability = (typeof CAPABILITIES)[number];

export interface User {
  user_id: string;
  email: string;
  name: string;
  role: "member" | "team_lead" | "platform_admin";
  group_ids: string[];
}

export interface Denial {
  error: "permission_denied";
  reason: string;
  required_scope?: string;
}

function repoRoot(): string {
  // src/policy.ts -> connector/src -> repo root is ../../
  const here = fileURLToPath(import.meta.url);
  return resolve(join(here, "..", "..", ".."));
}

function dataDir(): string {
  return (
    process.env.DIRECTORY_DIR ??
    join(repoRoot(), "starter-kit", "data", "directory")
  );
}

function envDir(): string {
  return (
    process.env.ENVIRONMENTS_DIR ??
    join(repoRoot(), "starter-kit", "environments")
  );
}

export function appEnv(): string {
  return process.env.APP_ENV ?? "dev";
}

export function loadUsers(): User[] {
  const doc = JSON.parse(readFileSync(join(dataDir(), "users.json"), "utf8"));
  return doc.users as User[];
}

export function loadEnvConfig(env?: string): any {
  const name = env ?? appEnv();
  return YAML.parse(readFileSync(join(envDir(), `${name}.yaml`), "utf8"));
}

export function caller(): User {
  const email = (process.env.MERIDIAN_USER_EMAIL ?? "").trim().toLowerCase();
  const user = loadUsers().find((u) => u.email.toLowerCase() === email);
  if (!user) throw new Error(`Unknown MERIDIAN_USER_EMAIL: ${email || "(unset)"}`);
  return user;
}

export function denial(reason: string, required_scope?: string): Denial {
  return required_scope
    ? { error: "permission_denied", reason, required_scope }
    : { error: "permission_denied", reason };
}

/** Local read check. Returns denial or null. Mirrors service/permissions.py. */
export function checkRead(
  user: User,
  group: string,
  cfg?: any,
): Denial | null {
  const conf = cfg ?? loadEnvConfig();
  if (!GROUPS.includes(group as GroupId)) {
    return denial(`Unknown group: ${group}`, "usage:read");
  }
  const roles: string[] = conf.scopes["usage:read"].roles;
  if (!roles.includes(user.role)) {
    return denial(
      `Role '${user.role}' may not read usage in environment '${appEnv()}'.`,
      "usage:read",
    );
  }
  const vis: string = conf.scopes["usage:read"].group_visibility;
  if (vis === "all") return null;
  if (user.role === "platform_admin") return null;
  if (!user.group_ids.includes(group)) {
    return denial(
      `Group '${group}' is outside your access. Team leads may only see their own group.`,
      "usage:read",
    );
  }
  return null;
}

/** Local write check. Returns denial or null. */
export function checkWrite(
  user: User,
  group: string,
  cfg?: any,
): Denial | null {
  const conf = cfg ?? loadEnvConfig();
  if (!GROUPS.includes(group as GroupId)) {
    return denial(`Unknown group: ${group}`, "capabilities:write");
  }
  const roles: string[] = conf.scopes["capabilities:write"].roles;
  if (!roles.includes(user.role)) {
    return denial(
      `Role '${user.role}' may not change capability controls in environment '${appEnv()}'.`,
      "capabilities:write",
    );
  }
  if (user.role !== "platform_admin" && !user.group_ids.includes(group)) {
    return denial(
      `Group '${group}' is outside your access. You may only change your own group.`,
      "capabilities:write",
    );
  }
  return null;
}

export function effectiveGroup(user: User, arg?: string): string {
  return arg ?? user.group_ids[0];
}
