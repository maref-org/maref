import {
  ChevronDown,
  ChevronUp,
  Activity,
  ShieldCheck,
  ShieldOff,
  Clock,
  Zap,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Users,
  Cpu,
  FileText,
  BarChart3,
  ShieldAlert,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useAuditStore } from "@/stores/auditStore";
import { useState, useEffect } from "react";

interface DetailSectionProps {
  title: string;
  icon: LucideIcon;
  defaultOpen?: boolean;
  children: React.ReactNode;
  accent?: string;
}

function DetailSection({
  title,
  icon: Icon,
  defaultOpen = true,
  children,
  accent,
}: DetailSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-maref-border last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-maref-text-muted hover:bg-maref-surface-alt/50 transition-colors"
      >
        <Icon
          className={cn("h-3 w-3", accent)}
        />
        <span className="flex-1 text-left">{title}</span>
        {open ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
      </button>
      {open && <div className="px-3 pb-3 text-xs">{children}</div>}
    </div>
  );
}

function StatusBadge({
  status,
}: {
  status: "active" | "idle" | "error" | "thinking" | "healthy" | "faulty" | "halted";
}) {
  const colors: Record<string, string> = {
    active: "bg-maref-success text-white",
    thinking: "bg-maref-accent text-white animate-pulse",
    idle: "bg-maref-text-muted/30 text-maref-text-muted",
    error: "bg-maref-danger text-white",
    healthy: "bg-maref-success/80 text-white",
    faulty: "bg-maref-danger/80 text-white",
    halted: "bg-maref-warning text-black",
  };

  const labels: Record<string, string> = {
    active: "活跃",
    thinking: "思考中",
    idle: "空闲",
    error: "错误",
    healthy: "健康",
    faulty: "故障",
    halted: "已暂停",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium",
        colors[status] || "bg-maref-surface-alt text-maref-text-muted"
      )}
    >
      {labels[status] || status}
    </span>
  );
}

function QuickMetric({
  label,
  value,
  unit,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon: LucideIcon;
}) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      <Icon className="h-3.5 w-3.5 flex-shrink-0 text-maref-text-muted" />
      <span className="text-maref-text-muted min-w-0 truncate">{label}</span>
      <span className="ml-auto flex-shrink-0 font-mono text-maref-text">
        {value}
        {unit && <span className="text-maref-text-muted ml-0.5">{unit}</span>}
      </span>
    </div>
  );
}

function formatRelativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp * 1000;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}秒前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

function severityColor(severity: string): string {
  switch (severity) {
    case "FATAL":
      return "text-maref-danger";
    case "ERROR":
      return "text-maref-danger";
    case "WARN":
      return "text-maref-warning";
    case "INFO":
      return "text-maref-info";
    default:
      return "text-maref-text-muted";
  }
}

function severityIcon(severity: string): LucideIcon {
  switch (severity) {
    case "FATAL":
    case "ERROR":
      return XCircle;
    case "WARN":
      return AlertTriangle;
    default:
      return CheckCircle2;
  }
}

