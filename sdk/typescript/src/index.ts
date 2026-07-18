/**
 * @maref-org/sdk — MAREF Agent Governance OS TypeScript SDK
 *
 * 治理执行客户端。供任何 Agent（Claude Code、OpenClaw、自定义等）
 * 调用 MAREF sidecar 进行写入前检查、执行前检查、HITL 人工介入、
 * 阶段门强制执行、审计上报。
 *
 * 使用方式:
 *   import { MAREFClient } from '@maref-org/sdk'
 *   const client = new MAREFClient('http://localhost:8000')
 *   const decision = await client.checkBeforeWrite({ file_path: '/tmp/test.txt' })
 *
 * 设计原则:
 *   - 所有治理接口 fail-closed（sidecar 不可达时默认阻断）
 *   - 审计上报 fail-open（不阻断业务）
 *   - 所有方法返回结构化结果，不抛异常
 */

// ═════════════════════════════════════════════════════════════════════
// 类型定义
// ═════════════════════════════════════════════════════════════════════

/** 治理状态总览 */
export interface GovernanceStatus {
  state: string;
  circuit_breaker: "CLOSED" | "OPEN" | "HALF_OPEN";
  agent_count: number;
  trust_score_avg: number;
  drift_level: "LOW" | "MEDIUM" | "HIGH";
  timestamp: number;
}

/** 单个 Agent 信任评分详情 */
export interface AgentTrustScore {
  agent_id: string;
  score: number;
  factors: {
    behavior_consistency: number;
    cb_trigger_frequency: number;
    halt_escape_rate: number;
    task_completion: number;
    vc_validity: number;
  };
}

// ── 治理执行相关类型 ─────────────────────────────────────────────

/** 治理检查结果 — sidecar 返回的标准格式 */
export interface GateDecision {
  verdict: "allow" | "block" | "hitl_required";
  rule_id: string;
  reason: string;
  risk_score: number;
  decision_latency_ms: number;
  actor: string;
  breaker_state: "closed" | "open" | "half_open";
  metadata: Record<string, unknown>;
}

/** 阶段门状态 */
export interface PhaseState {
  phase: "design" | "review" | "implement" | "deliver" | "unconstrained";
  allowed_outputs: string[];
  forbidden_outputs: string[];
  human_confirmation_required: boolean;
}

/** HITL 人工决策请求 */
export interface HumanDecisionRequest {
  session_id: string;
  title: string;
  description: string;
  options: Array<{
    id: string;
    label: string;
    risk: number;
  }>;
  timeout_seconds: number;
}

/** HITL 人工决策结果 */
export interface HumanDecisionResponse {
  decision_id: string;
  selected_option: string;
  reason: string;
  decided_by: "human" | "timeout" | "auto";
  decided_at: string;
}

// ── 请求参数类型 ─────────────────────────────────────────────────

export interface CheckBeforeWriteParams {
  file_path: string;
  actor?: string;
  session_id?: string;
}

export interface CheckBeforeExecuteParams {
  command: string;
  actor?: string;
  session_id?: string;
}

export interface ReportActionParams {
  action: string;
  result: unknown;
  actor?: string;
  session_id?: string;
}

// ═════════════════════════════════════════════════════════════════════
// 主客户端
// ═════════════════════════════════════════════════════════════════════

export class MAREFClient {
  private baseUrl: string;

