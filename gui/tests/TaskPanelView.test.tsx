import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TaskPanelView from "@/components/views/TaskPanelView";
import { api } from "@/api/client";
import type { Task } from "@/types";

vi.mock("@/api/client", () => ({
  api: {
    listTasks: vi.fn(),
    cancelTask: vi.fn(),
  },
}));

const mockTasks: Task[] = [
  {
    id: "task-1",
    name: "Fix lint errors",
    description: "",
    priority: 0,
    status: "running",
    payload: {},
    created_at: "2026-05-21T10:00:00Z",
    updated_at: "2026-05-21T10:00:00Z",
    started_at: "2026-05-21T10:00:00Z",
    completed_at: null,
    timeout_seconds: null,
    max_retries: 0,
    retry_count: 0,
    error_message: null,
    session_id: "sess-1",
    tags: [],
  },
  {
    id: "task-2",
    name: "Refactor auth module",
    description: "",
    priority: 2,
    status: "completed",
    payload: {},
    created_at: "2026-05-21T09:00:00Z",
    updated_at: "2026-05-21T09:00:00Z",
    started_at: null,
    completed_at: "2026-05-21T09:30:00Z",
    timeout_seconds: null,
    max_retries: 0,
    retry_count: 0,
    error_message: null,
    session_id: "sess-1",
    tags: [],
  },
];

function withProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("TaskPanelView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders title '任务面板'", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: [], total: 0 });
    withProviders(<TaskPanelView />);
    expect(screen.getByText("任务面板")).toBeInTheDocument();
  });

  it("shows empty state when no tasks", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: [], total: 0 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(screen.getByText("暂无任务")).toBeInTheDocument();
    });
  });

  it("renders task rows from API response", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: mockTasks, total: 2 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(screen.getByText("Fix lint errors")).toBeInTheDocument();
      expect(screen.getByText("Refactor auth module")).toBeInTheDocument();
    });
  });

  it("shows correct status badge text for running and completed", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: mockTasks, total: 2 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(screen.getByText("运行中")).toBeInTheDocument();
      expect(screen.getByText("已完成")).toBeInTheDocument();
    });
  });

  it("shows correct priority labels (0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL)", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: mockTasks, total: 2 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(screen.getByText("LOW")).toBeInTheDocument();
      expect(screen.getByText("HIGH")).toBeInTheDocument();
    });
  });

  it("filters tasks by search input", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: mockTasks, total: 2 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(screen.getByText("Fix lint errors")).toBeInTheDocument();
      expect(screen.getByText("Refactor auth module")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("搜索任务名称…");
    fireEvent.change(searchInput, { target: { value: "Refactor" } });

    await waitFor(() => {
      expect(screen.getByText("Refactor auth module")).toBeInTheDocument();
      expect(screen.queryByText("Fix lint errors")).not.toBeInTheDocument();
    });
  });

  it("triggers re-query on status filter change", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: mockTasks, total: 2 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledTimes(1);
    });

    vi.mocked(api.listTasks).mockClear();
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: [mockTasks[0]], total: 1 });

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "running" } });

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledWith(
        expect.objectContaining({ status: "running" })
      );
    });
  });

  it("opens detail modal when detail button clicked", async () => {
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: mockTasks, total: 2 });
    withProviders(<TaskPanelView />);
    await waitFor(() => {
      expect(screen.getByText("Fix lint errors")).toBeInTheDocument();
    });

    const detailButtons = screen.getAllByText("详情");
    fireEvent.click(detailButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("任务详情")).toBeInTheDocument();
    });
  });

  it("shows cancel button only for cancellable tasks (queued/pending)", async () => {
    const tasksWithPending: Task[] = [
      ...mockTasks,
      {
        id: "task-3",
        name: "Pending task",
        description: "",
        priority: 1,
        status: "pending",
        payload: {},
        created_at: "2026-05-21T11:00:00Z",
        updated_at: "2026-05-21T11:00:00Z",
        started_at: null,
        completed_at: null,
        timeout_seconds: null,
        max_retries: 0,
        retry_count: 0,
        error_message: null,
        session_id: "sess-1",
        tags: [],
      },
    ];
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: tasksWithPending, total: 3 });
    withProviders(<TaskPanelView />);

    await waitFor(() => {
      expect(screen.getByText("Pending task")).toBeInTheDocument();
    });

    const cancelButtons = screen.queryAllByText("取消");
    expect(cancelButtons).toHaveLength(1);
  });

  it("calls cancelTask API when cancel button clicked", async () => {
    vi.mocked(api.cancelTask).mockResolvedValue({
      id: "task-3",
      name: "Pending task",
      description: "",
      priority: 1,
      status: "cancelled",
      payload: {},
      created_at: "2026-05-21T11:00:00Z",
      updated_at: "2026-05-21T11:00:00Z",
      started_at: null,
      completed_at: null,
      timeout_seconds: null,
      max_retries: 0,
      retry_count: 0,
      error_message: null,
      session_id: "sess-1",
      tags: [],
    } as Task);

    const tasksWithPending: Task[] = [
      ...mockTasks,
      {
        id: "task-3",
        name: "Pending task",
        description: "",
        priority: 1,
        status: "pending",
        payload: {},
        created_at: "2026-05-21T11:00:00Z",
        updated_at: "2026-05-21T11:00:00Z",
        started_at: null,
        completed_at: null,
        timeout_seconds: null,
        max_retries: 0,
        retry_count: 0,
        error_message: null,
        session_id: "sess-1",
        tags: [],
      },
    ];
    vi.mocked(api.listTasks).mockResolvedValue({ tasks: tasksWithPending, total: 3 });
    withProviders(<TaskPanelView />);

    await waitFor(() => {
      expect(screen.getByText("Pending task")).toBeInTheDocument();
    });

    const cancelButton = screen.getByText("取消");
    fireEvent.click(cancelButton);

    await waitFor(() => {
      expect(api.cancelTask).toHaveBeenCalledWith("task-3");
    });
  });
});
