import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface HITLActionConfirmationProps {
  eventId: string;
  action: string;
  description: string;
  tier: string;
  onConfirm: (eventId: string) => void;
  onCancel: (eventId: string) => void;
  onPause: () => void;
}

const TIER_CONFIG: Record<string, { label: string; className: string }> = {
  p0_response: { label: "需确认", className: "bg-red-500 text-white" },
  p1_escalate: { label: "需注意", className: "bg-amber-500 text-white" },
  p2_log: { label: "仅记录", className: "bg-gray-500 text-white" },
  p3_observe: { label: "观察中", className: "bg-blue-500 text-white" },
};

export function HITLConfirmationDialog({
  eventId,
  action,
  description,
  tier,
  onConfirm,
  onCancel,
  onPause,
}: HITLActionConfirmationProps) {
  const [processing, setProcessing] = useState<string | null>(null);

  const handleConfirm = useCallback(async () => {
    setProcessing("confirm");
    try {
      await onConfirm(eventId);
    } finally {
      setProcessing(null);
    }
  }, [eventId, onConfirm]);

  const handleCancel = useCallback(async () => {
    setProcessing("cancel");
    try {
      await onCancel(eventId);
    } finally {
      setProcessing(null);
    }
  }, [eventId, onCancel]);

  const handlePause = useCallback(async () => {
    setProcessing("pause");
    try {
      await onPause();
    } finally {
      setProcessing(null);
    }
  }, [onPause]);

  const tierCfg = TIER_CONFIG[tier] ?? TIER_CONFIG.p2_log;

  return (
    <div
      className="rounded-lg border border-maref-border bg-maref-surface p-4 my-2"
      role="alertdialog"
      aria-label="Agent 操作确认"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold", tierCfg.className)}>
          {tierCfg.label}
        </span>
        <span className="text-sm font-semibold text-maref-text">{action}</span>
      </div>

      <p className="text-sm text-maref-text-muted mb-3 leading-relaxed">
        {description}
      </p>

      <div className="flex gap-2">
        <button
          onClick={handleConfirm}
          disabled={processing !== null}
          className={cn(
            "px-4 py-1.5 text-xs font-medium rounded-md transition-colors",
            "bg-emerald-600 text-white hover:bg-emerald-700",
            "disabled:opacity-50 disabled:cursor-wait",
          )}
        >
          {processing === "confirm" ? "确认中..." : "确认继续"}
        </button>

        <button
          onClick={handleCancel}
          disabled={processing !== null}
          className={cn(
            "px-4 py-1.5 text-xs font-medium rounded-md transition-colors",
            "border border-maref-border text-maref-text hover:bg-maref-surface-alt",
            "disabled:opacity-50 disabled:cursor-wait",
          )}
        >
          {processing === "cancel" ? "取消中..." : "取消执行"}
        </button>

        <button
          onClick={handlePause}
          disabled={processing !== null}
          className={cn(
            "px-4 py-1.5 text-xs font-medium rounded-md transition-colors",
            "border border-maref-border text-maref-text hover:bg-maref-surface-alt",
            "disabled:opacity-50 disabled:cursor-wait",
          )}
        >
          {processing === "pause" ? "暂停中..." : "暂停全部"}
        </button>
      </div>
    </div>
  );
}

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  pending: { label: "等待确认", className: "bg-amber-500 text-white" },
  approved: { label: "已确认", className: "bg-emerald-600 text-white" },
  rejected: { label: "已取消", className: "bg-red-500 text-white" },
  auto_approved: { label: "自动确认", className: "bg-blue-500 text-white" },
  expired: { label: "已过期", className: "bg-gray-500 text-white" },
};

export function HITLStatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.expired;
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium", cfg.className)}>
      {cfg.label}
    </span>
  );
}
