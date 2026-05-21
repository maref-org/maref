import {
  TrendingUp,
  Star,
  Shield,
  CheckCircle,
  Activity,
  GitCommit,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface TrustFactor {
  name: string;
  weight: number;
  score: number;
  icon: React.ElementType;
  description: string;
}

const FACTORS: TrustFactor[] = [
  {
    name: "行为一致性",
    weight: 30,
    score: 92,
    icon: Activity,
    description: "状态转换规律性、决策延迟稳定性",
  },
  {
    name: "熔断器触发频率",
    weight: 25,
    score: 98,
    icon: AlertTriangle,
    description: "30min 内 CB 触发次数、恢复速度",
  },
  {
    name: "HALT 逃逸率",
    weight: 20,
    score: 100,
    icon: Shield,
    description: "HALT 吸收态零逃逸、模型检查通过",
  },
  {
    name: "任务完成率",
    weight: 15,
    score: 85,
    icon: CheckCircle,
    description: "桌面任务成功率、超时恢复能力",
  },
  {
    name: "VC 有效性",
    weight: 10,
    score: 100,
    icon: GitCommit,
    description: "W3C VC 签名验证、HMAC proof 通过",
  },
];

const HISTORY_POINTS = [88, 90, 87, 91, 89, 93, 92, 94, 95, 94];

function GaugeCircle({ score, label }: { score: number; label: string }) {
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color =
    score >= 90 ? "stroke-maref-success" :
    score >= 70 ? "stroke-maref-info" :
    score >= 50 ? "stroke-maref-warning" :
    "stroke-maref-danger";

  return (
    <div className="relative flex flex-col items-center">
      <svg width="130" height="130" viewBox="0 0 130 130">
        <circle
          cx="65" cy="65" r={radius}
          fill="none"
          stroke="var(--color-maref-border)"
          strokeWidth="10"
        />
        <circle
          cx="65" cy="65" r={radius}
          fill="none"
          className={color}
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 65 65)"
          style={{ transition: "stroke-dashoffset 1s ease-in-out" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-maref-text">{score}</span>
        <span className="text-[10px] text-maref-text-muted">{label}</span>
      </div>
    </div>
  );
}

export function TrustScoreView() {
  const overall = Math.round(
    FACTORS.reduce((sum, f) => sum + f.score * (f.weight / 100), 0)
  );

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <Star className="h-4 w-4 text-maref-accent" />
          信任评分
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          MAREF 信任引擎 · 5 因子加权评估 · HMAC 凭证验证 · DID 注册表
        </p>
      </div>

      <div className="flex-1 p-6 flex items-start gap-8">
        <div className="flex-1 space-y-5">
          <div className="flex items-center gap-6 justify-center">
            <GaugeCircle score={overall} label="综合信任分" />
          </div>

          <div className="space-y-2">
            {FACTORS.map((factor) => (
              <div key={factor.name} className={cn(
                "rounded-lg border px-4 py-3 transition-colors",
                factor.score >= 90
                  ? "border-maref-success/30 bg-maref-success/5"
                  : factor.score >= 80
                    ? "border-maref-info/30 bg-maref-info/5"
                    : "border-maref-warning/30 bg-maref-warning/5"
              )}>
                <div className="flex items-center gap-3 mb-1.5">
                  <factor.icon className={cn(
                    "h-4 w-4",
                    factor.score >= 90 ? "text-maref-success" :
                    factor.score >= 80 ? "text-maref-info" : "text-maref-warning"
                  )} />
                  <span className="text-xs font-medium text-maref-text">{factor.name}</span>
                  <span className="ml-auto text-[10px] text-maref-text-muted">
                    权重 {factor.weight}%
                  </span>
                  <span className={cn(
                    "text-sm font-bold",
                    factor.score >= 90 ? "text-maref-success" :
                    factor.score >= 80 ? "text-maref-info" : "text-maref-warning"
                  )}>
                    {factor.score}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-maref-border overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      factor.score >= 90 ? "bg-maref-success" :
                      factor.score >= 80 ? "bg-maref-info" : "bg-maref-warning"
                    )}
                    style={{ width: `${factor.score}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-maref-text-muted">{factor.description}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="w-64 flex-shrink-0 space-y-4">
          <div className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-4">
            <h4 className="flex items-center gap-1.5 mb-3 text-xs font-medium text-maref-text">
              <TrendingUp className="h-3.5 w-3.5 text-maref-accent" />
              历史趋势
            </h4>
            <div className="flex items-end gap-1 h-32">
              {HISTORY_POINTS.map((v, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className={cn(
                      "w-full rounded-t transition-all",
                      v >= 90 ? "bg-maref-success" :
                      v >= 85 ? "bg-maref-info" : "bg-maref-warning"
                    )}
                    style={{ height: `${(v / 100) * 100}%` }}
                  />
                  <span className="text-[9px] text-maref-text-muted">{v}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 flex justify-between text-[10px] text-maref-text-muted">
              <span>10 周期前</span>
              <span>当前</span>
            </div>
            <div className="mt-2 rounded bg-maref-success/10 px-2 py-1 text-center text-[10px] text-maref-success">
              趋势 ↑ +6 (88 → 94)
            </div>
          </div>

          <div className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-4">
            <h4 className="flex items-center gap-1.5 mb-3 text-xs font-medium text-maref-text">
              <Shield className="h-3.5 w-3.5 text-maref-info" />
              凭证信息
            </h4>
            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between">
                <span className="text-maref-text-muted">DID</span>
                <span className="text-maref-text font-mono text-[10px]">did:maref:agent-1</span>
              </div>
              <div className="flex justify-between">
                <span className="text-maref-text-muted">VC 签发</span>
                <span className="text-maref-text">2026-05-09</span>
              </div>
              <div className="flex justify-between">
                <span className="text-maref-text-muted">VC 到期</span>
                <span className="text-maref-text">2026-06-09</span>
              </div>
              <div className="flex justify-between">
                <span className="text-maref-text-muted">HMAC Proof</span>
                <span className="text-maref-success">✓ 有效</span>
              </div>
              <div className="flex justify-between">
                <span className="text-maref-text-muted">Escape 尝试</span>
                <span className="text-maref-success">0</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}