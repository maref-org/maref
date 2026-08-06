import { AlertTriangle, Activity, Clock, BarChart3, Target } from "lucide-react";
import { cn } from "@/lib/utils";

interface ProbeMetric {
  name: string;
  value: number;
  primaryThreshold: number;
  shadowThreshold: number;
  status: "ok" | "warning" | "critical";
  unit: string;
  trend: "up" | "down" | "stable";
}

const PROBES: ProbeMetric[] = [
  { name: "entropy", value: 2.0, primaryThreshold: 4.0, shadowThreshold: 2.0, status: "ok", unit: "/4", trend: "stable" },
  { name: "anomaly", value: 3.0, primaryThreshold: 10.0, shadowThreshold: 3.0, status: "warning", unit: " events", trend: "down" },
  { name: "latency", value: 2.1, primaryThreshold: 5.0, shadowThreshold: 1.0, status: "warning", unit: "ms", trend: "up" },
  { name: "kg", value: 0.12, primaryThreshold: 0.95, shadowThreshold: 0.50, status: "ok", unit: "", trend: "stable" },
  { name: "oscillation", value: 2.5, primaryThreshold: 10.0, shadowThreshold: 4.0, status: "ok", unit: "/s", trend: "down" },
];

interface AnomalyEvent {
  time: string;
  probe: string;
  value: number;
  threshold: number;
  severity: string;
  description: string;
}

const ANOMALY_EVENTS: AnomalyEvent[] = [
  { time: "14:05", probe: "anomaly", value: 11.2, threshold: 10.0, severity: "HIGH", description: "anomaly_probe 主阈值触发" },
  { time: "13:20", probe: "oscillation", value: 12.0, threshold: 10.0, severity: "MEDIUM", description: "振荡频率超标" },
  { time: "12:40", probe: "latency", value: 8.1, threshold: 5.0, severity: "LOW", description: "决策延迟轻微超标" },
  { time: "11:55", probe: "entropy", value: 3.9, threshold: 4.0, severity: "LOW", description: "熵值接近上限" },
];

const FNR_FPR = [
  { batch: "B1", fnr: 0.12, fpr: 0.03, tp: 14, fp: 1, tn: 32, fn: 2 },
  { batch: "B2", fnr: 0.08, fpr: 0.02, tp: 16, fp: 1, tn: 34, fn: 1 },
  { batch: "B3", fnr: 0.05, fpr: 0.01, tp: 18, fp: 0, tn: 35, fn: 1 },
  { batch: "B4", fnr: 0.03, fpr: 0.02, tp: 19, fp: 1, tn: 33, fn: 0 },
  { batch: "B5", fnr: 0.01, fpr: 0.01, tp: 20, fp: 0, tn: 34, fn: 0 },
];

const STATUS_BADGES: Record<string, string> = {
  ok: "bg-maref-success/10 text-maref-success border-maref-success/30",
  warning: "bg-maref-warning/10 text-maref-warning border-maref-warning/30",
  critical: "bg-maref-danger/10 text-maref-danger border-maref-danger/30",
};

const STATUS_LABELS: Record<string, string> = {
  ok: "正常",
  warning: "注意",
  critical: "危险",
};

function ProbeCard({ probe }: { probe: ProbeMetric }) {
  const pct = Math.min(100, (probe.value / probe.primaryThreshold) * 100);
  const barColor =
    probe.status === "critical" ? "bg-maref-danger" :
    probe.status === "warning" ? "bg-maref-warning" :
    "bg-maref-success";

  return (
    <div className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-maref-text">{probe.name}</span>
        <span className={cn("rounded-full border px-2 py-0.5 text-[10px]", STATUS_BADGES[probe.status])}>
          {STATUS_LABELS[probe.status]}
        </span>
      </div>
      <div className="text-lg font-bold text-maref-text mb-1">
        {probe.value}
        <span className="text-xs text-maref-text-muted ml-0.5">{probe.unit}</span>
      </div>
      <div className="h-1.5 rounded-full bg-maref-border overflow-hidden mb-1">
        <div className={cn("h-full rounded-full transition-all", barColor)} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-maref-text-muted">
        <span>主阈值 {probe.primaryThreshold}</span>
        <span className="flex items-center gap-0.5">
          {probe.trend === "up" ? "↑" : probe.trend === "down" ? "↓" : "→"}
        </span>
      </div>
    </div>
  );
}

export function AnomalyMonitorView() {
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <AlertTriangle className="h-4 w-4 text-maref-accent" />
          异常监控
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          5 探针 · 双阈值检测 · 趋势分析 · FNR/FPR 追踪 · 混淆矩阵
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Activity className="h-3.5 w-3.5" />
            探针状态
          </h3>
          <div className="grid grid-cols-5 gap-3">
            {PROBES.map((p) => (
              <ProbeCard key={p.name} probe={p} />
            ))}
          </div>
        </section>

        <div className="grid grid-cols-2 gap-4">
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <AlertTriangle className="h-3.5 w-3.5" />
              最近异常事件
            </h3>
            <div className="space-y-2">
              {ANOMALY_EVENTS.map((ev, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-2.5">
                  <Clock className="h-3 w-3 text-maref-text-muted" />
                  <span className="text-xs text-maref-text-muted whitespace-nowrap">{ev.time}</span>
                  <span className="text-xs text-maref-text font-medium">{ev.probe}</span>
                  <span className="flex-1 text-xs text-maref-text">{ev.description}</span>
                  <span className="text-xs text-maref-text-muted">
                    {ev.value} / {ev.threshold}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <Target className="h-3.5 w-3.5" />
              FNR / FPR 追踪
            </h3>
            <div className="overflow-hidden rounded-lg border border-maref-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-maref-border bg-maref-surface-alt">
                    <th className="px-3 py-2 text-left font-medium text-maref-text-muted">批次</th>
                    <th className="px-3 py-2 text-left font-medium text-maref-text-muted">FNR</th>
                    <th className="px-3 py-2 text-left font-medium text-maref-text-muted">FPR</th>
                    <th className="px-3 py-2 text-left font-medium text-maref-text-muted">TP</th>
                    <th className="px-3 py-2 text-left font-medium text-maref-text-muted">FP</th>
                  </tr>
                </thead>
                <tbody>
                  {FNR_FPR.map((row) => (
                    <tr key={row.batch} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                      <td className="px-3 py-1.5 text-maref-text font-medium">{row.batch}</td>
                      <td className="px-3 py-1.5">
                        <span className={cn(row.fnr > 0.05 ? "text-maref-danger" : "text-maref-success")}>
                          {(row.fnr * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="px-3 py-1.5">
                        <span className={cn(row.fpr > 0.03 ? "text-maref-warning" : "text-maref-success")}>
                          {(row.fpr * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-maref-text">{row.tp}</td>
                      <td className="px-3 py-1.5 text-maref-text">{row.fp}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2 flex items-center gap-1 rounded-lg bg-maref-surface-alt/30 px-3 py-1.5 text-[10px]">
              <BarChart3 className="h-3 w-3 text-maref-accent" />
              <span className="text-maref-text-muted">
                FNR 从 12% 下降至 1% · FPR 稳定在 1-3% · 经 5 批次校正 66.7% FNR
              </span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
