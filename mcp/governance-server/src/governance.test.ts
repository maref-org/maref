import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Governance } from "./governance.js";

// Mock @maref-org/sdk
const mockCheckBeforeWrite = vi.fn();
const mockCheckBeforeExecute = vi.fn();

vi.mock("@maref-org/sdk", () => ({
  MAREFClient: vi.fn().mockImplementation(() => ({
    checkBeforeWrite: mockCheckBeforeWrite,
    checkBeforeExecute: mockCheckBeforeExecute,
    reportAction: vi.fn().mockResolvedValue(undefined),
    getGovernanceStatus: vi.fn(),
  })),
}));

function makeAllowDecision(overrides = {}) {
  return {
    verdict: "allow",
    rule_id: "ALLOW-TEST",
    reason: "Policy allows this operation",
    risk_score: 0.1,
    decision_latency_ms: 5,
    actor: "test-agent",
    breaker_state: "closed",
    metadata: {},
    ...overrides,
  };
}

function makeBlockDecision(overrides = {}) {
  return {
    verdict: "block",
    rule_id: "BLOCK-TEST",
    reason: "Policy blocks this operation",
    risk_score: 0.9,
    decision_latency_ms: 5,
    actor: "test-agent",
    breaker_state: "closed",
    metadata: {},
    ...overrides,
  };
}

function makeHITLDecision(overrides = {}) {
  return {
    verdict: "hitl_required",
    rule_id: "HITL-TEST",
    reason: "Human review required",
    risk_score: 0.7,
    decision_latency_ms: 5,
    actor: "test-agent",
    breaker_state: "closed",
    metadata: {},
    ...overrides,
  };
}

const defaultConfig = {
  sidecarUrl: "http://localhost:8000",
  mode: "enforcing" as const,
  failClosed: true,
  cacheTtlMs: 60_000,
  cacheBlockTtlMs: 120_000,
};

describe("Governance.classifyTool", () => {
  it("classifies write tools", () => {
    expect(Governance.classifyTool("write")).toBe("write");
    expect(Governance.classifyTool("write_file")).toBe("write");
    expect(Governance.classifyTool("apply_patch")).toBe("write");
    expect(Governance.classifyTool("create_file")).toBe("write");
    expect(Governance.classifyTool("delete_file")).toBe("write");
  });

  it("classifies execute tools", () => {
    expect(Governance.classifyTool("bash")).toBe("execute");
    expect(Governance.classifyTool("execute")).toBe("execute");
    expect(Governance.classifyTool("run_command")).toBe("execute");
    expect(Governance.classifyTool("terminal")).toBe("execute");
  });

  it("classifies read tools as other", () => {
    expect(Governance.classifyTool("read")).toBe("read");
    expect(Governance.classifyTool("list_files")).toBe("read");
    expect(Governance.classifyTool("search")).toBe("read");
    expect(Governance.classifyTool("think")).toBe("read");
  });

  it("is case insensitive", () => {
    expect(Governance.classifyTool("Write")).toBe("write");
    expect(Governance.classifyTool("BASH")).toBe("execute");
    expect(Governance.classifyTool("Read")).toBe("read");
  });
});

describe("Governance.extractTarget", () => {
  it("extracts file_path from args", () => {
    const result = Governance.extractTarget("write", { file_path: "/tmp/test.txt" });
    expect(result.filePath).toBe("/tmp/test.txt");
  });

  it("extracts command from args", () => {
    const result = Governance.extractTarget("bash", { command: "ls -la" });
    expect(result.command).toBe("ls -la");
  });

  it("returns empty object when no target found", () => {
    const result = Governance.extractTarget("think", { thought: "hmm" });
    expect(result.filePath).toBeUndefined();
    expect(result.command).toBeUndefined();
  });
});

describe("Governance", () => {
  let gov: Governance;

  beforeEach(() => {
    vi.clearAllMocks();
    gov = new Governance(defaultConfig);
  });

  describe("logging mode", () => {
    it("passes through all tool calls without checking sidecar", async () => {
      gov = new Governance({ ...defaultConfig, mode: "logging" });
      const result = await gov.checkToolCall("bash", { command: "rm -rf /" });
      expect(result.allowed).toBe(true);
      expect(mockCheckBeforeExecute).not.toHaveBeenCalled();
    });
  });

  describe("advisory mode", () => {
    it("passes through even when sidecar blocks", async () => {
      gov = new Governance({ ...defaultConfig, mode: "advisory" });
      mockCheckBeforeExecute.mockResolvedValue(makeBlockDecision());
      const result = await gov.checkToolCall("bash", { command: "rm -rf /" });
      expect(result.allowed).toBe(true);
    });
  });

  describe("enforcing mode", () => {
    it("allows when verdict is allow", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeAllowDecision());
      const result = await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(result.allowed).toBe(true);
    });

    it("blocks when verdict is block", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeBlockDecision());
      const result = await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(result.allowed).toBe(false);
      expect(result.blockReason).toContain("BLOCKED");
    });

    it("blocks when HITL is required", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeHITLDecision());
      const result = await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(result.allowed).toBe(false);
      expect(result.blockReason).toContain("HITL required");
    });

    it("blocks on sidecar unreachable (fail-closed)", async () => {
      mockCheckBeforeWrite.mockRejectedValue(new Error("ECONNREFUSED"));
      const result = await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(result.allowed).toBe(false);
      expect(result.blockReason).toContain("FAIL-CLOSED");
    });

    it("does not block on sidecar error when failClosed is false", async () => {
      gov = new Governance({ ...defaultConfig, failClosed: false });
      mockCheckBeforeWrite.mockRejectedValue(new Error("ECONNREFUSED"));
      const result = await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(result.allowed).toBe(true);
    });

    it("passes through read tools without checking", async () => {
      const result = await gov.checkToolCall("read", { path: "/tmp/test.txt" });
      expect(result.allowed).toBe(true);
      expect(mockCheckBeforeWrite).not.toHaveBeenCalled();
    });
  });

  describe("caching", () => {
    it("returns cached allow decision on repeated check", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeAllowDecision());
      await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(mockCheckBeforeWrite).toHaveBeenCalledTimes(1);
    });

    it("does not cache HITL decisions", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeHITLDecision());
      await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(mockCheckBeforeWrite).toHaveBeenCalledTimes(2);
    });

    it("caches different keys independently", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeAllowDecision());
      await gov.checkToolCall("write", { file_path: "/tmp/a.txt" });
      await gov.checkToolCall("write", { file_path: "/tmp/b.txt" });
      expect(mockCheckBeforeWrite).toHaveBeenCalledTimes(2);
      // Both should be cached now
      await gov.checkToolCall("write", { file_path: "/tmp/a.txt" });
      await gov.checkToolCall("write", { file_path: "/tmp/b.txt" });
      expect(mockCheckBeforeWrite).toHaveBeenCalledTimes(2);
    });
  });

  describe("cache stats", () => {
    it("tracks hits and misses", async () => {
      mockCheckBeforeWrite.mockResolvedValue(makeAllowDecision());
      expect(gov.cacheStats).toEqual({ size: 0, hits: 0, misses: 0 });

      await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      // First call: miss + set
      expect(gov.cacheStats.misses).toBeGreaterThanOrEqual(1);

      await gov.checkToolCall("write", { file_path: "/tmp/test.txt" });
      expect(gov.cacheStats.hits).toBeGreaterThanOrEqual(1);
    });
  });
});
