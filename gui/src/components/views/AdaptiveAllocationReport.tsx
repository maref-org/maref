import { cn } from "@/lib/utils";

interface AdaptiveAllocationReportProps {
  allocations: Array<{
    target: string;
    rounds_allocated: number;
    success_rate: number;
    current_weight: number;
  }>;
  loading?: boolean;
  error?: string | null;
}

function successRateColor(rate: number): string {
  if (rate > 0.7) return "text-maref-success";
  if (rate > 0.4) return "text-maref-warning";
  return "text-maref-danger";
}

function successRateBg(rate: number): string {
  if (rate > 0.7) return "bg-maref-success/20";
  if (rate > 0.4) return "bg-maref-warning/20";
  return "bg-maref-danger/20";
}

export default function AdaptiveAllocationReport({ allocations, loading, error }: AdaptiveAllocationReportProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 rounded-lg border border-maref-border bg-maref-surface-alt/30">
        <div className="text-xs text-maref-text-muted">Loading allocation report…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-32 rounded-lg border border-maref-danger/30 bg-maref-danger/10">
        <div className="text-xs text-maref-danger">{error}</div>
      </div>
    );
  }

  if (allocations.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 rounded-lg border border-maref-border bg-maref-surface-alt/30">
        <div className="text-xs text-maref-text-muted">No allocation data available</div>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-maref-border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-maref-border bg-maref-surface-alt/50">
            <th className="px-4 py-2.5 text-left font-semibold text-maref-text-muted">Target</th>
            <th className="px-4 py-2.5 text-right font-semibold text-maref-text-muted">Rounds Allocated</th>
            <th className="px-4 py-2.5 text-right font-semibold text-maref-text-muted">Success Rate</th>
            <th className="px-4 py-2.5 text-right font-semibold text-maref-text-muted">Current Weight</th>
          </tr>
        </thead>
        <tbody>
          {allocations.map((alloc, i) => (
            <tr
              key={alloc.target}
              className={cn(
                "border-b border-maref-border/50 last:border-b-0 hover:bg-maref-surface-alt/30",
              )}
            >
              <td className="px-4 py-2.5 font-mono text-maref-text">{alloc.target}</td>
              <td className="px-4 py-2.5 text-right font-mono text-maref-text">
                {alloc.rounds_allocated}
              </td>
              <td className="px-4 py-2.5 text-right">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
                    successRateBg(alloc.success_rate),
                    successRateColor(alloc.success_rate),
                  )}
                >
                  <span
                    className={cn(
                      "inline-block h-1.5 w-1.5 rounded-full",
                      successRateColor(alloc.success_rate).replace("text-", "bg-"),
                    )}
                  />
                  {(alloc.success_rate * 100).toFixed(0)}%
                </span>
              </td>
              <td className="px-4 py-2.5 text-right">
                <div className="flex items-center justify-end gap-2">
                  <div className="h-1.5 w-16 rounded-full bg-maref-surface-alt">
                    <div
                      className="h-1.5 rounded-full bg-maref-accent"
                      style={{ width: `${Math.min(alloc.current_weight * 100, 100)}%` }}
                    />
                  </div>
                  <span className="w-10 text-right font-mono text-maref-text-muted">
                    {(alloc.current_weight * 100).toFixed(1)}%
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
