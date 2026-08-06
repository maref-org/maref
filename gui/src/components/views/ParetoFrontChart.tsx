import { cn } from "@/lib/utils";

interface ParetoFrontChartProps {
  dimensions: string[];
  currentScores: Record<string, number>;
  recommendedWeights: Record<string, number>;
  rationale: string;
  loading?: boolean;
  error?: string | null;
}

const DIM_COLORS = [
  "bg-maref-accent text-maref-accent",
  "bg-maref-info text-maref-info",
  "bg-maref-success text-maref-success",
  "bg-maref-warning text-maref-warning",
  "bg-maref-danger text-maref-danger",
  "bg-purple-500 text-purple-400",
  "bg-pink-500 text-pink-400",
  "bg-cyan-500 text-cyan-400",
  "bg-orange-500 text-orange-400",
  "bg-teal-500 text-teal-400",
];

export default function ParetoFrontChart({
  dimensions,
  currentScores,
  recommendedWeights,
  rationale,
  loading,
  error,
}: ParetoFrontChartProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg border border-maref-border bg-maref-surface-alt/30">
        <div className="text-xs text-maref-text-muted">Loading Pareto front…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg border border-maref-danger/30 bg-maref-danger/10">
        <div className="text-xs text-maref-danger">{error}</div>
      </div>
    );
  }

  if (dimensions.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg border border-maref-border bg-maref-surface-alt/30">
        <div className="text-xs text-maref-text-muted">No Pareto data available</div>
      </div>
    );
  }

  const maxScore = Math.max(...Object.values(currentScores), 100);
  const maxWeight = Math.max(...Object.values(recommendedWeights), 1);

  return (
    <div className="space-y-3">
      <div className="relative h-64 rounded-lg border border-maref-border bg-maref-surface-alt/20 p-4">
        <div className="absolute bottom-4 left-16 right-4 top-12">
          {dimensions.map((dim, i) => {
            const score = currentScores[dim] ?? 0;
            const weight = recommendedWeights[dim] ?? 0;
            const colorIdx = i % DIM_COLORS.length;
            const x = (score / maxScore) * 100;
            const y = ((maxWeight - weight) / maxWeight) * 100;
            const color = DIM_COLORS[colorIdx];

            return (
              <div
                key={dim}
                className="group absolute"
                style={{ left: `${x}%`, top: `${y}%`, transform: "translate(-50%, -50%)" }}
              >
                <div className={cn("h-3.5 w-3.5 rounded-full ring-2 ring-maref-bg cursor-pointer", color.split(" ")[0])} />
                <div className="absolute bottom-full left-1/2 mb-1.5 hidden -translate-x-1/2 group-hover:block">
                  <div className="whitespace-nowrap rounded-md border border-maref-border bg-maref-surface px-2.5 py-1.5 text-[11px] shadow-lg">
                    <div className={cn("font-semibold", color.split(" ")[1])}>{dim}</div>
                    <div className="text-maref-text">Score: {score.toFixed(1)}</div>
                    <div className="text-maref-text-muted">Weight: {weight.toFixed(3)}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="absolute bottom-2 left-16 right-4 text-[10px] text-maref-text-muted text-center">
          Current Score →
        </div>
        <div className="absolute left-2 top-12 -translate-x-1/2 text-[10px] text-maref-text-muted" style={{ writingMode: "vertical-rl" }}>
          ← Recommended Weight
        </div>
      </div>

      {rationale && (
        <div className="rounded-lg border border-maref-border bg-maref-surface-alt/30 px-3 py-2 text-xs text-maref-text-muted leading-relaxed">
          {rationale}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {dimensions.map((dim, i) => {
          const colorIdx = i % DIM_COLORS.length;
          return (
            <div key={dim} className="flex items-center gap-1.5 text-[11px] text-maref-text-muted">
              <span className={cn("inline-block h-2 w-2 rounded-full", DIM_COLORS[colorIdx].split(" ")[0])} />
              {dim}
            </div>
          );
        })}
      </div>
    </div>
  );
}
