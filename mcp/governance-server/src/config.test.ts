/**
 * @maref-org/mcp-governance — Configuration loader tests
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Shared mock files map — hoisted so it's available in both the mock factory and tests
const { mockFiles } = vi.hoisted(() => {
  const mockFiles = new Map<string, string>();
  return { mockFiles };
});

// Mock fs module
vi.mock("node:fs", () => {
  return {
    readFileSync: vi.fn((path: string, _encoding?: string) => {
      const content = mockFiles.get(path);
      if (content === undefined) {
        const err: NodeJS.ErrnoException = new Error(`ENOENT: ${path}`);
        err.code = "ENOENT";
        throw err;
      }
      return content;
    }),
    existsSync: vi.fn((path: string) => mockFiles.has(path)),
  };
});

// Mock process.env
const ORIGINAL_ENV = { ...process.env };

function setEnv(key: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }
}

describe("config loader", () => {
  beforeEach(() => {
    // Clear all MAREF-related env vars
    for (const key of Object.keys(process.env)) {
      if (key.startsWith("MAREF_")) {
        delete process.env[key];
      }
    }

    // Clear mock files
    mockFiles.clear();
  });

  afterEach(() => {
    // Restore env
    process.env = { ...ORIGINAL_ENV };
    vi.restoreAllMocks();
  });

  it("uses defaults when no config is provided", async () => {
    setEnv("MAREF_BACKEND_COMMAND", "npx");
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["-y", "server"]));

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.sidecarUrl).toBe("http://localhost:8000");
    expect(config.governance.mode).toBe("enforcing");
    expect(config.governance.failClosed).toBe(true);
    expect(config.governance.cacheTtlMs).toBe(30_000);
    expect(config.governance.cacheBlockTtlMs).toBe(60_000);
    expect(config.backend.command).toBe("npx");
    expect(config.backend.args).toEqual(["-y", "server"]);
  });

  it("loads from a JSON config file path", async () => {
    const jsonConfig = JSON.stringify({
      governance: {
        sidecarUrl: "http://sidecar:8080",
        mode: "advisory",
        failClosed: false,
      },
      backend: {
        command: "node",
        args: ["server.js"],
      },
    });
    mockFiles.set("/etc/maref-mcp.json", jsonConfig);

    const { load } = await import("./config.js");
    const config = load("/etc/maref-mcp.json");

    expect(config.governance.sidecarUrl).toBe("http://sidecar:8080");
    expect(config.governance.mode).toBe("advisory");
    expect(config.governance.failClosed).toBe(false);
    expect(config.backend.command).toBe("node");
    expect(config.backend.args).toEqual(["server.js"]);
  });

  it("loads from MAREF_MCP_CONFIG env var pointing to a file", async () => {
    const jsonConfig = JSON.stringify({
      governance: {
        sidecarUrl: "http://sidecar:9000",
        cacheTtlMs: 10_000,
      },
      backend: {
        command: "python3",
        args: ["-m", "mcp_server"],
      },
    });
    mockFiles.set("/tmp/maref.json", jsonConfig);
    setEnv("MAREF_MCP_CONFIG", "/tmp/maref.json");

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.sidecarUrl).toBe("http://sidecar:9000");
    expect(config.governance.cacheTtlMs).toBe(10_000);
    expect(config.backend.command).toBe("python3");
  });

  it("loads from MAREF_MCP_CONFIG env var as inline JSON", async () => {
    const inlineJson = JSON.stringify({
      governance: { mode: "logging" },
      backend: { command: "go", args: ["run", "main.go"] },
    });
    setEnv("MAREF_MCP_CONFIG", inlineJson);

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.mode).toBe("logging");
    expect(config.backend.command).toBe("go");
  });

  it("loads from default ./maref-mcp.json in cwd", async () => {
    const jsonConfig = JSON.stringify({
      governance: { sidecarUrl: "http://default:7000" },
      backend: { command: "deno", args: ["run", "mod.ts"] },
    });
    // The default path is resolve("maref-mcp.json") which uses cwd
    const cwd = process.cwd();
    mockFiles.set(`${cwd}/maref-mcp.json`, jsonConfig);

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.sidecarUrl).toBe("http://default:7000");
    expect(config.backend.command).toBe("deno");
  });

  it("applies environment variable overrides", async () => {
    setEnv("MAREF_SIDECAR_URL", "http://env:6000");
    setEnv("MAREF_MODE", "advisory");
    setEnv("MAREF_FAIL_CLOSED", "false");
    setEnv("MAREF_CACHE_TTL", "5000");
    setEnv("MAREF_CACHE_BLOCK_TTL", "15000");
    setEnv("MAREF_BACKEND_COMMAND", "bun");
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["start"]));

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.sidecarUrl).toBe("http://env:6000");
    expect(config.governance.mode).toBe("advisory");
    expect(config.governance.failClosed).toBe(false);
    expect(config.governance.cacheTtlMs).toBe(5000);
    expect(config.governance.cacheBlockTtlMs).toBe(15000);
    expect(config.backend.command).toBe("bun");
    expect(config.backend.args).toEqual(["start"]);
  });

  it("env vars override file config values", async () => {
    const jsonConfig = JSON.stringify({
      governance: {
        sidecarUrl: "http://file:3000",
        mode: "logging",
      },
      backend: {
        command: "node",
        args: ["file.js"],
      },
    });
    mockFiles.set("/tmp/override-test.json", jsonConfig);
    setEnv("MAREF_MCP_CONFIG", "/tmp/override-test.json");
    setEnv("MAREF_SIDECAR_URL", "http://override:3000");
    setEnv("MAREF_MODE", "enforcing");

    const { load } = await import("./config.js");
    const config = load();

    // Env vars should win over file
    expect(config.governance.sidecarUrl).toBe("http://override:3000");
    expect(config.governance.mode).toBe("enforcing");
    // File values not overridden by env should remain
    expect(config.backend.command).toBe("node");
    expect(config.backend.args).toEqual(["file.js"]);
  });

  it("defaults unknown mode to enforcing", async () => {
    setEnv("MAREF_MODE", "invalid-mode");
    setEnv("MAREF_BACKEND_COMMAND", "echo");
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["hi"]));

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.mode).toBe("enforcing");
  });

  it("throws if no backend command is configured", async () => {
    const { load } = await import("./config.js");
    expect(() => load()).toThrow("No backend command configured");
  });

  it("loads sidecar URL from MAREF_SIDECAR_URL env var", async () => {
    setEnv("MAREF_SIDECAR_URL", "http://custom-sidecar:9999");
    setEnv("MAREF_BACKEND_COMMAND", "npx");
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["server"]));

    const { load } = await import("./config.js");
    const config = load();

    expect(config.governance.sidecarUrl).toBe("http://custom-sidecar:9999");
  });

  it("handles MAREF_FAIL_CLOSED as boolean string", async () => {
    setEnv("MAREF_FAIL_CLOSED", "false");
    setEnv("MAREF_BACKEND_COMMAND", "npx");
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["server"]));

    const { load } = await import("./config.js");
    const config = load();
    expect(config.governance.failClosed).toBe(false);

    setEnv("MAREF_FAIL_CLOSED", "true");
    const { load: load2 } = await import("./config.js");
    const config2 = load2();
    expect(config2.governance.failClosed).toBe(true);
  });

  it("handles MAREF_BACKEND_ARGS as JSON array", async () => {
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]));
    setEnv("MAREF_BACKEND_COMMAND", "npx");

    const { load } = await import("./config.js");
    const config = load();
    expect(config.backend.args).toEqual(["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]);
  });

  it("handles MAREF_MCP_CONFIG as inline JSON when starts with {", async () => {
    setEnv("MAREF_MCP_CONFIG", '{"governance":{"mode":"advisory"},"backend":{"command":"node","args":["app.js"]}}');

    const { load } = await import("./config.js");
    const config = load();
    expect(config.governance.mode).toBe("advisory");
    expect(config.backend.command).toBe("node");
  });

  it("gracefully handles invalid MAREF_MCP_CONFIG inline JSON", async () => {
    setEnv("MAREF_MCP_CONFIG", "{invalid json}");
    setEnv("MAREF_BACKEND_COMMAND", "npx");
    setEnv("MAREF_BACKEND_ARGS", JSON.stringify(["server"]));

    const { load } = await import("./config.js");
    // Should not throw, just log warning and use defaults/env
    const config = load();
    expect(config.governance.sidecarUrl).toBe("http://localhost:8000");
  });
});
