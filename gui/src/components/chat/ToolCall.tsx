import { useState } from "react";
import {
  Wrench,
  ChevronRight,
  ChevronDown,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  toolName: string;
  input?: Record<string, unknown>;
  output?: string;
  status: "success" | "error" | "pending";
  duration?: number;
}

export function ToolCall({ toolName, input, output, status, duration }: Props) {
  const [expanded, setExpanded] = useState(false);

  const statusConfig: Record<string, { icon: React.ElementType; color: string; bg: string; label: string }> = {
    success: { icon: CheckCircle, color: "text-maref-success", bg: "bg-maref-success/10", label: "成功" },
    error: { icon: XCircle, color: "text-maref-danger", bg: "bg-maref-danger/10", label: "失败" },
    pending: { icon: Loader2, color: "text-maref-warning", bg: "bg-maref-warning/10", label: "执行中" },
  };

  const config = statusConfig[status] ?? statusConfig.pending;
  const StatusIcon = config.icon;

  return (
    <div className={cn("mt-1.5 rounded-lg border border-maref-border overflow-hidden", config.bg)}>
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs transition-colors hover:bg-maref-surface-alt/30"
      >
        <Wrench className="h-3 w-3 text-maref-text-muted flex-shrink-0" />
        <span className="font-mono text-[11px] text-maref-text">{toolName}</span>
        {status === "pending" ? (
          <Loader2 className="h-3 w-3 text-maref-warning animate-spin ml-auto flex-shrink-0" />
        ) : (
          <StatusIcon className={cn("h-3 w-3 ml-auto flex-shrink-0", config.color)} />
        )}
        <span className={cn("text-[10px] flex-shrink-0", config.color)}>{config.label}</span>
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-maref-text-muted flex-shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-maref-text-muted flex-shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-maref-border px-3 py-2 space-y-2">
          {input && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted mb-1">
                输入参数
              </div>
              <pre className="rounded bg-maref-bg/60 p-2 text-[11px] font-mono text-maref-text overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify(input, null, 2)}
              </pre>
            </div>
          )}

          {output && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted mb-1">
                输出结果
              </div>
              <pre className="rounded bg-maref-bg/60 p-2 text-[11px] font-mono text-maref-text max-h-40 overflow-y-auto whitespace-pre-wrap break-all">
                {output.length > 500 ? output.slice(0, 500) + "\n…(截断)" : output}
              </pre>
            </div>
          )}

          {duration !== undefined && (
            <div className="flex items-center gap-1.5 text-[10px] text-maref-text-muted">
              <Clock className="h-3 w-3" />
              <span>{duration}ms</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
