/**
 * @maref-org/mcp-governance — Type definitions
 */

export type GovernanceMode = "enforcing" | "advisory" | "logging";

export interface GovernanceConfig {
  sidecarUrl: string;
  mode: GovernanceMode;
  failClosed: boolean;
  cacheTtlMs: number;
  cacheBlockTtlMs: number;
}

export interface BackendConfig {
  command: string;
  args: string[];
  env?: Record<string, string>;
}

export interface AppConfig {
  governance: GovernanceConfig;
  backend: BackendConfig;
}

/** Cached decision entry */
export interface CachedDecision {
  verdict: "allow" | "block";
  rule_id: string;
  reason: string;
  risk_score: number;
  expiresAt: number;
}

/** Tool classification for governance interception */
export type ToolCategory = "write" | "execute" | "read" | "other";

export const WRITE_TOOL_NAMES = new Set([
  "write",
  "write_file",
  "create_file",
  "overwrite_file",
  "edit_file",
  "patch_file",
  "apply_patch",
  "filesystem_write",
  "code_write",
]);

export const EXECUTE_TOOL_NAMES = new Set([
  "execute",
  "exec",
  "run",
  "bash",
  "shell",
  "command",
  "run_command",
  "execute_command",
  "code_exec",
  "terminal",
]);
