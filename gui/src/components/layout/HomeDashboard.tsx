import {
  Activity,
  Shield,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  Zap,
  Cpu,
  GitCommit,
} from "lucide-react";
import { cn } from "@/lib/utils";

type GovState =
  | "INIT"
  | "OBSERVE"
  | "ANALYZE"
  | "EVALUATE"
  | "DECIDE"
  | "ACT"
  | "VERIFY"
  | "STABILIZE"
  | "REPORT"
  | "HALT";

const GOV_STATES: GovState[] = [
  "INIT", "OBSERVE", "ANALYZE", "EVALUATE", "DECIDE",
  "ACT", "VERIFY", "STABILIZE", "REPORT", "HALT",
];

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color?: string;
}

function StatCard({ icon: Icon, label, value, color }: StatCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
      <div className={cn("rounded-lg p-2", color ?? "bg-maref-accent/20")}>
        <Icon className={cn("h-4 w-4", color ? color.replace("bg-", "text-") : "text-maref-accent")} />
      </div>
      <div>
        <div className="text-[11px] text-maref-text-muted">{label}</div>
        <div className="text-sm font-semibold text-maref-text">{value}</div>
      </div>
    </div>
  );
}

export function HomeDashboard() {
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="text-sm font-semibold text-maref-text">MAREF 仪表盘</h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          治理状态 · 漂移检测 · 安全审计
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Activity className="h-3.5 w-3.5" />
            治理状态机
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {GOV_STATES.map((state) => (
              <div
                key={state}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium transition-colors",
                  state === "OBSERVE"
                    ? "border-maref-info/40 bg-maref-info/10 text-maref-info"
                    : "border-maref-border bg-maref-surface-alt text-maref-text-muted"
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    state === "OBSERVE" ? "bg-maref-info animate-pulse" : "bg-maref-text-muted"
                  )}
                />
                {state}
              </div>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-3 gap-3">
            <StatCard icon={Zap} label="熵值" value={2} color="bg-maref-warning/20" />
            <StatCard icon={GitCommit} label="状态转换次数" value={147} color="bg-maref-accent/20" />
            <StatCard icon={CheckCircle} label="治理决策" value="12 通过 / 0 阻止" color="bg-maref-success/20" />
          </div>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Shield className="h-3.5 w-3.5" />
            安全状态
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              icon={Shield}
              label="熔断器"
              value="CLOSED"
              color="bg-maref-success/20"
            />
            <StatCard
              icon={AlertTriangle}
              label="异常事件"
              value="0 (24h)"
              color="bg-maref-info/20"
            />
            <StatCard
              icon={Cpu}
              label="桌面安全门"
              value="ACTIVE"
              color="bg-maref-success/20"
            />
            <StatCard
              icon={TrendingUp}
              label="漂移检测率"
              value="94.7%"
              color="bg-maref-accent/20"
            />
          </div>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Zap className="h-3.5 w-3.5" />
            最近治理事件
          </h3>
          <div className="space-y-2">
            {[
              { time: "2 min ago", event: "OBSERVE → ANALYZE", type: "transition" },
              { time: "5 min ago", event: "探针 anomaly_probe 超过主阈值 10.0", type: "warning" },
              { time: "12 min ago", event: "漂移检测: layout_update (JS=0.08)", type: "info" },
              { time: "18 min ago", event: "熔断器 CLOSED → HALF_OPEN → CLOSED", type: "recovery" },
            ].map((item, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/30 px-4 py-2.5"
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full flex-shrink-0",
                    item.type === "transition"
                      ? "bg-maref-info"
                      : item.type === "warning"
                        ? "bg-maref-warning"
                        : item.type === "recovery"
                          ? "bg-maref-success"
                          : "bg-maref-accent"
                  )}
                />
                <span className="flex-1 text-xs text-maref-text">{item.event}</span>
                <span className="text-[11px] text-maref-text-muted">{item.time}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}