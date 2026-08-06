import { useEffect } from "react";
import {
  AlertTriangle,
  Activity,
  Gauge,
  RefreshCw,
  Clock,
  Shield,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useErrorBudgetStore } from "@/stores/errorBudgetStore";

function BudgetCard({
  sloTarget,
  budgetRemaining,
  burnRate,
}: {
  sloTarget: number;
  budgetRemaining: number;
  burnRate: number;
}) {
  const budgetColor =
    budgetRemaining < 10
      ? "text-maref-danger"
      : budgetRemaining < 50
        ? "text-maref-warning"
        : "text-maref-success";

  const burnColor =
    burnRate > 10
      ? "text-maref-danger"
      : burnRate > 3
        ? "text-maref-warning"
        : "text-maref-success";

  return (
    <div className="grid grid-cols-3 gap-3">
      <div className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
        <div className="rounded-lg bg-maref-info/20 p-2">
          <Shield className="h-4 w-4 text-maref-info" />
        </div>
        <div>
          <div className="text-[11px] text-maref-text-muted">SLO Target</div>
          <div className="text-sm font-semibold text-maref-text">
            {(sloTarget * 100).toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
        <div className={cn("rounded-lg p-2", budgetColor.replace("text-", "bg-").replace("danger", "danger/20").replace("warning", "warning/20").replace("success", "success/20"))}>
          <Gauge className={cn("h-4 w-4", budgetColor)} />
        </div>
        <div>
          <div className="text-[11px] text-maref-text-muted">Budget Remaining</div>
          <div className={cn("text-sm font-semibold", budgetColor)}>
            {budgetRemaining.toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
        <div className={cn("rounded-lg p-2", burnColor.replace("text-", "bg-").replace("danger", "danger/20").replace("warning", "warning/20").replace("success", "success/20"))}>
          <Activity className={cn("h-4 w-4", burnColor)} />
        </div>
        <div>
          <div className="text-[11px] text-maref-text-muted">Burn Rate</div>
          <div className={cn("text-sm font-semibold", burnColor)}>
            {burnRate.toFixed(2)}x
          </div>
        </div>
      </div>
    </div>
  );
}

function BurnRateAlerts({
  alerts,
}: {
  alerts: Array<{
    level: string;
    burn_rate: number;
    threshold: number;
    triggered: boolean;
  }>;
}) {
  const levelColors: Record<string, string> = {
    P0: "bg-maref-danger/20 text-maref-danger border-maref-danger/30",
    P1: "bg-maref-warning/20 text-maref-warning border-maref-warning/30",
    P2: "bg-maref-info/20 text-maref-info border-maref-info/30",
    OK: "bg-maref-success/20 text-maref-success border-maref-success/30",
  };

  return (
    <section>
      <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
        <AlertTriangle className="h-3.5 w-3.5" />
        Burn Rate Alerts
      </h3>
      <div className="space-y-2">
        {alerts.map((alert, i) => {
          const colorClass = levelColors[alert.level] ?? levelColors.OK;
          return (
            <div
              key={i}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-4 py-2.5",
                alert.triggered ? colorClass : "border-maref-border bg-maref-surface-alt/30",
              )}
            >
              <div className={cn(
                "rounded px-2 py-0.5 text-[10px] font-bold",
                alert.triggered ? "bg-current/20" : "bg-maref-surface-alt text-maref-text-muted",
              )}>
                {alert.level}
              </div>
              <span className="flex-1 text-xs text-maref-text">
                {alert.triggered
                  ? `Burn rate ${alert.burn_rate.toFixed(2)}x exceeds threshold ${alert.threshold}x`
                  : `Burn rate ${alert.burn_rate.toFixed(2)}x (threshold ${alert.threshold}x)`}
              </span>
              {alert.triggered && <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
            </div>
          );
        })}
        {alerts.length === 0 && (
          <div className="text-xs text-maref-text-muted py-2 text-center">
            No alerts configured
          </div>
        )}
      </div>
    </section>
  );
}

function RecentErrors({
  errors,
}: {
  errors: Array<{ id: string; severity: string; source: string; message: string; timestamp: string }>;
}) {
  const severityColor = (s: string) => {
    switch (s) {
      case "ERROR": return "text-maref-danger";
      case "WARN": return "text-maref-warning";
      default: return "text-maref-text-muted";
    }
  };

  return (
    <section>
      <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
        <Clock className="h-3.5 w-3.5" />
        Recent Errors
      </h3>
      <div className="max-h-64 overflow-y-auto rounded-lg border border-maref-border">
        {errors.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-maref-text-muted">
            No errors recorded
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-maref-border bg-maref-surface-alt">
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">Severity</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">Source</th>
                <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">Message</th>
                <th className="px-4 py-2.5 text-right font-medium text-maref-text-muted">Time</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((err) => (
                <tr key={err.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                  <td className="px-4 py-2">
                    <span className={cn("font-medium", severityColor(err.severity))}>
                      {err.severity}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-maref-text-muted">{err.source}</td>
                  <td className="px-4 py-2 text-maref-text">{err.message}</td>
                  <td className="px-4 py-2 text-right text-maref-text-muted">{err.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

export function ErrorBudgetView() {
  const {
    sloTarget, budgetRemaining, burnRate,
    recentErrors, alerts, loading, error,
    fetchData,
  } = useErrorBudgetStore();

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
              <Activity className="h-4 w-4 text-maref-accent" />
              Error Budget
            </h2>
            <p className="mt-0.5 text-xs text-maref-text-muted">
              SLO compliance · Burn rate monitoring · Error tracking
            </p>
          </div>
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-maref-border bg-maref-surface-alt px-3 py-1.5 text-xs text-maref-text-muted hover:text-maref-text disabled:opacity-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-6 p-6">
        {error && (
          <div className="rounded-lg border border-maref-danger/30 bg-maref-danger/10 px-4 py-2 text-xs text-maref-danger">
            {error}
          </div>
        )}

        <BudgetCard
          sloTarget={sloTarget}
          budgetRemaining={budgetRemaining}
          burnRate={burnRate}
        />

        <BurnRateAlerts alerts={alerts} />

        <RecentErrors errors={recentErrors} />
      </div>
    </div>
  );
}
