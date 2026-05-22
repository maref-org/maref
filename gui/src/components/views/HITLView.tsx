import { useEffect, useState } from "react";
import { useHITLStore } from "@/stores/hitlStore";
import { HITLStatusBadge } from "@/components/common/HITLConfirmationDialog";
import { cn } from "@/lib/utils";

type HITLTab = "pending" | "history";

const TIER_LABELS: Record<string, string> = {
  p0_response: "需确认",
  p1_escalate: "需注意",
  p2_log: "仅记录",
  p3_observe: "观察中",
};

const TIER_COLORS: Record<string, string> = {
  p0_response: "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950",
  p1_escalate: "text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950",
  p2_log: "text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-900",
  p3_observe: "text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950",
};

function formatTime(ts: number) {
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

function HITLRequestRow({
  event,
  onApprove,
  onDeny,
}: {
  event: { event_id: string; tier: string; severity: string; description: string; action: string; timestamp: number; auto_approve_seconds: number; status: string };
  onApprove: (id: string) => void;
  onDeny: (id: string) => void;
}) {
  const [processing, setProcessing] = useState<string | null>(null);

  const handleApprove = async () => {
    setProcessing("approve");
    await onApprove(event.event_id);
    setProcessing(null);
  };

  const handleDeny = async () => {
    setProcessing("deny");
    await onDeny(event.event_id);
    setProcessing(null);
  };

  const isAutoApprove = event.auto_approve_seconds > 0;
  const isPending = event.status === "pending";

  return (
    <div className="rounded-lg border border-maref-border bg-maref-surface p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium", TIER_COLORS[event.tier] ?? TIER_COLORS.p2_log)}>
              {TIER_LABELS[event.tier] ?? event.tier}
            </span>
            <span className="text-sm font-semibold text-maref-text truncate">{event.action}</span>
          </div>
          <p className="text-sm text-maref-text-muted mt-1 line-clamp-2">{event.description}</p>
          <div className="flex items-center gap-3 mt-2 text-xs text-maref-text-muted">
            <span>{formatTime(event.timestamp)}</span>
            {isAutoApprove && (
              <span className="text-amber-600 dark:text-amber-400">
                自动确认: {event.auto_approve_seconds}s
              </span>
            )}
          </div>
        </div>

        {isPending && (
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleApprove}
              disabled={processing !== null}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                "bg-emerald-600 text-white hover:bg-emerald-700",
                "disabled:opacity-50 disabled:cursor-wait",
              )}
            >
              {processing === "approve" ? "确认中..." : "批准"}
            </button>
            <button
              onClick={handleDeny}
              disabled={processing !== null}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                "bg-red-600 text-white hover:bg-red-700",
                "disabled:opacity-50 disabled:cursor-wait",
              )}
            >
              {processing === "deny" ? "拒绝中..." : "拒绝"}
            </button>
          </div>
        )}

        {!isPending && (
          <div className="flex-shrink-0">
            <HITLStatusBadge status={event.status} />
          </div>
        )}
      </div>
    </div>
  );
}

function PendingTab() {
  const { pendingEvents, approveEvent, denyEvent, fetchPending } = useHITLStore();

  const handleApprove = async (id: string) => {
    await approveEvent(id);
  };

  const handleDeny = async (id: string) => {
    await denyEvent(id);
  };

  if (pendingEvents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-maref-text-muted">
        <div className="text-4xl mb-3 opacity-30">✓</div>
        <p className="text-sm">没有待确认的 HITL 事件</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {pendingEvents.map((event) => (
        <HITLRequestRow
          key={event.event_id}
          event={event}
          onApprove={handleApprove}
          onDeny={handleDeny}
        />
      ))}
    </div>
  );
}

function HistoryTab() {
  const { historyEvents, fetchHistory } = useHITLStore();

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  if (historyEvents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-maref-text-muted">
        <p className="text-sm">没有 HITL 历史记录</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {historyEvents.map((event) => (
        <div key={event.event_id} className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface px-4 py-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-maref-text truncate">{event.action}</span>
              <HITLStatusBadge status={event.status} />
            </div>
            <p className="text-xs text-maref-text-muted mt-0.5 truncate">{event.description}</p>
            <span className="text-[11px] text-maref-text-muted/60">{formatTime(event.timestamp)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function HITLView() {
  const [tab, setTab] = useState<HITLTab>("pending");
  const { stats, fetchPending, fetchStats, startPolling, stopPolling } = useHITLStore();

  useEffect(() => {
    fetchPending();
    fetchStats();
    startPolling();
    return () => stopPolling();
  }, [fetchPending, fetchStats, startPolling, stopPolling]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-maref-border px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-maref-text">HITL 审核</h1>
          <p className="text-sm text-maref-text-muted mt-0.5">
            人在回路审批 · {stats ? `${stats.pending_count} 个待确认` : "加载中..."}
          </p>
        </div>
        {stats && (
          <div className="flex items-center gap-4 text-xs text-maref-text-muted">
            <span>总计: {stats.total_events}</span>
            <span>待确认: {stats.pending_count}</span>
          </div>
        )}
      </div>

      <div className="flex gap-1 border-b border-maref-border px-6 pt-3">
        <button
          onClick={() => setTab("pending")}
          className={cn(
            "px-4 py-2 text-sm font-medium rounded-t-lg transition-colors",
            tab === "pending"
              ? "bg-maref-surface text-maref-accent border border-maref-border border-b-transparent"
              : "text-maref-text-muted hover:text-maref-text",
          )}
        >
          待确认
          {stats && stats.pending_count > 0 && (
            <span className="ml-2 inline-flex items-center justify-center h-5 min-w-5 rounded-full bg-maref-danger px-1.5 text-[11px] font-medium text-white">
              {stats.pending_count}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab("history")}
          className={cn(
            "px-4 py-2 text-sm font-medium rounded-t-lg transition-colors",
            tab === "history"
              ? "bg-maref-surface text-maref-accent border border-maref-border border-b-transparent"
              : "text-maref-text-muted hover:text-maref-text",
          )}
        >
          历史记录
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {tab === "pending" ? <PendingTab /> : <HistoryTab />}
      </div>
    </div>
  );
}
