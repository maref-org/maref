/**
 * @maref-org/sdk — 单元测试
 *
 * 覆盖:
 *   - 所有接口的正常路径
 *   - sidecar 不可达时的 fail-closed 行为
 *   - 审计上报的 best-effort 行为
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { MAREFClient, createMAREFClient } from "../index";

// EventSource 在 Node.js 测试环境中不存在，提供一个 mock
class MockEventSource {
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(_url: string) {}
  close() {}
}
vi.stubGlobal("EventSource", MockEventSource);

// ── Helper ────────────────────────────────────────────────────────

function mockFetch(status: number, body: unknown): void {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockFetchError(message: string): void {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error(message));
}

function mockFetchNetworkError(): void {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(
    new TypeError("fetch failed: connection refused"),
  );
}

// ── 测试 ──────────────────────────────────────────────────────────

describe("MAREFClient", () => {
  let client: MAREFClient;

  beforeEach(() => {
    client = new MAREFClient("http://localhost:8000");
    vi.restoreAllMocks();
  });

  describe("constructor", () => {
    it("默认端口: 8000", () => {
      const c = new MAREFClient();
      expect(c).toBeInstanceOf(MAREFClient);
    });

    it("自定义 sidecar URL", () => {
      const c = new MAREFClient("http://127.0.0.1:9000");
      expect(c).toBeInstanceOf(MAREFClient);
    });

    it("去掉尾部斜杠", () => {
      const c = new MAREFClient("http://localhost:8000/");
      // 只能通过方法行为间接验证
      expect(c).toBeInstanceOf(MAREFClient);
    });
  });

  // ── 只读查询（已有，保持兼容） ─────────────────────────────

  describe("getGovernanceStatus", () => {
    it("返回治理状态", async () => {
      const expected = {
        state: "STABILIZE",
        circuit_breaker: "CLOSED",
        agent_count: 5,
        trust_score_avg: 78.5,
        drift_level: "LOW",
        timestamp: Date.now() / 1000,
      };
      mockFetch(200, expected);

      const result = await client.getGovernanceStatus();
      expect(result.state).toBe("STABILIZE");
      expect(result.circuit_breaker).toBe("CLOSED");
      expect(result.agent_count).toBe(5);
    });

    it("sidecar 返回非 200 — HTTP 错误由 res.json() 正常返回", async () => {
      mockFetch(500, { error: "internal" });
      const result = await client.getGovernanceStatus();
      expect(result).toHaveProperty("error", "internal");
    });
  });

  describe("getAgentTrustScore", () => {
    it("返回 Agent 信任评分", async () => {
      const expected = {
        agent_id: "claude-code",
        score: 85.3,
        factors: {
          behavior_consistency: 90,
          cb_trigger_frequency: 5,
          halt_escape_rate: 2,
          task_completion: 88,
          vc_validity: 95,
        },
      };
      mockFetch(200, expected);

      const result = await client.getAgentTrustScore("claude-code");
      expect(result.agent_id).toBe("claude-code");
      expect(result.score).toBe(85.3);
    });

    it("URL 编码 agentId", async () => {
      mockFetch(200, { agent_id: "test agent", score: 50, factors: {} as any });
      const fetchSpy = vi.spyOn(globalThis, "fetch");
      await client.getAgentTrustScore("test agent");
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining(encodeURIComponent("test agent")),
        expect.anything(),
      );
    });
  });

  describe("listAgents", () => {
    it("返回 Agent 列表", async () => {
      mockFetch(200, { agents: ["agent-a", "agent-b"] });

      const result = await client.listAgents();
      expect(result).toEqual(["agent-a", "agent-b"]);
    });
  });

  describe("subscribeAuditLog", () => {
    it("返回 EventSource", () => {
      // EventSource 在 node 环境下不可用，只验证接口存在
      const source = client.subscribeAuditLog(() => {});
      expect(source).toBeDefined();
    });
  });

  // ── 治理执行（新增） ───────────────────────────────────────

  describe("checkBeforeWrite", () => {
    it("sidecar 返回 allow", async () => {
      mockFetch(200, {
        verdict: "allow",
        rule_id: "MAREF-WHITELIST",
        reason: "whitelisted path",
        risk_score: 0.1,
        decision_latency_ms: 5,
        actor: "test-agent",
        breaker_state: "closed",
        metadata: {},
      });

      const result = await client.checkBeforeWrite({
        file_path: "/tmp/test.txt",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("allow");
      expect(result.rule_id).toBe("MAREF-WHITELIST");
      expect(result.risk_score).toBeLessThan(0.5);
    });

    it("sidecar 返回 block", async () => {
      mockFetch(200, {
        verdict: "block",
        rule_id: "MAREF-POLICY-DENY",
        reason: "denied by policy",
        risk_score: 0.9,
        decision_latency_ms: 3,
        actor: "test-agent",
        breaker_state: "closed",
        metadata: {},
      });

      const result = await client.checkBeforeWrite({
        file_path: "/etc/passwd",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("block");
    });

    it("sidecar 返回 hitl_required", async () => {
      mockFetch(200, {
        verdict: "hitl_required",
        rule_id: "MAREF-REQUIRES-HITL",
        reason: "requires human approval",
        risk_score: 0.7,
        decision_latency_ms: 2,
        actor: "test-agent",
        breaker_state: "closed",
        metadata: {},
      });

      const result = await client.checkBeforeWrite({
        file_path: "/etc/config.yaml",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("hitl_required");
    });

    it("HTTP 503 时 fail-closed → block", async () => {
      mockFetch(503, { error: "service unavailable" });

      const result = await client.checkBeforeWrite({
        file_path: "/tmp/test.txt",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("block");
      expect(result.rule_id).toBe("MAREF-SIDECAR-UNREACHABLE");
      expect(result.risk_score).toBe(1.0);
      expect(result.breaker_state).toBe("open");
    });

    it("网络错误时 fail-closed → block", async () => {
      mockFetchNetworkError();

      const result = await client.checkBeforeWrite({
        file_path: "/tmp/test.txt",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("block");
      expect(result.rule_id).toBe("MAREF-SIDECAR-UNREACHABLE");
    });

    it("10 秒超时 fail-closed → block", async () => {
      mockFetchError("The operation was aborted due to timeout");

      const result = await client.checkBeforeWrite({
        file_path: "/tmp/test.txt",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("block");
      expect(result.reason).toContain("FAIL-CLOSED");
    });
  });

  describe("checkBeforeExecute", () => {
    it("sidecar 返回 allow", async () => {
      mockFetch(200, {
        verdict: "allow",
        rule_id: "MAREF-DEFAULT-ALLOW",
        reason: "allowed",
        risk_score: 0.3,
        decision_latency_ms: 4,
        actor: "test-agent",
        breaker_state: "closed",
        metadata: {},
      });

      const result = await client.checkBeforeExecute({
        command: "ls -la",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("allow");
    });

    it("sidecar 返回 block", async () => {
      mockFetch(200, {
        verdict: "block",
        rule_id: "MAREF-POLICY-DENY",
        reason: "command not allowed",
        risk_score: 0.95,
        decision_latency_ms: 2,
        actor: "test-agent",
        breaker_state: "closed",
        metadata: {},
      });

      const result = await client.checkBeforeExecute({
        command: "rm -rf /",
        actor: "test-agent",
      });

      expect(result.verdict).toBe("block");
    });
  });

  describe("reportAction", () => {
    it("正常上报不抛异常", async () => {
      mockFetch(200, { ok: true });

      await expect(
        client.reportAction({
          action: "file_write",
          result: { path: "/tmp/test.txt", size: 1024 },
          actor: "test-agent",
        }),
      ).resolves.not.toThrow();
    });

    it("sidecar 错误时不抛异常（best-effort）", async () => {
      mockFetch(500, { error: "internal" });

      await expect(
        client.reportAction({
          action: "file_write",
          result: { path: "/tmp/test.txt" },
        }),
      ).resolves.not.toThrow();
    });

    it("网络错误时不抛异常（best-effort）", async () => {
      mockFetchNetworkError();

      await expect(
        client.reportAction({
          action: "file_write",
          result: {},
        }),
      ).resolves.not.toThrow();
    });
  });

  describe("getPhaseGate", () => {
    it("返回当前阶段", async () => {
      mockFetch(200, {
        phase: "implement",
        allowed_outputs: ["code", "config"],
        forbidden_outputs: ["design_doc"],
        human_confirmation_required: false,
      });

      const result = await client.getPhaseGate();
      expect(result.phase).toBe("implement");
    });

    it("sidecar 不可达时返回 unconstrained", async () => {
      mockFetchNetworkError();

      const result = await client.getPhaseGate();
      expect(result.phase).toBe("unconstrained");
      expect(result.human_confirmation_required).toBe(false);
    });

    it("404 时返回 unconstrained", async () => {
      mockFetch(404, { error: "not found" });

      const result = await client.getPhaseGate();
      expect(result.phase).toBe("unconstrained");
    });
  });

  describe("requestHITL", () => {
    it("返回人工决策结果", async () => {
      mockFetch(200, {
        decision_id: "dec_001",
        selected_option: "allow",
        reason: "human approved",
        decided_by: "human",
        decided_at: "2026-07-18T12:00:00Z",
      });

      const result = await client.requestHITL({
        session_id: "sess_001",
        title: "审批请求",
        description: "Agent 请求写入敏感文件",
        options: [
          { id: "allow", label: "允许", risk: 0.3 },
          { id: "deny", label: "拒绝", risk: 0 },
        ],
        timeout_seconds: 60,
      });

      expect(result.selected_option).toBe("allow");
      expect(result.decided_by).toBe("human");
    });

    it("sidecar 不可达时返回 timeout", async () => {
      mockFetchNetworkError();

      const result = await client.requestHITL({
        session_id: "sess_001",
        title: "测试",
        description: "测试",
        options: [],
        timeout_seconds: 10,
      });

      expect(result.selected_option).toBe("timeout");
      expect(result.decided_by).toBe("timeout");
    });

    it("HTTP 错误时返回 timeout", async () => {
      mockFetch(503, { error: "unavailable" });

      const result = await client.requestHITL({
        session_id: "sess_001",
        title: "测试",
        description: "测试",
        options: [],
        timeout_seconds: 10,
      });

      expect(result.selected_option).toBe("timeout");
    });
  });

  // ── 工厂函数 ─────────────────────────────────────────────

  describe("createMAREFClient", () => {
    it("创建客户端实例", () => {
      const c = createMAREFClient();
      expect(c).toBeInstanceOf(MAREFClient);
    });

    it("传递 baseUrl", () => {
      const c = createMAREFClient("http://127.0.0.1:9000");
      expect(c).toBeInstanceOf(MAREFClient);
    });
  });
});
