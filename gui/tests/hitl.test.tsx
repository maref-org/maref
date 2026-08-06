import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { HITLConfirmationDialog, HITLStatusBadge } from "@/components/common/HITLConfirmationDialog";
import { HITLView } from "@/components/views/HITLView";
import { useHITLStore } from "@/stores/hitlStore";
import { api } from "@/api/client";

function withProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("HITLStatusBadge", () => {
  it("renders pending status", () => {
    render(<HITLStatusBadge status="pending" />);
    expect(screen.getByText("等待确认")).toBeInTheDocument();
  });

  it("renders approved status", () => {
    render(<HITLStatusBadge status="approved" />);
    expect(screen.getByText("已确认")).toBeInTheDocument();
  });

  it("renders rejected status", () => {
    render(<HITLStatusBadge status="rejected" />);
    expect(screen.getByText("已取消")).toBeInTheDocument();
  });

  it("renders auto_approved status", () => {
    render(<HITLStatusBadge status="auto_approved" />);
    expect(screen.getByText("自动确认")).toBeInTheDocument();
  });

  it("renders expired status", () => {
    render(<HITLStatusBadge status="expired" />);
    expect(screen.getByText("已过期")).toBeInTheDocument();
  });
});

describe("HITLConfirmationDialog", () => {
  it("renders with critical tier styling for p0", () => {
    render(
      <HITLConfirmationDialog
        eventId="hitl-000001"
        action="delete_file"
        description="Delete /etc/config.json"
        tier="p0_response"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        onPause={vi.fn()}
      />
    );
    expect(screen.getByText("需确认")).toBeInTheDocument();
    expect(screen.getByText("delete_file")).toBeInTheDocument();
    expect(screen.getByText("Delete /etc/config.json")).toBeInTheDocument();
    expect(screen.getByText("确认继续")).toBeInTheDocument();
    expect(screen.getByText("取消执行")).toBeInTheDocument();
    expect(screen.getByText("暂停全部")).toBeInTheDocument();
  });

  it("calls onConfirm when confirm button clicked", () => {
    const onConfirm = vi.fn();
    render(
      <HITLConfirmationDialog
        eventId="hitl-000001"
        action="test"
        description="test action"
        tier="p0_response"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        onPause={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("确认继续"));
    expect(onConfirm).toHaveBeenCalledWith("hitl-000001");
  });

  it("calls onCancel when cancel button clicked", () => {
    const onCancel = vi.fn();
    render(
      <HITLConfirmationDialog
        eventId="hitl-000001"
        action="test"
        description="test action"
        tier="p0_response"
        onConfirm={vi.fn()}
        onCancel={onCancel}
        onPause={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("取消执行"));
    expect(onCancel).toHaveBeenCalledWith("hitl-000001");
  });

  it("calls onPause when pause button clicked", () => {
    const onPause = vi.fn();
    render(
      <HITLConfirmationDialog
        eventId="hitl-000001"
        action="test"
        description="test action"
        tier="p0_response"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        onPause={onPause}
      />
    );
    fireEvent.click(screen.getByText("暂停全部"));
    expect(onPause).toHaveBeenCalled();
  });

  it("disables buttons while processing", () => {
    const slowConfirm = vi.fn(() => new Promise<void>(() => {}));
    render(
      <HITLConfirmationDialog
        eventId="hitl-000001"
        action="test"
        description="test"
        tier="p0_response"
        onConfirm={slowConfirm}
        onCancel={vi.fn()}
        onPause={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("确认继续"));
    const buttons = screen.getAllByRole("button");
    buttons.forEach((btn) => {
      expect(btn).toBeDisabled();
    });
  });
});

describe("HITLView", () => {
  beforeEach(() => {
    useHITLStore.setState({
      pendingEvents: [],
      historyEvents: [],
      stats: null,
      loading: false,
      error: null,
    });
  });

  it("renders without crashing", () => {
    withProviders(<HITLView />);
    expect(screen.getByText("HITL 审核")).toBeInTheDocument();
    expect(screen.getByText("待确认")).toBeInTheDocument();
    expect(screen.getByText("历史记录")).toBeInTheDocument();
  });

  it("shows empty state when no pending events", () => {
    withProviders(<HITLView />);
    expect(screen.getByText("没有待确认的 HITL 事件")).toBeInTheDocument();
  });

  it("renders pending events", () => {
    useHITLStore.setState({
      pendingEvents: [
        {
          event_id: "hitl-000001",
          tier: "p0_response",
          severity: "warning",
          description: "Approve this action",
          action: "execute_command",
          timestamp: Date.now() / 1000,
          auto_approve_seconds: 0,
          status: "pending",
        },
      ],
      stats: { total_events: 1, pending_count: 1, by_tier: {}, by_status: {}, tier_map: {} },
    });
    withProviders(<HITLView />);
    expect(screen.getByText("execute_command")).toBeInTheDocument();
    expect(screen.getByText("Approve this action")).toBeInTheDocument();
    expect(screen.getByText("批准")).toBeInTheDocument();
    expect(screen.getByText("拒绝")).toBeInTheDocument();
  });

  it("switches to history tab", () => {
    useHITLStore.setState({
      historyEvents: [
        {
          event_id: "hitl-000002",
          tier: "p0_response",
          severity: "info",
          description: "Completed action",
          action: "read_file",
          timestamp: Date.now() / 1000,
          auto_approve_seconds: 0,
          status: "approved",
        },
      ],
    });
    withProviders(<HITLView />);
    fireEvent.click(screen.getByText("历史记录"));
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("已确认")).toBeInTheDocument();
  });
});

describe("hitlStore", () => {
  beforeEach(() => {
    useHITLStore.setState({
      pendingEvents: [],
      historyEvents: [],
      stats: null,
      loading: false,
      error: null,
    });
  });

  it("approves event and removes from pending", async () => {
    useHITLStore.setState({
      pendingEvents: [
        {
          event_id: "hitl-000001",
          tier: "p0_response",
          severity: "warning",
          description: "test",
          action: "test_action",
          timestamp: Date.now() / 1000,
          auto_approve_seconds: 0,
          status: "pending",
        },
      ],
    });
    const store = useHITLStore.getState();
    expect(store.pendingEvents).toHaveLength(1);

    const mockApi = vi.spyOn(api, "hitlApprove");
    mockApi.mockResolvedValue({ event_id: "hitl-000001", status: "approved", approved: true });

    const result = await store.approveEvent("hitl-000001");
    expect(result).toBe(true);
    expect(useHITLStore.getState().pendingEvents).toHaveLength(0);

    mockApi.mockRestore();
  });

  it("stores error on API failure", async () => {
    const store = useHITLStore.getState();
    const mockApi = vi.spyOn(api, "hitlApprove");
    mockApi.mockRejectedValue(new Error("Network error"));

    const result = await store.approveEvent("hitl-000001");
    expect(result).toBe(false);
    expect(useHITLStore.getState().error).toBe("Network error");

    mockApi.mockRestore();
  });
});
