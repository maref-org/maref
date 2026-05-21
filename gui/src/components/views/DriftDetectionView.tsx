import { BarChart3, TrendingUp, Gauge, Activity, AlertTriangle, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface DriftScenario {
  cls: string;
  kl: number;
  js: number;
  hd: number;
  detected: boolean;
  severity: "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
}

const SCENARIOS: DriftScenario[] = [
  { cls: "THEME_COLOR", kl: 0.003, js: 0.002, hd: 0.01, detected: false, severity: "NONE" },
  { cls: "LAYOUT_UPDATE", kl: 0.082, js: 0.035, hd: 0.12, detected: true, severity: "MEDIUM" },
  { cls: "OS_VERSION", kl: 0.015, js: 0.008, hd: 0.04, detected: false, severity: "LOW" },
  { cls: "RESOLUTION", kl: 0.004, js: 0.002, hd: 0.01, detected: false, severity: "NONE" },
  { cls: "LOCALE", kl: 0.007, js: 0.004, hd: 0.02, detected: false, severity: "NONE" },
  { cls: "FONT_RENDERING", kl: 0.022, js: 0.012, hd: 0.05, detected: false, severity: "LOW" },
  { cls: "WINDOW_SIZE", kl: 0.011, js: 0.006, hd: 0.03, detected: false, severity: "NONE" },
  { cls: "DARK_MODE", kl: 0.095, js: 0.048, hd: 0.15, detected: true, severity: "HIGH" },
  { cls: "NEW_ELEMENT", kl: 0.064, js: 0.031, hd: 0.10, detected: true, severity: "MEDIUM" },
  { cls: "ELEMENT_REMOVAL", kl: 0.121, js: 0.062, hd: 0.18, detected: true, severity: "CRITICAL" },
];

const SEVERITY_BADGES: Record<string, string> = {
  NONE: "bg-maref-success/10 text-maref-success",
  LOW: "bg-maref-info/10 text-maref-info",
  MEDIUM: "bg-maref-warning/10 text-maref-warning",
  HIGH: "bg-maref-danger/10 text-maref-danger",
  CRITICAL: "bg-maref-danger/20 text-maref-danger font-bold",
};

function BarCell({ value, max, unit }: { value: number; max: number; unit: string }) {
  const pct = (value / max) * 100;
  const color =
    pct > 80 ? "bg-maref-danger" :
    pct > 50 ? "bg-maref-warning" :
    pct > 20 ? "bg-maref-accent" :
    "bg-maref-success";
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="h-1.5 flex-1 rounded-full bg-maref-border overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-14 text-right text-xs font-mono tabular-nums">{value.toFixed(3)} {unit}</span>
    </div>
  );
}

export function DriftDetectionView() {
  const detected = SCENARIOS.filter((s) => s.detected).length;
  const avgKL = SCENARIOS.reduce((sum, s) => sum + s.kl, 0) / SCENARIOS.length;
  const avgJS = SCENARIOS.reduce((sum, s) => sum + s.js, 0) / SCENARIOS.length;

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <BarChart3 className="h-4 w-4 text-maref-accent" />
          漂移检测
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          10 类场景 · KL/JS/Hellinger 散度 · 自适应阈值 (KL=0.1, JS=0.05) · 检测率 {detected}/10
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        <div className="grid grid-cols-3 gap-3">
          <StatCard icon={Activity} label="检测到的漂移" value={`${detected} / 10`} color="bg-maref-warning/20 text-maref-warning" />
          <StatCard icon={TrendingUp} label="平均 KL 散度" value={avgKL.toFixed(3)} color="bg-maref-accent/20 text-maref-accent" />
          <StatCard icon={Gauge} label="平均 JS 散度" value={avgJS.toFixed(3)} color="bg-maref-info/20 text-maref-info" />
        </div>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <BarChart3 className="h-3.5 w-3.5" />
            场景指标
          </h3>
          <div className="overflow-hidden rounded-lg border border-maref-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-maref-border bg-maref-surface-alt">
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">场景</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">KL 散度</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">JS 散度</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">Hellinger</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">检测</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">级别</th>
                </tr>
              </thead>
              <tbody>
                {SCENARIOS.map((s) => (
                  <tr key={s.cls} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                    <td className="px-4 py-2 font-mono text-maref-text text-[11px]">{s.cls}</td>
                    <td className="px-4 py-2"><BarCell value={s.kl} max={0.15} unit="" /></td>
                    <td className="px-4 py-2"><BarCell value={s.js} max={0.08} unit="" /></td>
                    <td className="px-4 py-2"><BarCell value={s.hd} max={0.20} unit="" /></td>
                    <td className="px-4 py-2">
                      {s.detected ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-maref-warning" />
                      ) : (
                        <CheckCircle className="h-3.5 w-3.5 text-maref-success" />
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn("rounded px-1.5 py-0.5 text-[10px]", SEVERITY_BADGES[s.severity])}>
                        {s.severity}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Gauge className="h-3.5 w-3.5" />
            自适应阈值管理
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-maref-text">KL 阈值</span>
                <span className="text-xs text-maref-accent font-mono">0.100</span>
              </div>
              <div className="h-1.5 rounded-full bg-maref-border overflow-hidden">
                <div className="h-full w-[42%] rounded-full bg-maref-accent" />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-[10px] text-maref-text-muted">初始 0.05</span>
                <span className="text-[10px] text-maref-text-muted">自适应</span>
                <span className="text-[10px] text-maref-text-muted">上限 0.20</span>
              </div>
              <div className="mt-3 space-y-1 text-[11px]">
                <div className="flex justify-between text-maref-text-muted">
                  <span>目标 FPR</span><span className="text-maref-text">0.05</span>
                </div>
                <div className="flex justify-between text-maref-text-muted">
                  <span>目标 FNR</span><span className="text-maref-text">0.02</span>
                </div>
                <div className="flex justify-between text-maref-text-muted">
                  <span>学习率</span><span className="text-maref-text">0.10</span>
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-4 flex flex-col justify-center items-center">
              <div className="text-4xl font-bold text-maref-success">{detected * 10}%</div>
              <div className="text-xs text-maref-text-muted mt-1">综合检测率</div>
              <div className="flex items-center gap-1 mt-2 text-[10px] text-maref-text-muted">
                <span>TP: {detected}</span>
                <span className="text-maref-border">|</span>
                <span>FP: 0</span>
                <span className="text-maref-border">|</span>
                <span>FN: 0</span>
                <span className="text-maref-border">|</span>
                <span>TN: {10 - detected}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

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