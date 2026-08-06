import { useState, useEffect, useCallback } from "react";
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
import { api } from "@/api/client";

type AuditType = "transition" | "decision" | "anomaly" | "operation" | "all";

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
  const [entries, setEntries] = useState<Array<{ id: number; type: string; actor: string; action: string; reason: string; severity: string; time: string }>>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 100;

  const loadLogs = useCallback(async (nextOffset = 0, append = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAuditLogs({
        type: typeFilter !== "all" ? typeFilter : undefined,
        search: search || undefined,
        limit,
        offset: nextOffset,
      });
      setEntries((prev) => append ? [...prev, ...res.entries] : res.entries);
      setCounts(res.counts);
      setTotal(res.total);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, search, limit]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOffset(0);
    loadLogs(0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter, search]);

  const loadMore = useCallback(async () => {
    const nextOffset = offset + limit;
    setOffset(nextOffset);
    await loadLogs(nextOffset, true);
  }, [offset, limit, loadLogs]);

  const exportCsv = useCallback(() => {
    const headers = ["id", "time", "type", "actor", "action", "reason", "severity"];
    const rows = entries.map((e) =>
      headers.map((h) => JSON.stringify(String((e as Record<string, unknown>)[h] ?? ""))).join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [entries]);

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
                <div className="text-xs font-semibold text-maref-text">{counts[type] ?? 0}</div>
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
            {entries.length} / {total} 条
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-sm text-maref-text-muted">
            加载中…
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-20 text-sm text-maref-danger">
            加载失败: {error}
          </div>
        ) : (
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
                {entries.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-16 text-center text-maref-text-muted">
                      暂无审计日志
                    </td>
                  </tr>
                ) : (
                  entries.map((entry) => {
                    const SevIcon = SEVERITY_ICONS[entry.severity] ?? CheckCircle;
                    return (
                      <tr key={entry.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                        <td className="px-4 py-2 text-maref-text-muted">{entry.id}</td>
                        <td className="px-4 py-2 text-maref-text-muted whitespace-nowrap">{entry.time}</td>
                        <td className="px-4 py-2">
                          <span className={cn("rounded px-1.5 py-0.5 text-[10px]", TYPE_COLORS[entry.type] ?? TYPE_COLORS.operation)}>
                            {TYPE_LABELS[entry.type] ?? entry.type}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-maref-text">{entry.actor}</td>
                        <td className="px-4 py-2 text-maref-text font-medium">{entry.action}</td>
                        <td className="px-4 py-2 text-maref-text-muted">{entry.reason}</td>
                        <td className="px-4 py-2">
                          <span className={cn("flex items-center gap-1 font-medium", SEVERITY_COLORS[entry.severity] ?? "text-maref-text-muted")}>
                            <SevIcon className="h-3 w-3" />
                            {entry.severity}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
        {entries.length > 0 && (
          <div className="flex items-center justify-between pt-2">
            <button
              onClick={exportCsv}
              className="flex items-center gap-1.5 rounded-lg border border-maref-border bg-maref-surface-alt px-3 py-1.5 text-xs text-maref-text-muted hover:text-maref-text"
            >
              Export CSV
            </button>
            {entries.length < total && (
              <button
                onClick={loadMore}
                disabled={loading}
                className="flex items-center gap-1.5 rounded-lg border border-maref-border bg-maref-surface-alt px-3 py-1.5 text-xs text-maref-text-muted hover:text-maref-text disabled:opacity-50"
              >
                Load More ({entries.length} / {total})
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
