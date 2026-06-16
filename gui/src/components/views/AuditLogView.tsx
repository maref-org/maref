import { useState } from "react";
import {
  FileText,
  Search,
  Filter,
  Shield,
  AlertTriangle,
  GitCommit,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

type AuditType = "transition" | "decision" | "anomaly" | "operation" | "all";

const AUDIT_ENTRIES = [
  { id: 1, type: "transition", actor: "StateMachine", action: "INIT → OBSERVE", reason: "系统启动", severity: "INFO", time: "2026-05-09 14:00:01" },
  { id: 2, type: "transition", actor: "StateMachine", action: "OBSERVE → ANALYZE", reason: "探针读数就绪", severity: "INFO", time: "2026-05-09 14:01:23" },
  { id: 3, type: "decision", actor: "GovernanceOverlay", action: "ALLOW 操作", reason: "安全门评估通过", severity: "INFO", time: "2026-05-09 14:03:45" },
  { id: 4, type: "anomaly", actor: "DualThresholdDetector", action: "anomaly_probe 超阈值", reason: "主阈值 10.0 被触发", severity: "WARN", time: "2026-05-09 14:05:12" },
  { id: 5, type: "transition", actor: "StateMachine", action: "ACT → VERIFY", reason: "操作执行完毕", severity: "INFO", time: "2026-05-09 14:06:30" },
  { id: 6, type: "decision", actor: "CircuitBreaker", action: "CLOSED → OPEN", reason: "连续失败 5 次", severity: "ERROR", time: "2026-05-09 13:45:00" },
  { id: 7, type: "anomaly", actor: "OscillationProbe", action: "振荡检测触发", reason: "频率 12.0/s > 阈值 10.0", severity: "WARN", time: "2026-05-09 13:20:00" },
  { id: 8, type: "operation", actor: "DesktopAgent", action: "click / Finder 窗口", reason: "桌面自动化", severity: "INFO", time: "2026-05-09 13:15:00" },
  { id: 9, type: "transition", actor: "StateMachine", action: "STABILIZE → REPORT", reason: "稳定期结束", severity: "INFO", time: "2026-05-09 13:10:00" },
  { id: 10, type: "decision", actor: "HumanArbitration", action: "APPROVE 漂移事件", reason: "人工审批", severity: "INFO", time: "2026-05-09 12:55:00" },
  { id: 11, type: "anomaly", actor: "LatencyProbe", action: "延迟超标", reason: "决策延迟 8ms > 阈值 5ms", severity: "WARN", time: "2026-05-09 12:40:00" },
  { id: 12, type: "operation", actor: "DesktopAgent", action: "type / 搜索 Documents", reason: "桌面自动化", severity: "INFO", time: "2026-05-09 12:30:00" },
];

const TYPE_COLORS: Record<string, string> = {
  transition: "bg-maref-info/10 text-maref-info",
  decision: "bg-maref-accent/10 text-maref-accent",
  anomaly: "bg-maref-warning/10 text-maref-warning",
  operation: "bg-maref-success/10 text-maref-success",
};

const SEVERITY_COLORS: Record<string, string> = {
  INFO: "text-maref-info",
  WARN: "text-maref-warning",
  ERROR: "text-maref-danger",
};

const SEVERITY_ICONS: Record<string, React.ElementType> = {
  INFO: CheckCircle,
  WARN: AlertTriangle,
  ERROR: XCircle,
};

const TYPE_LABELS: Record<string, string> = {
  transition: "状态转换",
  decision: "治理决策",
  anomaly: "异常事件",
  operation: "桌面操作",
};

export function AuditLogView() {
  const [typeFilter, setTypeFilter] = useState<AuditType>("all");
  const [search, setSearch] = useState("");

  const filtered = AUDIT_ENTRIES.filter((entry) => {
    if (typeFilter !== "all" && entry.type !== typeFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        entry.actor.toLowerCase().includes(q) ||
        entry.action.toLowerCase().includes(q) ||
        entry.reason.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const counts = {
    transition: AUDIT_ENTRIES.filter((e) => e.type === "transition").length,
    decision: AUDIT_ENTRIES.filter((e) => e.type === "decision").length,
    anomaly: AUDIT_ENTRIES.filter((e) => e.type === "anomaly").length,
    operation: AUDIT_ENTRIES.filter((e) => e.type === "operation").length,
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <FileText className="h-4 w-4 text-maref-accent" />
          审计日志
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          ISO 27001 C.5.33 · 不可变 JSONL · 线程安全 · governance_audit.jsonl
        </p>
      </div>

      <div className="flex-1 space-y-4 p-6">
        <div className="grid grid-cols-4 gap-3">
          {(["transition", "decision", "anomaly", "operation"] as const).map((type) => (
            <button
              key={type}
              onClick={() => setTypeFilter(typeFilter === type ? "all" : type)}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors",
                typeFilter === type
                  ? "border-maref-accent/40 bg-maref-accent/5"
                  : "border-maref-border hover:bg-maref-surface-alt/30"
              )}
            >
              <div className={cn("rounded-lg p-2", TYPE_COLORS[type])}>
                {type === "transition" ? <GitCommit className="h-4 w-4" /> :
                 type === "decision" ? <Shield className="h-4 w-4" /> :
                 type === "anomaly" ? <AlertTriangle className="h-4 w-4" /> :
                 <FileText className="h-4 w-4" />}
              </div>
              <div>
                <div className="text-xs font-semibold text-maref-text">{counts[type]}</div>
                <div className="text-[11px] text-maref-text-muted">{TYPE_LABELS[type]}</div>
              </div>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-3 py-2">
          <Search className="h-3.5 w-3.5 text-maref-text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索角色、操作、原因…"
            className="flex-1 bg-transparent text-xs text-maref-text placeholder-maref-text-muted outline-none"
          />
          <Filter className="h-3.5 w-3.5 text-maref-text-muted" />
          <span className="text-[11px] text-maref-text-muted">
            {filtered.length} / {AUDIT_ENTRIES.length} 条
          </span>
        </div>

        <div className="overflow-hidden rounded-lg border border-maref-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-maref-border bg-maref-surface-alt">
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted w-8">#</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">时间</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">类型</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">角色</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">操作</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">原因</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">级别</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => {
                const SevIcon = SEVERITY_ICONS[entry.severity];
                return (
                  <tr key={entry.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                    <td className="px-4 py-2 text-maref-text-muted">{entry.id}</td>
                    <td className="px-4 py-2 text-maref-text-muted whitespace-nowrap">{entry.time}</td>
                    <td className="px-4 py-2">
                      <span className={cn("rounded px-1.5 py-0.5 text-[10px]", TYPE_COLORS[entry.type])}>
                        {TYPE_LABELS[entry.type]}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-maref-text">{entry.actor}</td>
                    <td className="px-4 py-2 text-maref-text font-medium">{entry.action}</td>
                    <td className="px-4 py-2 text-maref-text-muted">{entry.reason}</td>
                    <td className="px-4 py-2">
                      <span className={cn("flex items-center gap-1 font-medium", SEVERITY_COLORS[entry.severity])}>
                        <SevIcon className="h-3 w-3" />
                        {entry.severity}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