  /**
   * @param baseUrl MAREF sidecar 地址，默认 http://localhost:8000
   */
  constructor(baseUrl = "http://localhost:8000") {
    // 去掉尾部斜杠，防止拼接 URL 时出现 //
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  // ═══════════════════════════════════════════════════════════════
  // 只读查询接口（已有，保持兼容）
  // ═══════════════════════════════════════════════════════════════

  /**
   * 获取治理状态总览
   */
  async getGovernanceStatus(): Promise<GovernanceStatus> {
    const res = await this._fetch("/api/status");
    return res.json();
  }

  /**
   * 获取指定 Agent 的信任评分详情
   */
  async getAgentTrustScore(agentId: string): Promise<AgentTrustScore> {
    const res = await this._fetch(`/api/agents/${encodeURIComponent(agentId)}/trust`);
    return res.json();
  }

  /**
   * 列出所有已注册 Agent
   */
  async listAgents(): Promise<string[]> {
    const res = await this._fetch("/api/agents");
    const data = await res.json();
    return data.agents ?? [];
  }

  /**
   * 订阅审计日志流（SSE）
   * 返回 EventSource，调用方负责关闭
   */
  subscribeAuditLog(
    callback: (entry: Record<string, unknown>) => void,
  ): EventSource {
    const source = new EventSource(`${this.baseUrl}/api/audit/stream`);
    source.onmessage = (event) => {
      try {
        callback(JSON.parse(event.data));
      } catch {
        // 忽略解析失败的条目
      }
    };
    source.onerror = () => {
      // EventSource 自动重连，不需要额外处理
    };
    return source;
  }

  // ═══════════════════════════════════════════════════════════════
  // 治理执行接口（新增）
  // ═══════════════════════════════════════════════════════════════

  /**
   * 【写入前治理检查】
   *
   * 在写入文件前调用，判断该操作是否被允许。
   * sidecar 不可达时返回 block（fail-closed）。
   *
   * @param params.file_path 要写入的文件路径
   * @param params.actor     执行操作的 Agent 标识
   * @param params.session_id 会话 ID（可选）
   */
  async checkBeforeWrite(
    params: CheckBeforeWriteParams,
  ): Promise<GateDecision> {
    return this._governanceCheck({
      actor: params.actor ?? "unknown",
      file_path: params.file_path,
      tool: "write",
      session_id: params.session_id ?? "default",
      parameters: { file_path: params.file_path },
    });
  }

  /**
   * 【执行前治理检查】
   *
   * 在执行命令前调用，判断该操作是否被允许。
   * sidecar 不可达时返回 block（fail-closed）。
   *
   * @param params.command   要执行的命令
   * @param params.actor     执行操作的 Agent 标识
   * @param params.session_id 会话 ID（可选）
   */
  async checkBeforeExecute(
    params: CheckBeforeExecuteParams,
  ): Promise<GateDecision> {
    return this._governanceCheck({
      actor: params.actor ?? "unknown",
      file_path: params.command,
      tool: "execute",
      session_id: params.session_id ?? "default",
      parameters: { command: params.command },
    });
  }

  /**
   * 【操作审计上报】
   *
   * 将 Agent 的操作记录上报到 MAREF 审计链。
   * 此方法为 best-effort，失败不抛异常。
   *
   * @param params.action   操作名称
   * @param params.result   操作结果（任意可 JSON 序列化的值）
   * @param params.actor    执行操作的 Agent 标识
   * @param params.session_id 会话 ID（可选）
   */
  async reportAction(params: ReportActionParams): Promise<void> {
    try {
      await this._fetch("/api/audit/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: "action",
          actor: params.actor ?? "unknown",
          action: params.action,
          details: JSON.stringify(params.result),
          session_id: params.session_id ?? "default",
          timestamp: Date.now() / 1000,
        }),
      });
    } catch {
      // 审计上报是 best-effort，失败不阻断业务
    }
  }

  /**
   * 【获取阶段门状态】
   *
   * 返回当前所处的开发阶段（design / review / implement / deliver），
   * 以及各阶段允许/禁止的产出类型。
   * sidecar 不可达时返回 unconstrained（放行）。
   */
  async getPhaseGate(): Promise<PhaseState> {
    try {
      const res = await this._fetch("/api/governance/phase");
      if (!res.ok) {
        return this._defaultPhaseState();
      }
      return res.json();
    } catch {
      return this._defaultPhaseState();
    }
  }

  /**
   * 【发起 HITL 人工决策】
   *
   * 当治理检查判定需要人工介入时，调用此方法向人类发送决策请求。
   * sidecar 不可达时返回 timeout 决策。
   *
   * @param request 决策请求参数
   */
  async requestHITL(
    request: HumanDecisionRequest,
  ): Promise<HumanDecisionResponse> {
    try {
      const res = await this._fetch("/api/human/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (!res.ok) {
        return this._defaultHITLResponse("HITL sidecar error");
      }
      return res.json();
    } catch {
      return this._defaultHITLResponse("HITL unreachable");
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════════════════

  /**
   * 底层 fetch 封装 — 所有请求通过此方法发出
   */
  private async _fetch(
    path: string,
    init?: RequestInit,
  ): Promise<Response> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      ...init,
      signal: AbortSignal.timeout(10_000), // 10 秒超时
    });
    return response;
  }

  /**
   * 治理检查核心 — checkBeforeWrite 和 checkBeforeExecute 共用
   */
  private async _governanceCheck(payload: {
    actor: string;
    file_path: string;
    tool: string;
    session_id: string;
    parameters: Record<string, string>;
  }): Promise<GateDecision> {
    try {
      const res = await this._fetch("/api/governance/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        return this._failClosedDecision(
          payload.actor,
          `Sidecar returned HTTP ${res.status}`,
        );
      }

      const decision: GateDecision = await res.json();
      return decision;
    } catch (err) {
      return this._failClosedDecision(
        payload.actor,
        `Sidecar unreachable: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }

  /**
   * fail-closed 默认决策 — sidecar 不可达时返回 block
   */
  private _failClosedDecision(
    actor: string,
    reason: string,
  ): GateDecision {
    return {
      verdict: "block",
      rule_id: "MAREF-SIDECAR-UNREACHABLE",
      reason: `[FAIL-CLOSED] ${reason}`,
      risk_score: 1.0,
      decision_latency_ms: 0,
      actor,
      breaker_state: "open",
      metadata: {
        fail_closed: true,
        timestamp: Date.now() / 1000,
      },
    };
  }

  /**
   * 默认阶段门状态（sidecar 不可达时）
   */
  private _defaultPhaseState(): PhaseState {
    return {
      phase: "unconstrained",
      allowed_outputs: ["*"],
      forbidden_outputs: [],
      human_confirmation_required: false,
    };
  }

  /**
   * 默认 HITL 响应（sidecar 不可达时）
   */
  private _defaultHITLResponse(reason: string): HumanDecisionResponse {
    return {
      decision_id: "auto_fallback",
      selected_option: "timeout",
      reason: `[AUTO-FALLBACK] ${reason}`,
      decided_by: "timeout",
      decided_at: new Date().toISOString(),
    };
  }
}

// ═════════════════════════════════════════════════════════════════════
// 便捷工厂函数
// ═════════════════════════════════════════════════════════════════════

/**
 * 创建 MAREF 治理客户端实例（便捷方式）
 *
 * 使用方式:
 *   import { createMAREFClient } from '@maref-org/sdk'
 *   const governance = createMAREFClient()
 *   const decision = await governance.checkBeforeWrite({ file_path: '/tmp/test.txt' })
 */
export function createMAREFClient(baseUrl?: string): MAREFClient {
  return new MAREFClient(baseUrl);
}
