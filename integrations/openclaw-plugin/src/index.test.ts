/**
 * @maref/openclaw-plugin — 单元测试
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { MAREFGovernancePlugin, createMAREFPlugin } from "./index";

// ── Mock @maref-org/sdk ─────────────────────────────────────────────

const mockCheckBeforeWrite = vi.fn();
const mockCheckBeforeExecute = vi.fn();
const mockReportAction = vi.fn().mockResolvedValue(undefined);

vi.mock("@maref-org/sdk", () => {
  return {
    MAREFClient: vi.fn(() => ({
      checkBeforeWrite: mockCheckBeforeWrite,
      checkBeforeExecute: mockCheckBeforeExecute,
      reportAction: mockReportAction,
    })),
    createMAREFClient: vi.fn(),
  };
});

// ── Helper ──────────────────────────────────────────────────────

const defaultContext = {
  agentId: "openclaw-agent",
  sessionId: "test-session",
  config: {},
};

function makeDecision(overrides: Record<string, unknown> = {}) {
  return {
    verdict: "allow",
    rule_id: "MAREF-TEST",
    reason: "test reason",
    risk_score: 0.1,
    decision_latency_ms: 5,
    actor: "openclaw-agent",
    breaker_state: "closed" as const,
    metadata: {},
    ...overrides,
  };
}

// ── 测试 ────────────────────────────────────────────────────────

describe("MAREFGovernancePlugin", () => {
  let plugin: MAREFGovernancePlugin;

  beforeEach(() => {
    vi.clearAllMocks();
    plugin = createMAREFPlugin({ mode: "enforcing" });
  });

  describe("beforeFileWrite", () => {
    it("enforcing 模式 allow → 放行", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeDecision({ verdict: "allow" }));

      const result = await plugin.beforeFileWrite(defaultContext, "/tmp/test.txt");

      expect(result.allowed).toBe(true);
      expect(mockCheckBeforeWrite).toHaveBeenCalledWith({
        file_path: "/tmp/test.txt",
        actor: "openclaw-agent",
        session_id: "test-session",
      });
    });

    it("enforcing 模式 block → 拦截", async () => {
      mockCheckBeforeWrite.mockResolvedValue(
        makeDecision({ verdict: "block", rule_id: "MAREF-POLICY-DENY", risk_score: 0.9 }),
      );

      const result = await plugin.beforeFileWrite(defaultContext, "/etc/passwd");

      expect(result.allowed).toBe(false);
      expect(result.reason).toContain("BLOCKED");
    });

    it("enforcing 模式 hitl_required → 拦截（插件层降级为 block）", async () => {
      mockCheckBeforeWrite.mockResolvedValue(
        makeDecision({ verdict: "hitl_required", rule_id: "MAREF-REQUIRES-HITL" }),
      );

      const result = await plugin.beforeFileWrite(defaultContext, "/etc/config.yaml");

      expect(result.allowed).toBe(false);
      expect(result.reason).toContain("HITL required");
    });

    it("advisory 模式 block → 只警告不拦截", async () => {
      plugin = createMAREFPlugin({ mode: "advisory" });
      mockCheckBeforeWrite.mockResolvedValue(makeDecision({ verdict: "block" }));

      const result = await plugin.beforeFileWrite(defaultContext, "/etc/passwd");

      expect(result.allowed).toBe(true);
    });

    it("logging 模式 → 放行", async () => {
      plugin = createMAREFPlugin({ mode: "logging" });
      mockCheckBeforeWrite.mockResolvedValue(makeDecision({ verdict: "block" }));

      const result = await plugin.beforeFileWrite(defaultContext, "/etc/passwd");

      expect(result.allowed).toBe(true);
    });

    it("fail-closed=false 时 block 只警告不拦截", async () => {
      plugin = createMAREFPlugin({ mode: "enforcing", failClosed: false });
      mockCheckBeforeWrite.mockResolvedValue(makeDecision({ verdict: "block" }));

      const result = await plugin.beforeFileWrite(defaultContext, "/etc/passwd");

      expect(result.allowed).toBe(true);
    });
  });

  describe("beforeCommand", () => {
    it("enforcing 模式 allow → 放行", async () => {
      mockCheckBeforeExecute.mockResolvedValue(makeDecision({ verdict: "allow" }));

      const result = await plugin.beforeCommand(defaultContext, "ls -la");

      expect(result.allowed).toBe(true);
    });

    it("enforcing 模式 block → 拦截", async () => {
      mockCheckBeforeExecute.mockResolvedValue(
        makeDecision({ verdict: "block", risk_score: 0.95 }),
      );

      const result = await plugin.beforeCommand(defaultContext, "rm -rf /");

      expect(result.allowed).toBe(false);
    });

    it("logging 模式不调用 sidecar", async () => {
      plugin = createMAREFPlugin({ mode: "logging" });

      const result = await plugin.beforeCommand(defaultContext, "any command");

      expect(result.allowed).toBe(true);
      expect(mockCheckBeforeExecute).not.toHaveBeenCalled();
    });
  });

  describe("beforeFileRead", () => {
    it("非敏感路径直接放行", async () => {
      const result = await plugin.beforeFileRead(defaultContext, "/tmp/test.txt");

      expect(result.allowed).toBe(true);
      expect(mockCheckBeforeWrite).not.toHaveBeenCalled();
    });

    it("敏感路径调用 sidecar 检查", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeDecision({ verdict: "allow" }));

      const result = await plugin.beforeFileRead(defaultContext, "/etc/passwd");

      expect(result.allowed).toBe(true);
      expect(mockCheckBeforeWrite).toHaveBeenCalled();
    });
  });

  describe("createMAREFPlugin", () => {
    it("工厂函数创建实例", () => {
      const p = createMAREFPlugin();
      expect(p).toBeInstanceOf(MAREFGovernancePlugin);
    });

    it("可传入配置", () => {
      const p = createMAREFPlugin({ mode: "advisory" });
      expect(p.currentMode).toBe("advisory");
    });
  });
});
