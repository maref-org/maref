/**
 * @maref-org/mcp-governance — MAREF governance middleware
 *
 * Wraps MAREFClient with caching and mode-aware decision making.
 * Reuses the same patterns as the OpenClaw maref-governance plugin.
 */

import {
  MAREFClient,
  type GateDecision,
} from "@maref-org/sdk";
import { DecisionCache } from "./cache.js";
import type { GovernanceConfig } from "./types.js";
import {
  WRITE_TOOL_NAMES,
  EXECUTE_TOOL_NAMES,
  type ToolCategory,
} from "./types.js";

export class Governance {
  private client: MAREFClient;
  private cache: DecisionCache;
  private config: GovernanceConfig;

  constructor(config: GovernanceConfig) {
    this.config = config;
    this.client = new MAREFClient(config.sidecarUrl);
    this.cache = new DecisionCache({
      cacheTtlMs: config.cacheTtlMs,
      cacheBlockTtlMs: config.cacheBlockTtlMs,
    });
  }

  get cacheStats() {
    return this.cache.stats();
  }

  get mode() {
    return this.config.mode;
  }

  /** Classify a tool by name into a governance category */
  static classifyTool(toolName: string): ToolCategory {
    const lower = toolName.toLowerCase();
    if (WRITE_TOOL_NAMES.has(lower)) return "write";
    if (EXECUTE_TOOL_NAMES.has(lower)) return "execute";
    // Normalize underscores to spaces so heuristic regex matches
    const normal = lower.replace(/_/g, " ");
    if (
      /\b(write|create|edit|patch|overwrite|delete|remove|rm|mv|cp)\b/.test(normal)
    )
      return "write";
    if (
      /\b(exec|run|bash|shell|command|terminal|spawn)\b/.test(normal)
    )
      return "execute";
    return "read";
  }

  /** Extract the primary file path or command from tool arguments */
  static extractTarget(
    toolName: string,
    args: Record<string, unknown>,
  ): { filePath?: string; command?: string } {
    const lower = toolName.toLowerCase();

    // Check common path arguments
    const pathKeys = ["file_path", "path", "filePath", "filename", "destination", "target"];
    for (const key of pathKeys) {
      const val = args[key];
      if (typeof val === "string" && val.length > 0) {
        return { filePath: val };
      }
    }

    // Check common command arguments
    const cmdKeys = ["command", "cmd", "shell", "exec", "code"];
    for (const key of cmdKeys) {
      const val = args[key];
      if (typeof val === "string" && val.length > 0) {
        return { command: val };
      }
    }

    return {};
  }

  /**
   * Check if a tool call is allowed by MAREF governance.
   * Returns null if allowed (no block), or a block reason string if blocked.
   */
  async checkToolCall(
    toolName: string,
    args: Record<string, unknown>,
    actor?: string,
    sessionId?: string,
  ): Promise<{
    allowed: boolean;
    blockReason?: string;
    decision?: GateDecision;
  }> {
    // Logging mode: skip all checks
    if (this.config.mode === "logging") {
      return { allowed: true };
    }

    const category = Governance.classifyTool(toolName);
    if (category === "read") {
      return { allowed: true };
    }

    const { filePath, command } = Governance.extractTarget(toolName, args);

    // If we can't extract a path or command, allow and let the backend handle it
    if (!filePath && !command) {
      // For write/execute classified tools with no extractable target,
      // still check but log the issue
      if (category === "write" || category === "execute") {
        console.warn(
          `[maref-mcp] Could not extract target from ${toolName} (category: ${category}), allowing passthrough`,
        );
      }
      return { allowed: true };
    }

    const cacheKey = category === "write"
      ? DecisionCache.key("write", filePath!)
      : DecisionCache.key("execute", command!);

    // Check cache first
    const cached = this.cache.get(cacheKey);
    if (cached) {
      if (cached.verdict === "block") {
        return {
          allowed: false,
          blockReason: `[MAREF] BLOCKED (cached) — rule ${cached.rule_id}: ${cached.reason}`,
          decision: {
            verdict: "block",
            rule_id: cached.rule_id,
            reason: cached.reason,
            risk_score: cached.risk_score,
            decision_latency_ms: 0,
            actor: actor ?? "unknown",
            breaker_state: "closed",
            metadata: { cached: true },
          },
        };
      }
      return { allowed: true };
    }

    // Check with MAREF sidecar
    try {
      let decision: GateDecision;

      if (category === "write" && filePath) {
        decision = await this.client.checkBeforeWrite({
          file_path: filePath,
          actor: actor ?? "mcp-agent",
          session_id: sessionId ?? "default",
        });
      } else if (category === "execute" && command) {
        decision = await this.client.checkBeforeExecute({
          command: command,
          actor: actor ?? "mcp-agent",
          session_id: sessionId ?? "default",
        });
      } else {
        return { allowed: true };
      }

      // Cache non-HITL decisions
      if (decision && decision.verdict !== "hitl_required") {
        this.cache.set(
          cacheKey,
          decision.verdict,
          decision.rule_id,
          decision.reason,
          decision.risk_score,
        );
      }

      // Resolve based on mode
      return this._resolveDecision(decision, `${category} ${filePath ?? command}`);
    } catch (err) {
      // Sidecar unreachable
      if (this.config.failClosed && this.config.mode === "enforcing") {
        return {
          allowed: false,
          blockReason: `[MAREF] FAIL-CLOSED: Sidecar unreachable: ${err instanceof Error ? err.message : String(err)}`,
        };
      }
      console.warn(`[maref-mcp] Sidecar error (fail-open): ${err}`);
      return { allowed: true };
    }
  }

  private _resolveDecision(
    decision: GateDecision,
    operation: string,
  ): { allowed: boolean; blockReason?: string; decision: GateDecision } {
    if (!decision || !decision.verdict) {
      if (this.config.mode === "enforcing" && this.config.failClosed) {
        return {
          allowed: false,
          blockReason: `[MAREF] No valid decision for ${operation}`,
          decision: decision ?? {
            verdict: "block",
            rule_id: "NO-DECISION",
            reason: "No decision returned from sidecar",
            risk_score: 1.0,
            decision_latency_ms: 0,
            actor: "unknown",
            breaker_state: "open",
            metadata: {},
          },
        };
      }
      return { allowed: true, decision };
    }

    switch (this.config.mode) {
      case "advisory": {
        if (decision.verdict === "block") {
          console.warn(
            `[maref-mcp] ADVISORY — would BLOCK ${operation}: ${decision.reason}`,
          );
        }
        return { allowed: true, decision };
      }
      case "enforcing":
      default: {
        if (decision.verdict === "block") {
          const reason = `[MAREF] BLOCKED ${operation} — rule ${decision.rule_id}: ${decision.reason}`;
          if (this.config.failClosed) {
            return { allowed: false, blockReason: reason, decision };
          }
          console.warn(`[maref-mcp] FAIL-OPEN: ${reason}`);
          return { allowed: true, decision };
        }

        if (decision.verdict === "hitl_required") {
          return {
            allowed: false,
            blockReason: `[MAREF] HITL required for ${operation} — contact human operator`,
            decision,
          };
        }

        return { allowed: true, decision };
      }
    }
  }
}
