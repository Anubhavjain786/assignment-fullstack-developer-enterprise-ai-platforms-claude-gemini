/** Live driver: speaks MCP stdio to the built connector, prints a transcript. */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const email = process.env.MERIDIAN_USER_EMAIL ?? "";
const env = process.env.APP_ENV ?? "dev";

async function call(tool, args) {
  const transport = new StdioClientTransport({
    command: "node",
    args: [join(root, "connector", "dist", "index.js")],
    env: { ...process.env, MERIDIAN_USER_EMAIL: email, APP_ENV: env },
  });
  const client = new Client({ name: "transcript-driver", version: "0.0.0" });
  await client.connect(transport);
  try {
    return await client.callTool({ name: tool, arguments: args });
  } finally {
    await client.close();
  }
}

function show(title, res) {
  console.log(`\n### ${title}`);
  console.log(`isError: ${res.isError ?? false}`);
  for (const b of res.content ?? []) {
    const text = String(b.text ?? "");
    try {
      console.log(JSON.stringify(JSON.parse(text), null, 2).slice(0, 1200));
    } catch {
      console.log(text.slice(0, 1200));
    }
  }
}

const [tool, ...rest] = process.argv.slice(2);
const args = rest.length ? JSON.parse(rest.join(" ")) : {};
const res = await call(tool, args);
show(`${tool} as ${email} [${env}]`, res);
