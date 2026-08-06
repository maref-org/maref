/**
 * @maref-org/mcp-governance — MCP Governance Proxy Server
 *
 * Starts a backend MCP server as a subprocess and wraps it with MAREF
 * governance guardrails. Clients connect to this server instead of the
 * backend directly. All tool calls are inspected, and write/execute
 * operations are checked against the MAREF sidecar before forwarding.
 *
 * Usage:
 *   maref-mcp --config maref-mcp.json
 *
 * Config (maref-mcp.json):
 *   {
 *     "governance": { "sidecarUrl": "...", "mode": "enforcing", ... },
 *     "backend": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"] }
 *   }
 */

import { spawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import process from "node:process";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import {
  ListToolsRequestSchema,
  ListToolsResultSchema,
  CallToolRequestSchema,
  CallToolResultSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { Governance } from "./governance.js";
import type { AppConfig } from "./types.js";

// ── Type helpers for MCP tool definitions ────────────────────────────

interface ToolDefinition {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

enum McpErrorCode {
  InvalidParams = -32602,
  InternalError = -32603,
}

// ── MCP Proxy Server ─────────────────────────────────────────────────

export class GovernanceProxyServer {
  private server: Server;
  private client?: Client;
  private backendProcess?: ChildProcess;
  private backendTools: ToolDefinition[] = [];
  private governance: Governance;
  private abortController = new AbortController();

  constructor(private config: AppConfig) {
    this.governance = new Governance(config.governance);
    this.server = new Server(
      { name: "maref-governance", version: "0.1.0" },
      { capabilities: { tools: {} } },
    );
    this._setupHandlers();
  }

  async start(): Promise<void> {
    await this._startBackend();
    await this._discoverTools();
    await this._startFrontend();
  }

  async shutdown(): Promise<void> {
    this.abortController.abort();
    try {
      await this.client?.close();
    } catch { /* ignore */ }
    if (this.backendProcess && !this.backendProcess.killed) {
      this.backendProcess.kill("SIGTERM");
      setTimeout(() => {
        if (this.backendProcess && !this.backendProcess.killed) {
          this.backendProcess.kill("SIGKILL");
        }
      }, 5000);
    }
    await this.server.close();
  }

  // ── Private: Backend Management ──────────────────────────────────

  private async _startBackend(): Promise<void> {
    const { command, args, env } = this.config.backend;
    console.error(`[maref-mcp] Starting backend: ${command} ${args.join(" ")}`);

    const transport = new StdioClientTransport({
      command,
      args,
      env: env
        ? { ...process.env as Record<string, string>, ...env }
        : undefined,
    });

    this.client = new Client(
      {
        name: "maref-governance-client",
        version: "0.1.0",
      },
      { capabilities: {} },
    );

    await this.client.connect(transport);
    console.error("[maref-mcp] Connected to backend MCP server");
  }

  private async _discoverTools(): Promise<void> {
    if (!this.client) throw new Error("Backend client not initialized");

    const result = await this.client.request(
      { method: "tools/list" },
      ListToolsResultSchema,
    );

    this.backendTools = (result.tools ?? []).map((t: Record<string, unknown>) => ({
      name: t.name as string,
      description: t.description as string | undefined,
      inputSchema: t.inputSchema as Record<string, unknown>,
    }));

    console.error(
      `[maref-mcp] Discovered ${this.backendTools.length} tools from backend`,
    );
  }

  // ── Private: Frontend Handlers ───────────────────────────────────

  private _setupHandlers(): void {
    // tools/list — forward backend tools with governance notice
    this.server.setRequestHandler(
      ListToolsRequestSchema,
      async () => {
        const tools = this.backendTools.map((tool) => ({
          ...tool,
          description: tool.description
            ? `[Governed by MAREF] ${tool.description}`
            : "[Governed by MAREF] Tool calls are checked by MAREF governance sidecar",
        }));

        // Add governance introspection tool
        tools.push({
          name: "maref_governance_status",
          description:
            "Get the current MAREF governance status, including mode, cache stats, and sidecar status",
          inputSchema: {
            type: "object",
            properties: {},
            required: [] as string[],
          },
        });

        return { tools };
      },
    );

    // tools/call — intercept and govern
    this.server.setRequestHandler(
      CallToolRequestSchema,
      async (request) => {
        const params = request.params;
        const name = params.name;
        const args = params.arguments ?? {};

        // Handle governance introspection tool
        if (name === "maref_governance_status") {
          return {
            content: [
              {
                type: "text" as const,
                text: JSON.stringify(
                  {
                    mode: this.governance.mode,
                    cache: this.governance.cacheStats,
                    sidecarUrl: this.config.governance.sidecarUrl,
                    failClosed: this.config.governance.failClosed,
                  },
                  null,
                  2,
                ),
              },
            ],
          };
        }

        // Check governance
        const check = await this.governance.checkToolCall(
          name,
          args,
          "mcp-agent",
          "default",
        );

        if (!check.allowed) {
          return {
            content: [
              {
                type: "text" as const,
                text: check.blockReason ?? "[MAREF] Operation blocked by governance policy",
              },
            ],
            isError: true,
          };
        }

        // Forward to backend
        if (!this.client) {
          return {
            content: [
              {
                type: "text" as const,
                text: "[MAREF] Backend MCP server not connected",
              },
            ],
            isError: true,
          };
        }

        try {
          const result = await this.client.request(
            {
              method: "tools/call",
              params: { name, arguments: args },
            },
            CallToolResultSchema,
          );

          return result;
        } catch (err: unknown) {
          return {
            content: [
              {
                type: "text" as const,
                text: `Backend error: ${err instanceof Error ? err.message : String(err)}`,
              },
            ],
            isError: true,
          };
        }
      },
    );
  }

  private async _startFrontend(): Promise<void> {
    const transport = new StdioServerTransport();
    console.error("[maref-mcp] Starting MCP governance server on stdio");
    await this.server.connect(transport);
  }
}
