import { cn } from "@/lib/utils";
import { Shield, AlertTriangle } from "lucide-react";

type CircuitBreakerState = "CLOSED" | "OPEN" | "HALF_OPEN";

interface GovernanceStatusProps {
  state: string;
  entropy: number;
  cbState: CircuitBreakerState;
  anomalyCount: number;
}

function CircuitBreakerBadge({ state }: { state: CircuitBreakerState }) {
  const config = {
    CLOSED: { color: "bg-maref-success/20 text-maref-success", label: "CB: 闭合" },
    OPEN: { color: "bg-maref-danger/20 text-maref-danger", label: "CB: 断开" },
    HALF_OPEN: { color: "bg-maref-warning/20 text-maref-warning", label: "CB: 半开" },
  };
  const c = config[state];
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", c.color)}>
      {c.label}
    </span>
  );
}

export function GovernanceStatus({
  state,
  entropy,
  cbState,
  anomalyCount,
}: GovernanceStatusProps) {
  const anomalyColor =
    anomalyCount > 5 ? "text-maref-danger" : anomalyCount > 0 ? "text-maref-warning" : "text-maref-success";

  return (
    <span className="flex items-center gap-2 text-[11px]">
      <span className="flex items-center gap-1">
        <Shield className="h-3 w-3 text-maref-info" />
        <span className="text-maref-text-muted">状态:</span>
        <span
          className={cn(
            "font-medium",
            state === "HALT" ? "text-maref-danger" : "text-maref-text"
          )}
        >
          {state}
        </span>
      </span>
      <span className="text-maref-border">|</span>
      <span className="flex items-center gap-1">
        <span className="text-maref-text-muted">熵:</span>
        <span className="font-medium text-maref-text">{entropy}/4</span>
      </span>
      <span className="text-maref-border">|</span>
      <span className="flex items-center gap-1">
        <AlertTriangle className={cn("h-3 w-3", anomalyColor)} />
        <span className={cn("font-medium", anomalyColor)}>{anomalyCount}</span>
      </span>
      <span className="text-maref-border">|</span>
      <CircuitBreakerBadge state={cbState} />
    </span>
  );
}