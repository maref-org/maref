import { useEffect } from "react";
import {
  Shield,
  Activity,
  GitCommit,
  Zap,
  AlertTriangle,
  TrendingUp,
  History,
  Gauge,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useGovernanceStore } from "@/stores/governanceStore";

type GovState =
  | "INIT" | "OBSERVE" | "ANALYZE" | "EVALUATE" | "DECIDE"
  | "ACT" | "VERIFY" | "STABILIZE" | "REPORT" | "HALT";

const GOV_STATES: GovState[] = [
  "INIT", "OBSERVE", "ANALYZE", "EVALUATE", "DECIDE",
  "ACT", "VERIFY", "STABILIZE", "REPORT", "HALT",
];

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

export function GovernanceView() {
  const {
    state, entropy, entropyMax, transitionCount, circuitBreaker,
    transitions, cbEvents, oscEvents, loading,
    refreshAll,
  } = useGovernanceStore();

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const entropyColor =
    entropy > entropyMax * 0.7
      ? "bg-maref-danger/20 text-maref-danger"
      : entropy > entropyMax * 0.4
        ? "bg-maref-warning/20 text-maref-warning"
        : "bg-maref-info/20 text-maref-info";

  const cbColor = circuitBreaker === "OPEN"
    ? "bg-maref-danger/20 text-maref-danger"
    : circuitBreaker === "HALF_OPEN"
      ? "bg-maref-warning/20 text-maref-warning"
      : "bg-maref-success/20 text-maref-success";

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <Shield className="h-4 w-4 text-maref-accent" />
          治理看板
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          10 状态 Gray 码 · 熔断器 · 振荡修复 · 审计追踪
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        {loading && (
          <div className="text-xs text-maref-text-muted text-center py-2">
            加载中…
          </div>
        )}

        <div className="grid grid-cols-4 gap-3">
          <StatCard icon={Activity} label="当前状态" value={state} color="bg-maref-info/20 text-maref-info" />
          <StatCard icon={Zap} label="熵值" value={`${entropy} / ${entropyMax}`} color={entropyColor} />
          <StatCard icon={GitCommit} label="转换次数" value={String(transitionCount)} color="bg-maref-accent/20 text-maref-accent" />
          <StatCard icon={Gauge} label="熔断器" value={circuitBreaker} color={cbColor} />
        </div>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <GitCommit className="h-3.5 w-3.5" />
            状态机 (Gray 码)
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {GOV_STATES.map((s) => (
              <div
                key={s}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium transition-all",
                  s === state
                    ? "border-maref-info/40 bg-maref-info/10 text-maref-info shadow-[0_0_8px_rgba(59,130,246,0.15)]"
                    : s === "HALT"
                      ? "border-maref-danger/30 bg-maref-danger/10 text-maref-danger/70"
                      : "border-maref-border bg-maref-surface-alt text-maref-text-muted"
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    s === state
                      ? "bg-maref-info animate-pulse"
                      : s === "HALT"
                        ? "bg-maref-danger"
                        : "bg-maref-text-muted"
                  )}
                />
                {s}
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-maref-text-muted">
            Hamming 距离 = 1 · BFS 最短路径强制 · HALT 吸收态 · 熵值山峰分布 (ACT=4)
          </p>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <History className="h-3.5 w-3.5" />
            转换历史
          </h3>
          <div className="overflow-hidden rounded-lg border border-maref-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-maref-border bg-maref-surface-alt">
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">从</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">到</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">原因</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">状态</th>
                  <th className="px-4 py-2.5 text-right font-medium text-maref-text-muted">时间</th>
                </tr>
              </thead>
              <tbody>
                {transitions.map((t, i) => (
                  <tr key={i} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                    <td className="px-4 py-2 text-maref-text-muted">{t.from}</td>
                    <td className="px-4 py-2">
                      <span className={cn(t.from === state ? "text-maref-info font-medium" : "text-maref-text")}>
                        {t.to}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-maref-text">{t.reason}</td>
                    <td className="px-4 py-2">
                      {t.valid ? (
                        <span className="text-maref-success">✓ 有效</span>
                      ) : (
                        <span className="text-maref-danger">✗ 无效</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right text-maref-text-muted">{t.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid grid-cols-2 gap-4">
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <AlertTriangle className="h-3.5 w-3.5" />
              熔断器事件
            </h3>
            <div className="space-y-2">
              {cbEvents.map((ev, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-2.5">
                  <div className="flex items-center gap-1.5 flex-1">
                    <span className="text-maref-text-muted text-xs">{ev.from}</span>
                    <span className="text-maref-text-muted">→</span>
                    <span className={cn(
                      "text-xs font-medium",
                      ev.to === "OPEN" ? "text-maref-danger" : ev.to === "HALF_OPEN" ? "text-maref-warning" : "text-maref-success"
                    )}>
                      {ev.to}
                    </span>
                  </div>
                  <span className="text-xs text-maref-text">{ev.reason}</span>
                  <span className="text-[11px] text-maref-text-muted">{ev.time}</span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <TrendingUp className="h-3.5 w-3.5" />
              振荡修复
            </h3>
            <div className="space-y-2">
              {oscEvents.map((ev, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-2.5">
                  <span className="rounded bg-maref-accent/20 px-1.5 py-0.5 text-[10px] font-medium text-maref-accent">
                    {ev.stage}
                  </span>
                  <span className="flex-1 text-xs text-maref-text">{ev.desc}</span>
                  <Clock className="h-3 w-3 text-maref-text-muted" />
                  <span className="text-[11px] text-maref-text-muted">{ev.time}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
