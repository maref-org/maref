import { useEffect } from "react";
import { RefreshCw, TrendingUp, BarChart3, Target } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRsiStore } from "@/stores/rsiStore";
import ParetoFrontChart from "./ParetoFrontChart";
import CrossImpactHeatmap from "./CrossImpactHeatmap";
import AdaptiveAllocationReport from "./AdaptiveAllocationReport";

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
  return (
    <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
      <Icon className="h-3.5 w-3.5" />
      {title}
    </h3>
  );
}

export default function RsiDashboard() {
  const {
    paretoFront,
    crossEffects,
    adaptiveAllocation,
    loading,
    error,
    refreshAll,
  } = useRsiStore();

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
              <TrendingUp className="h-4 w-4 text-maref-accent" />
              RSI Dashboard
            </h2>
            <p className="mt-0.5 text-xs text-maref-text-muted">
              Pareto front · Cross-effects · Adaptive allocation
            </p>
          </div>
          <button
            onClick={refreshAll}
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

        <section>
          <SectionHeader icon={BarChart3} title="Pareto Front" />
          <div className="mt-3">
            <ParetoFrontChart
              dimensions={paretoFront?.dimensions ?? []}
              currentScores={paretoFront?.current_scores ?? {}}
              recommendedWeights={paretoFront?.recommended_weights ?? {}}
              rationale={paretoFront?.rationale ?? ""}
              loading={loading && !paretoFront}
              error={null}
            />
          </div>
        </section>

        <section>
          <SectionHeader icon={Target} title="Cross-Impact Effects" />
          <div className="mt-3">
            <CrossImpactHeatmap
              effects={crossEffects ?? []}
              loading={loading && !crossEffects}
              error={null}
            />
          </div>
        </section>

        <section>
          <SectionHeader icon={TrendingUp} title="Adaptive Allocation" />
          <div className="mt-3">
            <AdaptiveAllocationReport
              allocations={adaptiveAllocation ?? []}
              loading={loading && !adaptiveAllocation}
              error={null}
            />
          </div>
        </section>
      </div>
    </div>
  );
}