import { useState, useCallback } from "react";

interface HITLActionConfirmationProps {
  eventId: string;
  action: string;
  description: string;
  tier: string;
  onConfirm: (eventId: string) => void;
  onCancel: (eventId: string) => void;
  onPause: () => void;
}

const TIER_LABELS: Record<string, { label: string; color: string; severity: "low" | "medium" | "high" | "critical" }> = {
  "p0_response": { label: "需确认", color: "#ef4444", severity: "critical" },
  "p1_escalate": { label: "需注意", color: "#f59e0b", severity: "medium" },
  "p2_log": { label: "仅记录", color: "#6b7280", severity: "low" },
  "p3_observe": { label: "观察中", color: "#3b82f6", severity: "low" },
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

  const tierInfo = TIER_LABELS[tier] ?? TIER_LABELS["p2_log"];

  return (
    <div
      style={{
        border: `1px solid ${tierInfo.color}40`,
        borderRadius: 8,
        padding: "12px 16px",
        margin: "8px 0",
        backgroundColor: `${tierInfo.color}08`,
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
      role="alertdialog"
      aria-label="Agent 操作确认"
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "2px 8px",
            borderRadius: 4,
            fontSize: 12,
            fontWeight: 600,
            color: "#fff",
            backgroundColor: tierInfo.color,
          }}
        >
          {tierInfo.label}
        </span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "#1f2937" }}>
          {action}
        </span>
      </div>

      <p style={{ margin: "0 0 12px 0", fontSize: 13, color: "#6b7280", lineHeight: 1.5 }}>
        {description}
      </p>

      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={handleConfirm}
          disabled={processing !== null}
          style={{
            padding: "6px 16px",
            fontSize: 13,
            fontWeight: 500,
            border: "none",
            borderRadius: 6,
            cursor: processing === "confirm" ? "wait" : "pointer",
            backgroundColor: "#059669",
            color: "#fff",
            opacity: processing === "confirm" ? 0.7 : 1,
          }}
        >
          {processing === "confirm" ? "确认中..." : "确认继续"}
        </button>

        <button
          onClick={handleCancel}
          disabled={processing !== null}
          style={{
            padding: "6px 16px",
            fontSize: 13,
            fontWeight: 500,
            border: "1px solid #d1d5db",
            borderRadius: 6,
            cursor: processing === "cancel" ? "wait" : "pointer",
            backgroundColor: "#fff",
            color: "#374151",
            opacity: processing === "cancel" ? 0.7 : 1,
          }}
        >
          {processing === "cancel" ? "取消中..." : "取消执行"}
        </button>

        <button
          onClick={handlePause}
          disabled={processing !== null}
          style={{
            padding: "6px 16px",
            fontSize: 13,
            fontWeight: 500,
            border: "1px solid #d1d5db",
            borderRadius: 6,
            cursor: processing === "pause" ? "wait" : "pointer",
            backgroundColor: "#fff",
            color: "#374151",
            opacity: processing === "pause" ? 0.7 : 1,
          }}
        >
          {processing === "pause" ? "暂停中..." : "暂停全部"}
        </button>
      </div>
    </div>
  );
}

export function HITLStatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    pending: "#f59e0b",
    approved: "#059669",
    rejected: "#ef4444",
    auto_approved: "#3b82f6",
    expired: "#6b7280",
  };

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 500,
        color: "#fff",
        backgroundColor: colorMap[status] ?? "#6b7280",
      }}
    >
      {status === "pending" && "等待确认"}
      {status === "approved" && "已确认"}
      {status === "rejected" && "已取消"}
      {status === "auto_approved" && "自动确认"}
      {status === "expired" && "已过期"}
    </span>
  );
}