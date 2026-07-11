import { useState, useEffect, useCallback, useRef } from "react";
import { Clock, XCircle, GitMerge, Ban, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/api/client";
import type { CooldownEntry, CooldownSummary } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  cooling: "bg-maref-info/10 text-maref-info",
  blocked: "bg-maref-danger/10 text-maref-danger",
  merged: "bg-maref-success/10 text-maref-success",
  force_merged: "bg-maref-warning/10 text-maref-warning",
};

const STATUS_LABELS: Record<string, string> = {
  cooling: "冷却中",
  blocked: "已阻止",
  merged: "已合并",
  force_merged: "强制合并",
};

function SummaryCards({ summary }: { summary: CooldownSummary }) {
  const cards = [
    { icon: Clock, label: "冷却中", value: summary.cooling, color: "bg-maref-info/20 text-maref-info" },
    { icon: Ban, label: "已阻止", value: summary.blocked, color: "bg-maref-danger/20 text-maref-danger" },
    { icon: GitMerge, label: "已合并", value: summary.merged, color: "bg-maref-success/20 text-maref-success" },
    { icon: XCircle, label: "强制合并", value: summary.force_merged, color: "bg-maref-warning/20 text-maref-warning" },
  ];

  return (
    <div className="grid grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
          <div className={cn("rounded-lg p-2", card.color.split(" ")[0])}>
            <card.icon className={cn("h-4 w-4", card.color.split(" ")[1])} />
          </div>
          <div>
            <div className="text-[11px] text-maref-text-muted">{card.label}</div>
            <div className="text-sm font-semibold text-maref-text">{card.value}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CooldownTimeline({ entry }: { entry: CooldownEntry }) {
  const steps = [
    { label: "提交", time: entry.submitted_at, active: true },
    { label: "评估", time: entry.evaluated_at, active: !!entry.evaluated_at },
    { label: "合并", time: entry.merged_at, active: !!entry.merged_at },
  ];

  const activeCount = steps.filter((s) => s.active).length;

  return (
    <div className="flex items-center gap-1.5 min-w-[140px]">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center gap-1.5">
          <div
            className={cn(
              "h-2 w-2 rounded-full flex-shrink-0",
              step.active ? "bg-maref-accent" : "bg-maref-border"
            )}
          />
          {i < steps.length - 1 && (
            <div
              className={cn(
                "h-0.5 w-6",
                i < activeCount - 1 ? "bg-maref-accent" : "bg-maref-border"
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

export function CooldownDashboard() {
  const [entries, setEntries] = useState<CooldownEntry[]>([]);
  const [summary, setSummary] = useState<CooldownSummary>({ status: "checking", total_agents: 0, cooling: 0, blocked: 0, merged: 0, force_merged: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const loadingRef = useRef(false);
  const dataLoadedRef = useRef(false);

  const loadData = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      setLoading(true);
      setError(null);
      const [entriesRes, summaryRes] = await Promise.all([
        api.getImmunityCooldown(),
        api.getImmunityCooldownSummary(),
      ]);
      if (mountedRef.current) {
        setEntries((entriesRes.entries ?? []) as CooldownEntry[]);
        setSummary(summaryRes);
        dataLoadedRef.current = true;
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e instanceof Error ? e.message : "Failed to load cooldown data");
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (!dataLoadedRef.current) {
      loadData();
    }
    return () => {
      mountedRef.current = false;
    };
  }, [loadData]);

  if (summary.status === "no_manager") {
    return (
      <div className="flex h-full flex-col items-center justify-center py-16">
        <AlertCircle className="h-10 w-10 text-maref-text-muted mb-3" />
        <p className="text-sm text-maref-text-muted">Cooldown system not yet active</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SummaryCards summary={summary} />

      {error && (
        <div className="rounded-lg border border-maref-danger/30 bg-maref-danger/10 px-4 py-2 text-xs text-maref-danger">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-maref-accent border-t-transparent" />
        </div>
      )}

      {!loading && !error && entries.length === 0 && (
        <div className="flex flex-col items-center justify-center py-8 text-maref-text-muted">
          <Clock className="h-8 w-8 mb-2" />
          <p className="text-sm">No cooldown entries</p>
        </div>
      )}

      {!loading && entries.length > 0 && (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div key={entry.id} className="flex items-center gap-4 rounded-lg border border-maref-border bg-maref-surface-alt/30 px-4 py-3">
              <CooldownTimeline entry={entry} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-maref-text truncate">{entry.agent_name}</p>
                <p className="text-xs text-maref-text-muted">{entry.repo}</p>
              </div>
              <div className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-medium", STATUS_COLORS[entry.status] || "bg-maref-border/50 text-maref-text-muted")}>
                {STATUS_LABELS[entry.status] || entry.status}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}