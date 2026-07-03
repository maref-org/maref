import { cn } from "@/lib/utils";

interface CrossImpactHeatmapProps {
  effects: Array<{
    source_dim: string;
    target_dim: string;
    effect_size: number;
    direction: string;
    confidence: number;
  }>;
  loading?: boolean;
  error?: string | null;
}

function getEffectColor(size: number): string {
  if (size > 0.3) return "bg-maref-success/60 text-maref-success";
  if (size > 0.1) return "bg-maref-success/30 text-maref-success";
  if (size < -0.3) return "bg-maref-danger/60 text-maref-danger";
  if (size < -0.1) return "bg-maref-danger/30 text-maref-danger";
  return "bg-maref-surface-alt text-maref-text-muted";
}

function getEffectTextColor(size: number): string {
  if (size > 0.3) return "text-white";
  if (size > 0.1) return "text-maref-success";
  if (size < -0.3) return "text-white";
  if (size < -0.1) return "text-maref-danger";
  return "text-maref-text-muted";
}

export default function CrossImpactHeatmap({ effects, loading, error }: CrossImpactHeatmapProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg border border-maref-border bg-maref-surface-alt/30">
        <div className="text-xs text-maref-text-muted">Loading cross-effect heatmap…</div>
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

  if (effects.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg border border-maref-border bg-maref-surface-alt/30">
        <div className="text-xs text-maref-text-muted">No cross-effect data available</div>
      </div>
    );
  }

  const dims = Array.from(new Set(effects.flatMap((e) => [e.source_dim, e.target_dim]))).sort();
  const lookup = new Map(effects.map((e) => [`${e.source_dim}→${e.target_dim}`, e]));

  return (
    <div className="overflow-x-auto">
      <div className="inline-block min-w-full">
        <div
          className="grid gap-px"
          style={{
            gridTemplateColumns: `120px repeat(${dims.length}, 64px)`,
            gridTemplateRows: `32px repeat(${dims.length}, 48px)`,
          }}
        >
          <div className="flex items-end pb-1 text-[10px] text-maref-text-muted" />

          {dims.map((dim) => (
            <div
              key={`header-${dim}`}
              className="flex items-end justify-center pb-1 text-[10px] font-medium text-maref-text-muted truncate px-1"
              title={dim}
            >
              {dim}
            </div>
          ))}

          {dims.map((rowDim, ri) => (
            <>
              <div
                key={`row-${rowDim}`}
                className="flex items-center pr-2 text-[10px] font-medium text-maref-text-muted truncate justify-end"
                title={rowDim}
              >
                {rowDim}
              </div>
              {dims.map((colDim) => {
                const effect = lookup.get(`${rowDim}→${colDim}`);
                const isDiagonal = rowDim === colDim;

                if (isDiagonal) {
                  return (
                    <div
                      key={`${rowDim}→${colDim}`}
                      className="flex items-center justify-center rounded bg-maref-surface-alt/50"
                    >
                      <span className="text-[10px] text-maref-text-muted">—</span>
                    </div>
                  );
                }

                if (!effect) {
                  return (
                    <div
                      key={`${rowDim}→${colDim}`}
                      className="flex items-center justify-center rounded bg-maref-surface-alt/20"
                    >
                      <span className="text-[10px] text-maref-text-muted">–</span>
                    </div>
                  );
                }

                return (
                  <div
                    key={`${rowDim}→${colDim}`}
                    className={cn(
                      "group relative flex items-center justify-center rounded cursor-default",
                      getEffectColor(effect.effect_size),
                    )}
                  >
                    <span className={cn("text-[11px] font-mono font-medium", getEffectTextColor(effect.effect_size))}>
                      {effect.effect_size.toFixed(2)}
                    </span>

                    <div className="absolute bottom-full left-1/2 mb-1 hidden -translate-x-1/2 group-hover:block z-10">
                      <div className="whitespace-nowrap rounded-md border border-maref-border bg-maref-surface px-2.5 py-1.5 text-[11px] shadow-lg">
                        <div className="font-medium text-maref-text">
                          {effect.source_dim} → {effect.target_dim}
                        </div>
                        <div className="text-maref-text-muted">
                          Effect: {effect.effect_size.toFixed(3)} ({effect.direction})
                        </div>
                        <div className="text-maref-text-muted">
                          Confidence: {(effect.confidence * 100).toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-4 text-[10px] text-maref-text-muted">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-maref-success/60" /> Strong positive
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-maref-success/30" /> Weak positive
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-maref-surface-alt" /> Neutral
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-maref-danger/30" /> Weak negative
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-maref-danger/60" /> Strong negative
        </span>
      </div>
    </div>
  );
}
