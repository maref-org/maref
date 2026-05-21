import { Coins } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  used: number;
  total: number;
  cost?: number;
  compact?: boolean;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function TokenUsage({ used, total, cost, compact = false }: Props) {
  const percent = Math.min(Math.round((used / total) * 100), 100);
  const barColor =
    percent > 80
      ? "bg-maref-danger"
      : percent > 50
        ? "bg-maref-warning"
        : "bg-maref-success";

  if (compact) {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-maref-text-muted">
        <Coins className="h-3 w-3 flex-shrink-0" />
        <div className="flex-1 h-1.5 rounded-full bg-maref-border overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-300", barColor)}
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="flex-shrink-0 font-mono">
          {formatTokens(used)}/{formatTokens(total)}
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] text-maref-text-muted">
          <Coins className="h-3 w-3" />
          <span>Token 用量</span>
        </div>
        <span className="text-[11px] text-maref-text font-mono">
          {formatTokens(used)} / {formatTokens(total)}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-maref-border overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-300", barColor)}
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className={cn("text-xs font-mono min-w-[3ch] text-right", barColor.replace("bg", "text"))}>
          {percent}%
        </span>
      </div>

      {cost !== undefined && (
        <div className="text-right text-[10px] text-maref-text-muted">
          预估成本: ${cost.toFixed(4)}
        </div>
      )}
    </div>
  );
}
