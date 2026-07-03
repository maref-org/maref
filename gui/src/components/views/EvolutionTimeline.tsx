import { useEffect, useState } from "react";
import {
  RefreshCw,
  Clock,
  GitTag,
  ShieldCheck,
  AlertTriangle,
  HeartPulse,
  Sparkles,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEvolutionStore } from "@/stores/evolutionStore";
import type { DaySnapshot, TimelineEvent } from "@/stores/evolutionStore";

function eventIcon(type: TimelineEvent["type"]) {
  switch (type) {
    case "version":
      return <GitTag className="h-3 w-3 text-maref-accent" />;
    case "gate":
      return <ShieldCheck className="h-3 w-3 text-maref-success" />;
    case "conflict":
      return <AlertTriangle className="h-3 w-3 text-maref-danger" />;
    case "heal":
      return <HeartPulse className="h-3 w-3 text-maref-success" />;
    case "alert":
      return <Activity className="h-3 w-3 text-maref-warning" />;
  }
}

function DayColumn({ snapshot }: { snapshot: DaySnapshot }) {
  const [expanded, setExpanded] = useState(false);
  const healRate =
    snapshot.selfHealCount > 0
      ? Math.round((snapshot.selfHealSuccesses / snapshot.selfHealCount) * 100)
      : 0;

  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border border-maref-border bg-maref-surface-alt/20 p-3 transition-colors hover:border-maref-border/80",
        expanded && "row-span-2",
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-xs font-semibold text-maref-text">
          Day {snapshot.day}
        </span>
        <span className="text-[10px] text-maref-text-muted">
          {snapshot.date}
        </span>
      </button>

      {snapshot.version && (
        <div className="mt-1 flex items-center gap-1 text-[10px] text-maref-accent">
          <GitTag className="h-2.5 w-2.5" />
          {snapshot.version}
        </div>
      )}

      <div className="mt-3 space-y-2">
        <div>
          <div className="flex items-center justify-between text-[10px] text-maref-text-muted">
            <span>Score</span>
            <span>{snapshot.avgScore.toFixed(0)}</span>
          </div>
          <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-maref-surface-alt">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                snapshot.avgScore >= 70
                  ? "bg-maref-success"
                  : snapshot.avgScore >= 40
                    ? "bg-maref-warning"
                    : "bg-maref-danger",
              )}
              style={{ width: `${snapshot.avgScore}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between text-[10px] text-maref-text-muted">
            <span>Adoption</span>
            <span>{(snapshot.adoptionRate * 100).toFixed(0)}%</span>
          </div>
          <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-maref-surface-alt">
            <div
              className="h-full rounded-full bg-maref-accent"
              style={{ width: `${snapshot.adoptionRate * 100}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {snapshot.events.map((ev, i) => (
          <span key={i} title={`${ev.label}: ${ev.detail}`}>
            {eventIcon(ev.type)}
          </span>
        ))}
      </div>

      {snapshot.selfHealCount > 0 && (
        <div className="mt-2 flex items-center gap-2 text-[10px] text-maref-text-muted">
          <span className="flex items-center gap-1">
            <Sparkles className="h-2.5 w-2.5 text-maref-success" />
            {healRate}%
          </span>
          <span className="flex items-center gap-0.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-maref-success" />
            {snapshot.selfHealSuccesses}
          </span>
          <span className="flex items-center gap-0.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-maref-danger" />
            {snapshot.selfHealCount - snapshot.selfHealSuccesses}
          </span>
        </div>
      )}

      {expanded && snapshot.events.length > 0 && (
        <div className="mt-3 space-y-1.5 border-t border-maref-border pt-3">
          {snapshot.events.map((ev, i) => (
            <div key={i} className="flex items-start gap-2 text-[10px]">
              <span className="mt-0.5 flex-shrink-0">{eventIcon(ev.type)}</span>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-maref-text">{ev.label}</div>
                <div className="text-maref-text-muted">{ev.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function EvolutionTimeline() {
  const { daySnapshots, loading, error, fetchEvolution } = useEvolutionStore();

  useEffect(() => {
    fetchEvolution();
  }, [fetchEvolution]);

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
              <Activity className="h-4 w-4 text-maref-accent" />
              Evolution Timeline
            </h2>
            <p className="mt-0.5 text-xs text-maref-text-muted">
              7-day RSI evolution · Score · Adoption · Events
            </p>
          </div>
          <button
            onClick={fetchEvolution}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-maref-border bg-maref-surface-alt px-3 py-1.5 text-xs text-maref-text-muted hover:text-maref-text disabled:opacity-50"
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", loading && "animate-spin")}
            />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-4 p-6">
        {error && (
          <div className="rounded-lg border border-maref-danger/30 bg-maref-danger/10 px-4 py-2 text-xs text-maref-danger">
            {error}
          </div>
        )}

        {loading && daySnapshots.length === 0 && (
          <div className="flex items-center justify-center py-16">
            <div className="flex items-center gap-2 text-xs text-maref-text-muted">
              <Clock className="h-4 w-4 animate-pulse" />
              Loading evolution timeline…
            </div>
          </div>
        )}

        {!loading && daySnapshots.length === 0 && !error && (
          <div className="flex items-center justify-center py-16">
            <div className="flex items-center gap-2 text-xs text-maref-text-muted">
              <Activity className="h-4 w-4" />
              No evolution data available
            </div>
          </div>
        )}

        {daySnapshots.length > 0 && (
          <div className="flex flex-wrap gap-3" style={{ "--day-count": daySnapshots.length } as React.CSSProperties}>
            {daySnapshots.map((snapshot) => (
              <div key={snapshot.day} className="min-w-[120px] flex-1">
                <DayColumn snapshot={snapshot} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
