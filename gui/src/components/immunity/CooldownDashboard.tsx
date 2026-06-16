import { useState, useEffect, useCallback } from "react";
import { Clock, XCircle, GitMerge, Ban, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface CooldownEntry {
  id: string;
  agent_id: string;
  agent_name: string;
  status: "cooling" | "blocked" | "merged" | "force_merged";
  submitted_at: string;
  evaluated_at: string | null;
  merged_at: string | null;
  age_seconds: number;
  contamination_score: number;
  blocked_reason: string | null;
  merged_branch: string | null;
}

interface CooldownSummary {
  status: string;
  total_agents: number;
  cooling: number;
  blocked: number;
  merged: number;
  force_merged: number;
}

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

async function fetchCooldownData(): Promise<{ entries: CooldownEntry[]; summary: CooldownSummary }> {
  const [entriesRes, summaryRes] = await Promise.all([
    fetch("/api/immunity/cooldown"),
    fetch("/api/immunity/cooldown/summary"),
  ]);
  const entries = entriesRes.ok ? await entriesRes.json() : { entries: [] };
  const summary = summaryRes.ok ? await summaryRes.json() : { status: "no_manager" };
  return { entries: entries.entries ?? [], summary };
}

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

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchCooldownData();
      setEntries(data.entries);
      setSummary(data.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cooldown data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
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

      <div className="overflow-hidden rounded-lg border border-maref-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-maref-border bg-maref-surface-alt">
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">ID</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">Agent</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">状态</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">年龄</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">污染</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">已阻止</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">已合并</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">时间线</th>
              <th className="px-3 py-2.5 text-left font-medium text-maref-text-muted">操作</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && !loading && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-maref-text-muted text-xs">
                  暂无冷却记录
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-maref-text-muted text-xs">
                  加载中...
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                <td className="px-3 py-2 font-mono text-[11px] text-maref-text-muted">{entry.id}</td>
                <td className="px-3 py-2 text-maref-text font-medium">{entry.agent_name}</td>
                <td className="px-3 py-2">
                  <span className={cn("rounded px-1.5 py-0.5 text-[10px]", STATUS_COLORS[entry.status])}>
                    {STATUS_LABELS[entry.status]}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-maref-text">{entry.age_seconds}s</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-12 rounded-full bg-maref-border overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          entry.contamination_score > 0.7 ? "bg-maref-danger" :
                          entry.contamination_score > 0.4 ? "bg-maref-warning" :
                          "bg-maref-success"
                        )}
                        style={{ width: `${entry.contamination_score * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-maref-text-muted">{(entry.contamination_score * 100).toFixed(0)}%</span>
                  </div>
                </td>
                <td className="px-3 py-2">
                  {entry.blocked_reason ? (
                    <span className="flex items-center gap-1 text-maref-danger">
                      <Ban className="h-3 w-3" />
                      <span className="truncate max-w-[80px]">{entry.blocked_reason}</span>
                    </span>
                  ) : (
                    <span className="text-maref-text-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {entry.merged_branch ? (
                    <span className="text-maref-success">{entry.merged_branch}</span>
                  ) : (
                    <span className="text-maref-text-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <CooldownTimeline entry={entry} />
                </td>
                <td className="px-3 py-2">
                  <button className="rounded px-2 py-1 text-[10px] text-maref-accent hover:bg-maref-accent/10 transition-colors">
                    详情
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
