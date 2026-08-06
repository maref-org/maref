#!/usr/bin/env node
/**
 * @maref-org/mcp-governance — CLI Entry Point
 *
 * Usage:
 *   maref-mcp [--config <path>]
 *   MAREF_BACKEND_COMMAND=<cmd> MAREF_BACKEND_ARGS='["..."]' maref-mcp
 *
 * Examples:
 *   maref-mcp --config ./maref-mcp.json
 *   MAREF_BACKEND_COMMAND=npx MAREF_BACKEND_ARGS='["-y","@modelcontextprotocol/server-filesystem","/workspace"]' maref-mcp
 *   MAREF_SIDECAR_URL=http://sidecar:8000 MAREF_MODE=advisory maref-mcp
 */

import { parseArgs } from "node:util";
import { load } from "./config.js";
import { GovernanceProxyServer } from "./server.js";

async function main(): Promise<void> {
  // Parse CLI args
  const args = parseArgs({
    options: {
      config: { type: "string", short: "c" },
    },
    strict: false,
  });

  const configPath = args.values.config as string | undefined;

  let config;
  try {
    config = load(configPath);
  } catch (err) {
    console.error(
      `[maref-mcp] Configuration error: ${err instanceof Error ? err.message : String(err)}`,
    );
    console.error(
      "[maref-mcp] Set MAREF_BACKEND_COMMAND or provide a maref-mcp.json config file.",
    );
    process.exit(1);
  }

  const server = new GovernanceProxyServer(config);

  // Handle graceful shutdown
  const shutdown = async () => {
    console.error("[maref-mcp] Shutting down...");
    await server.shutdown();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
  process.on("uncaughtException", (err) => {
    console.error(`[maref-mcp] Uncaught exception: ${err.message}`);
    shutdown();
  });

  try {
    await server.start();
    console.error("[maref-mcp] Running (awaiting MCP client connection)");
  } catch (err) {
    console.error(
      `[maref-mcp] Startup failed: ${err instanceof Error ? err.message : String(err)}`,
    );
    process.exit(1);
  }
}

main();
