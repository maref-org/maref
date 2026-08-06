import { useEffect } from "react";
import {
  Shield,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Activity,
  Clock,
  Gauge,
  Ban,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useGuardrailsStore } from "@/stores/guardrailsStore";

function StatCard({
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
    <div className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
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

const GATE_VERDICT_COLORS: Record<string, string> = {
  ALLOW: "text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950",
  DENY: "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950",
  AUDIT: "text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950",
};

export function GuardrailsView() {
  const {
    totalChecks,
    allowRate,
    denyRate,
    auditRate,
    riskScores,
    openCircuitBreakers,
    activeDenials,
    recentEvents,
    loading,
    fetchStats,
    fetchRecentEvents,
    startPolling,
    stopPolling,
  } = useGuardrailsStore();

  useEffect(() => {
    fetchStats();
    fetchRecentEvents();
    startPolling(3000);
    return () => stopPolling();
  }, [fetchStats, fetchRecentEvents, startPolling, stopPolling]);

  const denyColor = denyRate > 30
    ? "bg-maref-danger/20 text-maref-danger"
    : denyRate > 15
      ? "bg-maref-warning/20 text-maref-warning"
      : "bg-maref-success/20 text-maref-success";

  const cbColor = openCircuitBreakers > 0
    ? "bg-maref-danger/20 text-maref-danger"
    : "bg-maref-success/20 text-maref-success";

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <Shield className="h-4 w-4 text-maref-accent" />
          护栏监控
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          安全门 · 策略引擎 · 熔断器 · HITL 指标
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        {loading && (
          <div className="text-xs text-maref-text-muted text-center py-2">
            加载中…
          </div>
        )}

        <div className="grid grid-cols-4 gap-3">
          <StatCard
            icon={Activity}
            label="总检查次数"
            value={String(totalChecks)}
            color="bg-maref-info/20 text-maref-info"
          />
          <StatCard
            icon={CheckCircle}
            label="允许率"
            value={`${allowRate}%`}
            color="bg-maref-success/20 text-maref-success"
          />
          <StatCard
            icon={XCircle}
            label="拒绝率"
            value={`${denyRate}%`}
            color={denyColor}
          />
          <StatCard
            icon={Ban}
            label="开放熔断器"
            value={String(openCircuitBreakers)}
            color={cbColor}
          />
        </div>

        <div className="grid grid-cols-4 gap-3">
          <StatCard
            icon={Gauge}
            label="活跃拒绝数"
            value={String(activeDenials)}
            color="bg-maref-warning/20 text-maref-warning"
          />
          <StatCard
            icon={AlertTriangle}
            label="审计率"
            value={`${auditRate}%`}
            color="bg-maref-accent/20 text-maref-accent"
          />
          <StatCard
            icon={Clock}
            label="监控 Agent"
            value={String(riskScores.length)}
            color="bg-maref-info/20 text-maref-info"
          />
          <div />
        </div>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Gauge className="h-3.5 w-3.5" />
            风险评分
          </h3>
          {riskScores.length === 0 ? (
            <div className="text-xs text-maref-text-muted">暂无风险数据</div>
          ) : (
            <div className="space-y-2">
              {riskScores.map((rs) => {
                const barColor = rs.score > 80
                  ? "bg-maref-danger"
                  : rs.score > 50
                    ? "bg-maref-warning"
                    : "bg-maref-info";
                return (
                  <div
                    key={rs.agentId}
                    className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface px-4 py-2.5"
                  >
                    <span className="w-32 truncate text-xs font-mono text-maref-text">
                      {rs.agentId}
                    </span>
                    <div className="flex-1 h-2 rounded-full bg-maref-surface-alt">
                      <div
                        className={cn("h-2 rounded-full transition-all", barColor)}
                        style={{ width: `${rs.score}%` }}
                      />
                    </div>
                    <span
                      className={cn(
                        "w-10 text-right text-xs font-mono",
                        rs.score > 80
                          ? "text-maref-danger"
                          : rs.score > 50
                            ? "text-maref-warning"
                            : "text-maref-text-muted",
                      )}
                    >
                      {rs.score}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Activity className="h-3.5 w-3.5" />
            最近事件
          </h3>
          {recentEvents.length === 0 ? (
            <div className="text-xs text-maref-text-muted">暂无事件记录</div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-maref-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-maref-border bg-maref-surface-alt/50">
                    <th className="px-3 py-2 text-left font-semibold text-maref-text-muted">判决</th>
                    <th className="px-3 py-2 text-left font-semibold text-maref-text-muted">关卡</th>
                    <th className="px-3 py-2 text-right font-semibold text-maref-text-muted">耗时</th>
                    <th className="px-3 py-2 text-right font-semibold text-maref-text-muted">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {recentEvents.map((event, idx) => (
                    <tr
                      key={idx}
                      className="border-b border-maref-border/50 last:border-b-0 hover:bg-maref-surface-alt/30"
                    >
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium",
                            GATE_VERDICT_COLORS[event.verdict] ?? "",
                          )}
                        >
                          {event.verdict}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-maref-text-muted font-mono">{event.gate}</td>
                      <td className="px-3 py-2 text-right text-maref-text-muted font-mono">
                        {event.duration.toFixed(1)}ms
                      </td>
                      <td className="px-3 py-2 text-right text-maref-text-muted">
                        {event.timestamp}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
