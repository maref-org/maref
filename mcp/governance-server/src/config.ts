/**
 * @maref-org/mcp-governance — Configuration loader
 *
 * Loads config from:
 *   1. CLI arguments (--config <path>)
 *   2. MAREF_MCP_CONFIG env var (JSON string or file path)
 *   3. ./maref-mcp.json (default)
 *   4. Environment variable overrides (MAREF_SIDECAR_URL, MAREF_MODE, etc.)
 */

import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import type { AppConfig, GovernanceConfig, BackendConfig } from "./types.js";

const DEFAULT_CONFIG: AppConfig = {
  governance: {
    sidecarUrl: "http://localhost:8000",
    mode: "enforcing",
    failClosed: true,
    cacheTtlMs: 30_000,
    cacheBlockTtlMs: 60_000,
  },
  backend: {
    command: "",
    args: [],
  },
};

function loadJsonFile(path: string): Record<string, unknown> {
  const resolved = resolve(path);
  const raw = readFileSync(resolved, "utf-8");
  return JSON.parse(raw);
}

function resolveConfigPath(providedPath?: string): string | null {
  // 1. CLI --config argument
  if (providedPath) return providedPath;

  // 2. MAREF_MCP_CONFIG env var
  const envConfig = process.env.MAREF_MCP_CONFIG;
  if (envConfig) {
    // Could be a JSON string or a file path
    if (envConfig.startsWith("{") || envConfig.startsWith("[")) {
      return null; // Inline JSON, handled in load()
    }
    return envConfig;
  }

  // 3. ./maref-mcp.json
  const defaultPath = resolve("maref-mcp.json");
  if (existsSync(defaultPath)) return defaultPath;

  return null;
}

export function load(providedConfigPath?: string): AppConfig {
  const config: AppConfig = structuredClone(DEFAULT_CONFIG);
  const mergedGovernance: Partial<GovernanceConfig> = {};
  const mergedBackend: Partial<BackendConfig> = {};

  // Step 1: Load from JSON file
  const configPath = resolveConfigPath(providedConfigPath);
  if (configPath) {
    const fileConfig = loadJsonFile(configPath);
    if (typeof fileConfig.governance === "object" && fileConfig.governance) {
      Object.assign(mergedGovernance, fileConfig.governance);
    }
    if (typeof fileConfig.backend === "object" && fileConfig.backend) {
      Object.assign(mergedBackend, fileConfig.backend);
    }
  }

  // Step 2: MAREF_MCP_CONFIG as inline JSON
  const envConfig = process.env.MAREF_MCP_CONFIG;
  if (envConfig && (envConfig.startsWith("{") || envConfig.startsWith("["))) {
    try {
      const parsed = JSON.parse(envConfig);
      if (typeof parsed.governance === "object" && parsed.governance) {
        Object.assign(mergedGovernance, parsed.governance);
      }
      if (typeof parsed.backend === "object" && parsed.backend) {
        Object.assign(mergedBackend, parsed.backend);
      }
    } catch {
      console.error("[maref-mcp] Invalid MAREF_MCP_CONFIG JSON");
    }
  }

  // Step 3: Environment variable overrides
  if (process.env.MAREF_SIDECAR_URL) mergedGovernance.sidecarUrl = process.env.MAREF_SIDECAR_URL;
  if (process.env.MAREF_MODE) mergedGovernance.mode = process.env.MAREF_MODE as GovernanceConfig["mode"];
  if (process.env.MAREF_FAIL_CLOSED) mergedGovernance.failClosed = process.env.MAREF_FAIL_CLOSED === "true";
  if (process.env.MAREF_CACHE_TTL) mergedGovernance.cacheTtlMs = Number(process.env.MAREF_CACHE_TTL);
  if (process.env.MAREF_CACHE_BLOCK_TTL) mergedGovernance.cacheBlockTtlMs = Number(process.env.MAREF_CACHE_BLOCK_TTL);
  if (process.env.MAREF_BACKEND_COMMAND) mergedBackend.command = process.env.MAREF_BACKEND_COMMAND;
  if (process.env.MAREF_BACKEND_ARGS) mergedBackend.args = JSON.parse(process.env.MAREF_BACKEND_ARGS);

  // Merge into config
  config.governance = { ...DEFAULT_CONFIG.governance, ...mergedGovernance };
  config.backend = { ...DEFAULT_CONFIG.backend, ...mergedBackend };

  // Validate
  const gov = config.governance as GovernanceConfig;
  if (!["enforcing", "advisory", "logging"].includes(gov.mode)) {
    console.warn(`[maref-mcp] Unknown mode '${gov.mode}', defaulting to 'enforcing'`);
    gov.mode = "enforcing";
  }

  const backend = config.backend as BackendConfig;
  if (!backend.command) {
    throw new Error(
      "No backend command configured. Set MAREF_BACKEND_COMMAND or provide a maref-mcp.json with backend.command.",
    );
  }

  return config;
}
