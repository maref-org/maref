import { AlertTriangle, Shield, ShieldAlert, ShieldOff } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  operation: string;
  description: string;
  risk: "low" | "medium" | "high" | "critical";
  onAllow?: () => void;
  onBlock?: () => void;
  onAsk?: () => void;
}

const RISK_CONFIG: Record<string, { icon: React.ElementType; bg: string; border: string; text: string; label: string }> = {
  low: {
    icon: Shield,
    bg: "bg-maref-info/5",
    border: "border-maref-info/30",
    text: "text-maref-info",
    label: "低风险",
  },
  medium: {
    icon: ShieldAlert,
    bg: "bg-maref-warning/5",
    border: "border-maref-warning/40",
    text: "text-maref-warning",
    label: "中等风险",
  },
  high: {
    icon: ShieldOff,
    bg: "bg-maref-danger/5",
    border: "border-maref-danger/40",
    text: "text-maref-danger",
    label: "高风险",
  },
  critical: {
    icon: AlertTriangle,
    bg: "bg-maref-danger/10",
    border: "border-maref-danger/60",
    text: "text-maref-danger",
    label: "严重风险",
  },
};

export function PermissionBanner({
  operation,
  description,
  risk,
  onAllow,
  onBlock,
  onAsk,
}: Props) {
  const config = RISK_CONFIG[risk] ?? RISK_CONFIG.low;
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "mt-1.5 rounded-lg border px-3 py-2 flex flex-col gap-2",
        config.bg,
        config.border
      )}
    >
      <div className="flex items-start gap-2">
        <Icon className={cn("h-4 w-4 flex-shrink-0 mt-0.5", config.text)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-maref-text">{operation}</span>
            <span className={cn("text-[10px] font-medium", config.text)}>
              {config.label}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-maref-text-muted leading-relaxed">
            {description}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onAllow}
          className={cn(
            "rounded-md px-3 py-1 text-[11px] font-medium transition-colors",
            risk === "critical"
              ? "bg-maref-danger/20 text-maref-danger hover:bg-maref-danger/30"
              : "bg-maref-success/20 text-maref-success hover:bg-maref-success/30"
          )}
        >
          允许
        </button>
        <button
          onClick={onBlock}
          className="rounded-md px-3 py-1 text-[11px] font-medium bg-maref-surface-alt text-maref-text-muted hover:bg-maref-surface-alt/80 transition-colors"
        >
          阻止
        </button>
        {onAsk && (
          <button
            onClick={onAsk}
            className="rounded-md px-3 py-1 text-[11px] font-medium text-maref-accent hover:bg-maref-surface-alt transition-colors"
          >
            询问详情
          </button>
        )}
      </div>
    </div>
  );
}
