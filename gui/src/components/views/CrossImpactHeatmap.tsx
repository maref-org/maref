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

          {dims.map((rowDim) => (
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
                      <span className="text-[10px] text-maref-text-muted">·</span>
                    </div>
                  );
                }

                return (
                  <div
                    key={`${rowDim}→${colDim}`}
                    className={cn(
                      "flex items-center justify-center rounded cursor-default",
                      getEffectColor(effect.effect_size)
                    )}
                    title={`${effect.source_dim} → ${effect.target_dim}: ${effect.effect_size.toFixed(3)} (${effect.direction}, conf: ${effect.confidence.toFixed(2)})`}
                  >
                    <span className={cn("text-[10px] font-medium", getEffectTextColor(effect.effect_size))}>
                      {effect.effect_size.toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </div>
    </div>
  );
}