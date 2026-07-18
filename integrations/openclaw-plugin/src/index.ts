/**
 * @maref/openclaw-plugin — MAREF Governance Plugin for OpenClaw
 *
 * 在 OpenClaw Agent 的写入/执行前插入 MAREF 治理检查。
 * 支持三种模式: enforcing / advisory / logging
 *
 * 安装:
 *   1. npm install @maref-org/sdk @maref/openclaw-plugin
 *   2. 在 OpenClaw 配置中加载本插件 (见 README)
 *   3. 确保 MAREF sidecar 在 localhost:8000 运行
 *
 * 设计原则:
 *   - enforcing 模式: block verdict 阻止操作，hitl_required 发起人工介入
 *   - advisory 模式: 只警告不拦截，用于灰度验证
 *   - logging 模式: 只记日志，零拦截
 *   - fail-closed: sidecar 不可达时 enforcing 模式默认阻断
 */

import { MAREFClient, type GateDecision } from "@maref-org/sdk";

// ═════════════════════════════════════════════════════════════════════
// 类型定义
// ═════════════════════════════════════════════════════════════════════

/** 插件执行模式 */
export type MAREFMode = "enforcing" | "advisory" | "logging";

/** 插件配置 */
export interface MAREFPluginConfig {
  /** MAREF sidecar 地址，默认 http://localhost:8000 */
  sidecarUrl?: string;
  /**
   * 执行模式:
   *   - enforcing: 拦截违规操作 + HITL 人工介入（生产）
   *   - advisory:  仅警告不拦截（灰度）
   *   - logging:   仅记日志（调试）
   */
  mode?: MAREFMode;
  /** 是否在 sidecar 不可达时阻断操作（仅 enforcing 模式有效） */
  failClosed?: boolean;
}

/** Hook 上下文 — OpenClaw 传入 */
export interface OpenClawHookContext {
  agentId: string;
  sessionId: string;
  config: Record<string, unknown>;
}

/** Hook 返回值 */
export interface HookResult {
  allowed: boolean;
  reason: string;
}

// ═════════════════════════════════════════════════════════════════════
// 插件主类
// ═════════════════════════════════════════════════════════════════════

export class MAREFGovernancePlugin {
  private client: MAREFClient;
  private mode: MAREFMode;
  private failClosed: boolean;

  constructor(config: MAREFPluginConfig = {}) {
    this.client = new MAREFClient(config.sidecarUrl);
    this.mode = config.mode ?? "enforcing";
    this.failClosed = config.failClosed ?? true;
  }

  /** 当前模式 */
  get currentMode(): MAREFMode {
    return this.mode;
  }

  /**
   * 【文件写入前 hook】
   *
   * 在 OpenClaw Agent 写入文件前调用，判断是否允许。
   */
  async beforeFileWrite(
    context: OpenClawHookContext,
    filePath: string,
  ): Promise<HookResult> {
    const decision = await this.client.checkBeforeWrite({
      file_path: filePath,
      actor: context.agentId,
      session_id: context.sessionId,
    });

    // 审计上报（best-effort）
    this._report(context, "beforeFileWrite", decision, { filePath });

    return this._resolve(decision, `write ${filePath}`);
  }

  /**
   * 【命令执行前 hook】
   *
   * 在 OpenClaw Agent 执行命令前调用，判断是否允许。
   */
  async beforeCommand(
    context: OpenClawHookContext,
    command: string,
  ): Promise<HookResult> {
    if (this.mode === "logging") {
      return { allowed: true, reason: "logging mode — no check" };
    }

    const decision = await this.client.checkBeforeExecute({
      command,
      actor: context.agentId,
      session_id: context.sessionId,
    });

    this._report(context, "beforeCommand", decision, { command });

    return this._resolve(decision, `execute ${command}`);
  }

  /**
   * 【读取前 hook】（可选）
   *
   * 敏感文件读取前检查。默认放行，可在 enforcing 模式下对高危路径拦截。
   */
  async beforeFileRead(
    context: OpenClawHookContext,
    filePath: string,
  ): Promise<HookResult> {
    if (this.mode === "logging") {
      return { allowed: true, reason: "logging mode" };
    }

    // 只对明确的高危路径做检查
    const sensitivePatterns = [
      /\.pem$/i, /\.key$/i, /\.p12$/i, /\.jks$/i,
      /\.env/, /\.env\..+/,
      /id_rsa/, /id_ed25519/, /credentials/i,
      /\/etc\/(passwd|shadow|sudoers)/,
    ];

    const isSensitive = sensitivePatterns.some((p) => p.test(filePath));
    if (!isSensitive) {
      return { allowed: true, reason: "non-sensitive path" };
    }

    const decision = await this.client.checkBeforeWrite({
      file_path: filePath,
      actor: context.agentId,
      session_id: context.sessionId,
    });

    return this._resolve(decision, `read ${filePath}`);
  }

  // ── 内部方法 ───────────────────────────────────────────────

  /** 根据模式和决策结果决定是否放行 */
  private _resolve(decision: GateDecision, operation: string): HookResult {
    switch (this.mode) {
      case "logging":
        return { allowed: true, reason: `[LOG] ${decision.rule_id}: ${decision.reason}` };

      case "advisory":
        if (decision.verdict === "block") {
          console.warn(
            `[MAREF] ADVISORY — would BLOCK ${operation}: ${decision.reason}`,
          );
        }
        return { allowed: true, reason: `[ADVISORY] ${decision.reason}` };

      case "enforcing":
      default:
        if (decision.verdict === "block") {
          const reason = `[MAREF] BLOCKED ${operation} — rule ${decision.rule_id}: ${decision.reason}`;
          if (this.failClosed) {
            return { allowed: false, reason };
          }
          console.warn(`[MAREF] FAIL-OPEN: ${reason}`);
          return { allowed: true, reason };
        }

        if (decision.verdict === "hitl_required") {
          // 在 plugin 层，hitl_required 默认降级为 block
          // 因为 OpenClaw 的 hook 接口不支持异步等待人工决策
          // 真正的 HITL 由 sidecar 的 HitlEnforcementLayer 在服务端处理
          return {
            allowed: false,
            reason: `[MAREF] HITL required for ${operation} — contact human operator`,
          };
        }

        return { allowed: true, reason: `[MAREF] ALLOWED: ${decision.reason}` };
    }
  }

  /** 审计上报 */
  private _report(
    context: OpenClawHookContext,
    hook: string,
    decision: GateDecision,
    extra: Record<string, unknown>,
  ): void {
    // fire-and-forget: 审计失败不阻断业务
    this.client.reportAction({
      action: `openclaw:${hook}`,
      result: {
        verdict: decision.verdict,
        rule_id: decision.rule_id,
        reason: decision.reason,
        risk_score: decision.risk_score,
        ...extra,
      },
      actor: context.agentId,
      session_id: context.sessionId,
    }).catch(() => {
      // 审计上报是 best-effort，忽略所有错误
    });
  }
}

// ═════════════════════════════════════════════════════════════════════
// 便捷工厂
// ═════════════════════════════════════════════════════════════════════

/**
 * 创建 MAREF Governance Plugin 实例
 *
 * 使用方式:
 *   import { createMAREFPlugin } from '@maref/openclaw-plugin'
 *   const plugin = createMAREFPlugin({ mode: 'enforcing' })
 *   const result = await plugin.beforeFileWrite(ctx, '/tmp/test.txt')
 */
export function createMAREFPlugin(config?: MAREFPluginConfig): MAREFGovernancePlugin {
  return new MAREFGovernancePlugin(config);
}