export function DetailPanel() {
  const { terminalVisible } = useUIStore();
  const { activeSessionId, sessions } = useSessionStore();
  const {
    snapshot,
    events,
    stats,
    agents,
    integrity,
    startPolling,
    stopPolling,
  } = useAuditStore();
  const session = sessions.find((s) => s.id === activeSessionId);

  useEffect(() => {
    startPolling(5000);
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const circuitEvents = events.filter(
    (e) =>
      e.action === "halt" ||
      e.action === "trip" ||
      e.action === "recover" ||
      e.category === "governance"
  );

  const recentEvents = events.slice(0, 8);

  const cbColor =
    snapshot?.circuit_breaker === "CLOSED"
      ? "bg-maref-success"
      : snapshot?.circuit_breaker === "OPEN"
        ? "bg-maref-danger"
        : "bg-maref-warning";

  const smColor =
    snapshot?.state_machine === "HALT"
      ? "bg-maref-danger"
      : snapshot?.state_machine === "OBSERVE"
        ? "bg-maref-success"
        : "bg-maref-accent";

  return (
    <aside
      className="flex h-full flex-col border-l border-maref-border bg-maref-surface overflow-y-auto"
      style={{ width: "100%" }}
    >
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-maref-border">
        <span className="text-[11px] font-semibold tracking-wide text-maref-text-muted uppercase">
          详情
        </span>
        {integrity && (
          <span
            className={cn(
              "text-[10px] font-medium",
              integrity.intact
                ? "text-maref-success"
                : "text-maref-danger"
            )}
          >
            {integrity.intact ? "审计完整" : `⚠ ${integrity.tampered} 篡改`}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {session && (
          <DetailSection title="Agent 会话" icon={Activity} defaultOpen>
            <div className="space-y-0.5">
              <div className="text-maref-text font-medium truncate">
                {session.title}
              </div>
              <div className="flex items-center gap-1.5">
                <StatusBadge
                  status={
                    session.status === "active" || session.status === "thinking"
                      ? session.status
                      : "idle"
                  }
                />
                <span className="text-[10px] text-maref-text-muted">
                  {session.mode === "agent" ? "Agent" : session.mode === "full-access" ? "全权限" : "对话"}
                </span>
              </div>
            </div>
            <div className="mt-2 space-y-0">
              <QuickMetric label="模型" value={session.model} icon={Cpu} />
              <QuickMetric
                label="上下文"
                value={session.contextPercent}
                unit="%"
                icon={BarChart3}
              />
              <QuickMetric
                label="提供商"
                value={session.provider}
                icon={Zap}
              />
              <QuickMetric
                label="创建"
                value={
                  new Date(session.createdAt).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }
                icon={Clock}
              />
            </div>
          </DetailSection>
        )}

        {snapshot && (
          <DetailSection
            title="治理状态"
            icon={snapshot.halted ? ShieldAlert : ShieldCheck}
            accent={snapshot.halted ? "text-maref-danger" : "text-maref-success"}
          >
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <div className={cn("h-2 w-2 rounded-full", smColor)} />
                <span className="text-maref-text">
                  状态机: {snapshot.state_machine}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className={cn("h-2 w-2 rounded-full", cbColor)} />
                <span className="text-maref-text">
                  断路器: {snapshot.circuit_breaker}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    "h-2 w-2 rounded-full",
                    snapshot.entropy > 7
                      ? "bg-maref-danger"
                      : snapshot.entropy > 4
                        ? "bg-maref-warning"
                        : "bg-maref-text-muted/40"
                  )}
                />
                <span className="text-maref-text-muted">
                  熵值: {snapshot.entropy}
                </span>
              </div>
              {snapshot.oscillation_rate > 0 && (
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-3 w-3 text-maref-text-muted" />
                  <span className="text-maref-text-muted">
                    振荡率: {snapshot.oscillation_rate.toFixed(1)}/s
                  </span>
                </div>
              )}
            </div>
          </DetailSection>
        )}

        {agents.length > 0 && (
          <DetailSection title="代理健康" icon={Users} accent="text-maref-success">
            <div className="space-y-1.5">
              {agents.map((agent) => (
                <div
                  key={agent.id}
                  className="flex items-center justify-between"
                >
                  <span className="text-maref-text truncate max-w-[120px]">
                    {agent.name}
                  </span>
                  <StatusBadge status={agent.status} />
                </div>
              ))}
            </div>
          </DetailSection>
        )}

        {!agents.length && (
          <DetailSection title="代理健康" icon={Users} accent="text-maref-text-muted">
            <div className="text-maref-text-muted text-[11px] py-1">
              等待后端数据...
            </div>
          </DetailSection>
        )}

        {recentEvents.length > 0 && (
          <DetailSection title="最近事件" icon={FileText}>
            <div className="space-y-1.5 text-[10px] max-h-[180px] overflow-y-auto">
              {recentEvents.map((event) => {
                const Icon = severityIcon(event.severity);
                return (
                  <div
                    key={event.event_id}
                    className="flex items-start gap-1.5"
                  >
                    <Icon
                      className={cn(
                        "h-3 w-3 flex-shrink-0 mt-0.5",
                        severityColor(event.severity)
                      )}
                    />
                    <div className="min-w-0">
                      <span className="text-maref-text-muted truncate block">
                        {event.action} · {event.resource}
                      </span>
                      <span className="text-maref-text-muted/60">
                        {formatRelativeTime(event.timestamp)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </DetailSection>
        )}

        {circuitEvents.length > 0 && (
          <DetailSection
            title="断路器历史"
            icon={ShieldOff}
            accent="text-maref-warning"
            defaultOpen={false}
          >
            <div className="space-y-1.5 text-[10px] text-maref-text-muted max-h-[120px] overflow-y-auto">
              {circuitEvents.map((event) => {
                const Icon = event.action === "recover" ? CheckCircle2 : XCircle;
                const color =
                  event.action === "recover"
                    ? "text-maref-success"
                    : "text-maref-danger";
                return (
                  <div
                    key={event.event_id}
                    className="flex items-start gap-1.5"
                  >
                    <Icon
                      className={cn("h-3 w-3 flex-shrink-0 mt-0.5", color)}
                    />
                    <div className="min-w-0">
                      <span className="truncate block">
                        {event.action === "halt"
                          ? "Trip"
                          : event.action === "recover"
                            ? "恢复"
                            : event.action}{" "}
                        · {event.metadata?.reason || event.resource}
                      </span>
                      <span className="text-maref-text-muted/60">
                        {formatRelativeTime(event.timestamp)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </DetailSection>
        )}

        {stats && (
          <DetailSection title="审计统计" icon={BarChart3} defaultOpen={false}>
            <div className="space-y-1.5">
              <QuickMetric
                label="事件总数"
                value={stats.total_events}
                icon={FileText}
              />
              <QuickMetric
                label="订阅者"
                value={stats.subscriber_count}
                icon={Users}
              />
              {Object.entries(stats.by_severity).length > 0 && (
                <div className="mt-1 pt-1 border-t border-maref-border/50">
                  <span className="text-[10px] text-maref-text-muted">
                    按严重程度
                  </span>
                  {Object.entries(stats.by_severity).map(([sev, count]) => (
                    <div
                      key={sev}
                      className="flex items-center justify-between mt-0.5"
                    >
                      <span
                        className={cn("text-[10px]", severityColor(sev))}
                      >
                        {sev}
                      </span>
                      <span className="font-mono text-maref-text">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </DetailSection>
        )}
      </div>

      <div className="border-t border-maref-border px-3 py-2">
        <div className="flex items-center gap-1.5 text-[10px] text-maref-text-muted">
          <Clock className="h-3 w-3" />
          <span>MAREF v0.30.0-GA</span>
          <span className="ml-auto">
            {terminalVisible ? "终端已开启" : "终端已关闭"}
          </span>
        </div>
      </div>
    </aside>
  );
}