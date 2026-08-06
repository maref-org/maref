import { useEffect, useState, useCallback } from "react";
import {
  Monitor,
  Shield,
  Terminal,
  MousePointer,
  Keyboard,
  Eye,
  Play,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, detectBackend } from "@/api/client";

type ExecutionRecord = {
  id: number;
  plan_id: string;
  description: string;
  success: boolean;
  created_at: number;
  executed_at: number;
  plan_json: string;
  result_json: string;
};

type OperationRecord = {
  id: number;
  execution_id: number;
  step_index: number;
  op_type: string;
  params_json: string;
  description: string;
  success: boolean;
  duration_ms: number;
  error: string;
  safety_decision: string;
  verification_passed: boolean;
  verification_diff_pct: number;
};

const OP_ICONS: Record<string, React.ElementType> = {
  click: MousePointer,
  double_click: MousePointer,
  right_click: MousePointer,
  type: Keyboard,
  hotkey: Terminal,
  scroll: RefreshCw,
  drag: MousePointer,
  screenshot: Eye,
  parse: Eye,
  wait: Clock,
};

const SAFETY_COLORS: Record<string, string> = {
  allow: "text-maref-success bg-maref-success/10",
  block: "text-maref-danger bg-maref-danger/10",
  ask_user: "text-maref-warning bg-maref-warning/10",
};

const SAFETY_LABELS: Record<string, string> = {
  allow: "允许",
  block: "拦截",
  ask_user: "询问",
};

const DEFAULT_OPS = [
  { op_type: "click", params: { x: 100, y: 100 }, description: "点击屏幕" },
  { op_type: "type", params: { text: "Hello MAREF" }, description: "输入文本" },
  { op_type: "hotkey", params: { keys: ["command", "n"] }, description: "新建窗口" },
];

export function DesktopAgentView() {
  const [backendMode, setBackendModeState] = useState<"checking" | "real" | "mock">("checking");
  const [isExecuting, setIsExecuting] = useState(false);
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedExecution, setSelectedExecution] = useState<number | null>(null);
  const [executionOps, setExecutionOps] = useState<OperationRecord[]>([]);
  const [policyStatus, setPolicyStatus] = useState<Record<string, unknown> | null>(null);
  const [operationMode, setOperationMode] = useState<string>("semi_auto");
  const [governanceStatus, setGovernanceStatus] = useState<Record<string, unknown> | null>(null);
  const [governanceEvents, setGovernanceEvents] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    let cancelled = false;
    detectBackend().then((mode) => {
      if (!cancelled) setBackendModeState(mode);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshStatus = useCallback(() => {
    api.desktopStatus().catch(() => {});
  }, []);

  const refreshPolicyStatus = useCallback(() => {
    api.desktopPolicyStatus()
      .then((data) => {
        setPolicyStatus(data as Record<string, unknown>);
      })
      .catch(() => {
        setPolicyStatus(null);
      });
  }, []);

  const refreshGovernanceStatus = useCallback(() => {
    api.desktopGovernanceStatus()
      .then((data) => {
        setGovernanceStatus(data as Record<string, unknown>);
      })
      .catch(() => {
        setGovernanceStatus(null);
      });
    api.desktopGovernanceEvents(20)
      .then((data) => {
        setGovernanceEvents(((data as { events?: Array<Record<string, unknown>> })?.events ?? []) as Array<Record<string, unknown>>);
      })
      .catch(() => {
        setGovernanceEvents([]);
      });
  }, []);

  const refreshHistory = useCallback(() => {
    api.desktopHistory(20)
      .then((data) => {
        const response = data as Record<string, unknown> | unknown[];
        const executionsArray = Array.isArray(response)
          ? response
          : ((response as { executions?: Array<Record<string, unknown>> })?.executions ?? []);
        const records: ExecutionRecord[] = executionsArray.map((item) => {
          const obj = item as Record<string, unknown>;
          return {
            id: Number(obj.id ?? 0),
            plan_id: String(obj.plan_id ?? ""),
            description: String(obj.description ?? ""),
            success: Boolean(obj.success),
            created_at: Number(obj.created_at ?? 0),
            executed_at: Number(obj.executed_at ?? 0),
            plan_json: String(obj.plan_json ?? ""),
            result_json: String(obj.result_json ?? ""),
          };
        });
        setExecutions(records);
      })
      .catch(() => {
        setExecutions([]);
      });
  }, []);

  const viewExecutionDetails = useCallback((executionId: number) => {
    api.desktopExecutionDetails(executionId)
      .then((data) => {
        const d = data as Record<string, unknown>;
        setSelectedExecution(executionId);
        const opsArray = (d.operations as Array<Record<string, unknown>>) ?? [];
        const ops: OperationRecord[] = opsArray.map((item) => {
          const obj = item as Record<string, unknown>;
          return {
            id: Number(obj.id ?? 0),
            execution_id: Number(obj.execution_id ?? 0),
            step_index: Number(obj.step_index ?? 0),
            op_type: String(obj.op_type ?? ""),
            params_json: String(obj.params_json ?? "{}"),
            description: String(obj.description ?? ""),
            success: Boolean(obj.success),
            duration_ms: Number(obj.duration_ms ?? 0),
            error: String(obj.error ?? ""),
            safety_decision: String(obj.safety_decision ?? "allow"),
            verification_passed: Boolean(obj.verification_passed),
            verification_diff_pct: Number(obj.verification_diff_pct ?? 0),
          };
        });
        setExecutionOps(ops);
      })
      .catch(() => {
        setSelectedExecution(null);
        setExecutionOps([]);
      });
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshHistory();
    refreshGovernanceStatus();
    refreshPolicyStatus();
  }, [refreshStatus, refreshHistory, refreshGovernanceStatus, refreshPolicyStatus]);

  const handleExecute = useCallback(async () => {
    setIsExecuting(true);
    setError(null);
    try {
      await api.desktopExecutePlan(DEFAULT_OPS, false, "前端测试执行");
      refreshHistory();
      refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "执行失败");
    } finally {
      setIsExecuting(false);
    }
  }, [refreshHistory, refreshStatus]);

  const handleCapture = useCallback(async () => {
    try {
      await api.desktopCapture();
      refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "截图失败");
    }
  }, [refreshHistory]);

  const handleCalibrate = useCallback(async () => {
    try {
      await api.desktopCalibrate();
      refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "校准失败");
    }
  }, [refreshStatus]);

  const modeLabel = backendMode === "real" ? "已连接" : backendMode === "mock" ? "模拟模式" : "检测中...";
  const modeColor = backendMode === "real" ? "bg-maref-success/20 text-maref-success" : backendMode === "mock" ? "bg-maref-warning/20 text-maref-warning" : "bg-maref-surface-alt text-maref-text-muted";
  const successfulExecutions = executions.filter((e) => e.success).length;

  const formatTime = (timestamp: number) => {
    if (!timestamp) return "-";
    return new Date(timestamp * 1000).toLocaleTimeString("zh-CN");
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <Monitor className="h-4 w-4 text-maref-accent" />
          桌面 Agent
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          OmniParser 3 后端 · PyAutoGUI · pyobjc · macOS 原生窗口管理
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-maref-danger/30 bg-maref-danger/10 px-4 py-2 text-xs text-maref-danger">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}

        <div className="grid grid-cols-4 gap-3">
          <StatTile icon={Monitor} label="后端" value={modeLabel} color={modeColor} />
          <StatTile icon={Shield} label="模式" value={isExecuting ? "执行中..." : "就绪"} color={isExecuting ? "bg-maref-warning/20 text-maref-warning" : "bg-maref-success/20 text-maref-success"} />
          <StatTile icon={CheckCircle} label="成功执行" value={`${successfulExecutions} 次`} color="bg-maref-info/20 text-maref-info" />
          <StatTile icon={Play} label="执行总数" value={`${executions.length} 次`} color="bg-maref-accent/20 text-maref-accent" />
        </div>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Terminal className="h-3.5 w-3.5" />
            执行历史
          </h3>
          <div className="overflow-hidden rounded-lg border border-maref-border">
            {executions.length === 0 ? (
              <div className="px-4 py-8 text-center text-xs text-maref-text-muted">暂无执行记录</div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-maref-border bg-maref-surface-alt">
                    <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">ID</th>
                    <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">计划 ID</th>
                    <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">描述</th>
                    <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">结果</th>
                    <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">执行时间</th>
                    <th className="px-4 py-2.5 text-right font-medium text-maref-text-muted">创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((exec) => {
                    const isExpanded = selectedExecution === exec.id;
                    return (
                      <tr key={exec.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                        <td className="px-4 py-2 text-maref-text-muted">{exec.id}</td>
                        <td className="px-4 py-2 font-mono text-maref-text text-[10px]">{exec.plan_id}</td>
                        <td className="px-4 py-2 text-maref-text">{exec.description}</td>
                        <td className="px-4 py-2">
                          {exec.success ? (
                            <span className="flex items-center gap-1 text-maref-success"><CheckCircle className="h-3 w-3" />成功</span>
                          ) : (
                            <span className="flex items-center gap-1 text-maref-danger"><XCircle className="h-3 w-3" />失败</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-maref-text-muted">{formatTime(exec.executed_at)}</td>
                        <td className="px-4 py-2 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <span className="text-maref-text-muted">{formatTime(exec.created_at)}</span>
                            <button
                              onClick={() => isExpanded ? setSelectedExecution(null) : viewExecutionDetails(exec.id)}
                              className="ml-1 rounded p-0.5 hover:bg-maref-surface-alt"
                            >
                              {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {selectedExecution !== null && executionOps.length > 0 && (
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <ChevronDown className="h-3.5 w-3.5" />
              执行 #{selectedExecution} 详情 — {executionOps.length} 步操作
            </h3>
            <div className="overflow-hidden rounded-lg border border-maref-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-maref-border bg-maref-surface-alt/50">
                    <th className="px-4 py-2 text-left font-medium text-maref-text-muted">步骤</th>
                    <th className="px-4 py-2 text-left font-medium text-maref-text-muted">操作</th>
                    <th className="px-4 py-2 text-left font-medium text-maref-text-muted">描述</th>
                    <th className="px-4 py-2 text-left font-medium text-maref-text-muted">安全门</th>
                    <th className="px-4 py-2 text-left font-medium text-maref-text-muted">验证</th>
                    <th className="px-4 py-2 text-right font-medium text-maref-text-muted">耗时</th>
                    <th className="px-4 py-2 text-left font-medium text-maref-text-muted">结果</th>
                  </tr>
                </thead>
                <tbody>
                  {executionOps.map((op) => {
                    const Icon = OP_ICONS[op.op_type] ?? Terminal;
                    return (
                      <tr key={op.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                        <td className="px-4 py-2 text-maref-text-muted">{op.step_index}</td>
                        <td className="px-4 py-2">
                          <span className="flex items-center gap-1.5 text-maref-text">
                            <Icon className="h-3 w-3 text-maref-accent" />
                            {op.op_type}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-maref-text">{op.description}</td>
                        <td className="px-4 py-2">
                          <span className={cn("rounded px-1.5 py-0.5 text-[10px]", SAFETY_COLORS[op.safety_decision] ?? SAFETY_COLORS.allow)}>
                            {SAFETY_LABELS[op.safety_decision] ?? op.safety_decision}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-maref-text-muted">
                          {op.verification_passed ? (
                            <span className="text-maref-success">通过 ({op.verification_diff_pct.toFixed(1)}%)</span>
                          ) : (
                            <span className="text-maref-warning">未通过</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right text-maref-text-muted">{op.duration_ms.toFixed(0)}ms</td>
                        <td className="px-4 py-2">
                          {op.success ? (
                            <span className="flex items-center gap-1 text-maref-success"><CheckCircle className="h-3 w-3" />成功</span>
                          ) : (
                            <span className="flex items-center gap-1 text-maref-danger" title={op.error}><XCircle className="h-3 w-3" />失败</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            可用操作
          </h3>
          <div className="grid grid-cols-4 gap-2">
            {["CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "TYPE", "HOTKEY", "SCROLL", "DRAG", "WAIT"].map((op) => (
              <div key={op} className="flex items-center gap-2 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-3 py-2">
                <div className="h-1.5 w-1.5 rounded-full bg-maref-accent" />
                <span className="text-[11px] text-maref-text">{op}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            控制
          </h3>
          <div className="flex gap-2">
            <button
              onClick={handleExecute}
              disabled={isExecuting || backendMode !== "real"}
              className="rounded-md bg-maref-accent px-4 py-2 text-xs font-medium text-black transition-opacity disabled:opacity-50"
            >
              {isExecuting ? "执行中..." : "执行测试计划"}
            </button>
            <button
              onClick={handleCapture}
              disabled={backendMode !== "real"}
              className="rounded-md border border-maref-border bg-maref-surface-alt px-4 py-2 text-xs font-medium text-maref-text transition-opacity hover:bg-maref-surface-alt/80 disabled:opacity-50"
            >
              截图
            </button>
            <button
              onClick={handleCalibrate}
              disabled={backendMode !== "real"}
              className="rounded-md border border-maref-border bg-maref-surface-alt px-4 py-2 text-xs font-medium text-maref-text transition-opacity hover:bg-maref-surface-alt/80 disabled:opacity-50"
            >
              校准
            </button>
            <button
              onClick={() => { refreshStatus(); refreshHistory(); setSelectedExecution(null); refreshPolicyStatus(); refreshGovernanceStatus(); }}
              className="rounded-md border border-maref-border bg-maref-surface-alt px-4 py-2 text-xs font-medium text-maref-text transition-opacity hover:bg-maref-surface-alt/80"
            >
              刷新
            </button>
          </div>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Shield className="h-3.5 w-3.5" />
            安全策略状态
          </h3>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <StatTile
                icon={Shield}
                label="操作模式"
                value={policyStatus?.operation_mode as string ?? "semi_auto"}
                color="bg-maref-accent/20 text-maref-accent"
              />
              <StatTile
                icon={CheckCircle}
                label="决策记录数"
                value={`${policyStatus?.decision_log_count ?? 0} 条`}
                color="bg-maref-info/20 text-maref-info"
              />
              <StatTile
                icon={AlertTriangle}
                label="待确认 HITL"
                value={policyStatus?.pending_hitl ? "1 个" : "无"}
                color={policyStatus?.pending_hitl ? "bg-maref-warning/20 text-maref-warning" : "bg-maref-success/20 text-maref-success"}
              />
            </div>
            {policyStatus?.pending_hitl != null && (
              <div className="rounded-lg border border-maref-warning/30 bg-maref-warning/10 p-4">
                <p className="mb-2 text-xs font-medium text-maref-warning">
                  HITL 待确认: {(policyStatus.pending_hitl as {reason: string}).reason}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      await api.desktopApproveHitl();
                      refreshPolicyStatus();
                    }}
                    className="rounded-md bg-maref-success px-3 py-1.5 text-xs font-medium text-white"
                  >
                    批准
                  </button>
                  <button
                    onClick={async () => {
                      await api.desktopRejectHitl();
                      refreshPolicyStatus();
                    }}
                    className="rounded-md bg-maref-danger px-3 py-1.5 text-xs font-medium text-white"
                  >
                    拒绝
                  </button>
                </div>
              </div>
            )}
            {policyStatus?.level_distribution != null && (
              <div className="rounded-lg border border-maref-border p-3">
                <p className="mb-2 text-[10px] text-maref-text-muted">决策层级分布</p>
                <div className="flex gap-3">
                  {Object.entries(policyStatus.level_distribution as Record<string, number>).map(([level, count]) => (
                    <span key={level} className="text-[10px] text-maref-text-muted">
                      {level}: {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="flex gap-2">
              {["full_auto", "semi_auto", "ask_mode"].map((mode) => (
                <button
                  key={mode}
                  onClick={async () => {
                    await api.desktopSetMode(mode);
                    setOperationMode(mode);
                    refreshPolicyStatus();
                  }}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-[11px] transition-colors",
                    operationMode === mode
                      ? "border-maref-accent bg-maref-accent/10 text-maref-accent"
                      : "border-maref-border bg-maref-surface-alt text-maref-text-muted hover:bg-maref-surface-alt/80",
                  )}
                >
                  {mode === "full_auto" ? "全自动" : mode === "semi_auto" ? "半自动" : "询问模式"}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Shield className="h-3.5 w-3.5" />
            治理看板
          </h3>
          <div className="space-y-3">
            <div className="grid grid-cols-4 gap-3">
              <StatTile
                icon={Shield}
                label="治理状态"
                value={governanceStatus?.state as string ?? "healthy"}
                color={
                  governanceStatus?.state === "healthy"
                    ? "bg-maref-success/20 text-maref-success"
                    : governanceStatus?.state === "locked"
                    ? "bg-maref-danger/20 text-maref-danger"
                    : "bg-maref-warning/20 text-maref-warning"
                }
              />
              <StatTile
                icon={Monitor}
                label="自治等级"
                value={`L${governanceStatus?.autonomy_level ?? 4}`}
                color="bg-maref-accent/20 text-maref-accent"
              />
              <StatTile
                icon={AlertTriangle}
                label="连续失败"
                value={`${governanceStatus?.consecutive_failures ?? 0} 次`}
                color={
                  Number(governanceStatus?.consecutive_failures ?? 0) >= 3
                    ? "bg-maref-danger/20 text-maref-danger"
                    : "bg-maref-success/20 text-maref-success"
                }
              />
              <StatTile
                icon={Clock}
                label="治理事件"
                value={`${governanceStatus?.total_events ?? 0} 条`}
                color="bg-maref-info/20 text-maref-info"
              />
            </div>
            {governanceEvents.length > 0 && (
              <div className="overflow-hidden rounded-lg border border-maref-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-maref-border bg-maref-surface-alt/50">
                      <th className="px-3 py-2 text-left font-medium text-maref-text-muted">动作</th>
                      <th className="px-3 py-2 text-left font-medium text-maref-text-muted">原因</th>
                      <th className="px-3 py-2 text-left font-medium text-maref-text-muted">状态转换</th>
                      <th className="px-3 py-2 text-right font-medium text-maref-text-muted">时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {governanceEvents.slice(-10).reverse().map((event, i) => (
                      <tr key={i} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                        <td className="px-3 py-2">
                          <span className={cn(
                            "rounded px-1.5 py-0.5 text-[10px]",
                            (event.action as string)?.includes("circuit") ? "bg-maref-danger/10 text-maref-danger"
                            : (event.action as string)?.includes("restore") ? "bg-maref-success/10 text-maref-success"
                            : "bg-maref-warning/10 text-maref-warning",
                          )}>
                            {event.action as string}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-maref-text truncate max-w-[200px]" title={event.reason as string}>{event.reason as string}</td>
                        <td className="px-3 py-2 text-maref-text-muted">
                          {event.previous_state as string} → {event.new_state as string}
                        </td>
                        <td className="px-3 py-2 text-right text-maref-text-muted">{formatTime(event.timestamp as number)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  await api.desktopSetGovernanceMode("degrade");
                  refreshGovernanceStatus();
                }}
                className="rounded-md border border-maref-warning/30 bg-maref-warning/10 px-3 py-1.5 text-[11px] text-maref-warning hover:bg-maref-warning/20"
              >
                降级模式
              </button>
              <button
                onClick={async () => {
                  await api.desktopSetGovernanceMode("escalate");
                  refreshGovernanceStatus();
                }}
                className="rounded-md border border-maref-danger/30 bg-maref-danger/10 px-3 py-1.5 text-[11px] text-maref-danger hover:bg-maref-danger/20"
              >
                人工升级
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-maref-border px-4 py-3">
      <div className={cn("rounded-lg p-2", color.split(" ")[0])}>
        <Icon className={cn("h-4 w-4", color.split(" ")[1])} />
      </div>
      <div>
        <div className="text-[11px] text-maref-text-muted">{label}</div>
        <div className="text-sm font-semibold text-maref-text">{value}</div>
      </div>
    </div>
  );
}
