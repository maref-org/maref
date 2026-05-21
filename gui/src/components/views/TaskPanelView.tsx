import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ListTodo, XCircle, Eye, Search, Filter } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/api/client";
import type { Task } from "@/types";

const STATUS_CONFIG: Record<Task["status"], { label: string; color: string }> = {
  pending: { label: "待处理", color: "bg-gray-400/10 text-gray-400 border-gray-400/20" },
  queued: { label: "已排队", color: "bg-blue-400/10 text-blue-400 border-blue-400/20" },
  running: { label: "运行中", color: "bg-green-400/10 text-green-400 border-green-400/20" },
  completed: { label: "已完成", color: "bg-gray-500/10 text-gray-500 border-gray-500/20" },
  failed: { label: "失败", color: "bg-red-400/10 text-red-400 border-red-400/20" },
  cancelled: { label: "已取消", color: "bg-orange-400/10 text-orange-400 border-orange-400/20" },
  timeout: { label: "超时", color: "bg-yellow-400/10 text-yellow-400 border-yellow-400/20" },
};

const PRIORITY_LABELS: Record<number, string> = {
  0: "LOW",
  1: "MEDIUM",
  2: "HIGH",
  3: "CRITICAL",
};

const PRIORITY_COLORS: Record<number, string> = {
  0: "text-maref-text-muted",
  1: "text-maref-info",
  2: "text-maref-warning",
  3: "text-maref-danger",
};

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "pending", label: "待处理" },
  { value: "queued", label: "已排队" },
  { value: "running", label: "运行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
  { value: "timeout", label: "超时" },
];

function truncateId(id: string, len = 8): string {
  if (id.length <= len) return id;
  return `${id.slice(0, len)}…`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function TaskDetailModal({
  task,
  onClose,
}: {
  task: Task;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-maref-border bg-maref-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-maref-text">任务详情</h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          >
            <XCircle className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">ID</span>
            <span className="col-span-2 text-maref-text font-mono text-xs break-all">{task.id}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">名称</span>
            <span className="col-span-2 text-maref-text font-medium">{task.name}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">描述</span>
            <span className="col-span-2 text-maref-text">{task.description || "-"}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">状态</span>
            <span className="col-span-2">
              <span
                className={cn(
                  "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                  STATUS_CONFIG[task.status].color
                )}
              >
                {STATUS_CONFIG[task.status].label}
              </span>
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">优先级</span>
            <span className={cn("col-span-2 font-medium", PRIORITY_COLORS[task.priority])}>
              {PRIORITY_LABELS[task.priority]}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">创建时间</span>
            <span className="col-span-2 text-maref-text">{formatDateTime(task.created_at)}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">更新时间</span>
            <span className="col-span-2 text-maref-text">{formatDateTime(task.updated_at)}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">开始时间</span>
            <span className="col-span-2 text-maref-text">{formatDateTime(task.started_at)}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">完成时间</span>
            <span className="col-span-2 text-maref-text">{formatDateTime(task.completed_at)}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">超时(秒)</span>
            <span className="col-span-2 text-maref-text">{task.timeout_seconds ?? "-"}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">最大重试</span>
            <span className="col-span-2 text-maref-text">{task.max_retries}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">重试次数</span>
            <span className="col-span-2 text-maref-text">{task.retry_count}</span>
          </div>
          {task.error_message && (
            <div className="grid grid-cols-3 gap-2 text-sm">
              <span className="text-maref-text-muted">错误信息</span>
              <span className="col-span-2 text-maref-danger text-xs break-all">{task.error_message}</span>
            </div>
          )}
          <div className="grid grid-cols-3 gap-2 text-sm">
            <span className="text-maref-text-muted">会话 ID</span>
            <span className="col-span-2 text-maref-text font-mono text-xs">{task.session_id || "-"}</span>
          </div>
          {task.tags.length > 0 && (
            <div className="grid grid-cols-3 gap-2 text-sm">
              <span className="text-maref-text-muted">标签</span>
              <span className="col-span-2 flex flex-wrap gap-1">
                {task.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded bg-maref-accent/10 px-1.5 py-0.5 text-[11px] text-maref-accent"
                  >
                    {tag}
                  </span>
                ))}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TaskPanelView() {
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [detailTask, setDetailTask] = useState<Task | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", statusFilter, search],
    queryFn: async () => {
      try {
        const params: { status?: string; limit?: number } = { limit: 100 };
        if (statusFilter !== "all") params.status = statusFilter;
        return await api.listTasks(params);
      } catch {
        return { tasks: [], total: 0 };
      }
    },
    staleTime: 5_000,
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.cancelTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const tasks = data?.tasks ?? [];
  const filtered = search
    ? tasks.filter((t: Task) => t.name.toLowerCase().includes(search.toLowerCase()))
    : tasks;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <ListTodo className="h-4 w-4 text-maref-accent" />
          任务面板
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          管理和监控异步任务执行状态
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-3 py-2 flex-1">
            <Search className="h-3.5 w-3.5 text-maref-text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索任务名称…"
              className="flex-1 bg-transparent text-xs text-maref-text placeholder-maref-text-muted outline-none"
            />
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-3 py-2">
            <Filter className="h-3.5 w-3.5 text-maref-text-muted" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-xs text-maref-text outline-none"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <span className="text-[11px] text-maref-text-muted">
            {filtered.length} 条
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20 text-sm text-maref-text-muted">
            加载中…
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-maref-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-maref-border bg-maref-surface-alt">
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">ID</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">名称</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">状态</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">优先级</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">创建时间</th>
                  <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-16 text-center text-maref-text-muted">
                      <div className="flex flex-col items-center gap-2">
                        <ListTodo className="h-8 w-8 opacity-30" />
                        <span className="text-sm">暂无任务</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filtered.map((task: Task) => {
                    const isCancellable = task.status === "queued" || task.status === "pending";
                    return (
                      <tr
                        key={task.id}
                        className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30"
                      >
                        <td className="px-4 py-3 text-maref-text-muted font-mono">
                          {truncateId(task.id)}
                        </td>
                        <td className="px-4 py-3 text-maref-text font-medium max-w-[200px] truncate">
                          {task.name}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                              STATUS_CONFIG[task.status].color
                            )}
                          >
                            {STATUS_CONFIG[task.status].label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={cn("font-medium", PRIORITY_COLORS[task.priority])}>
                            {PRIORITY_LABELS[task.priority]}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-maref-text-muted whitespace-nowrap">
                          {formatDateTime(task.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => setDetailTask(task)}
                              className="inline-flex items-center gap-1 rounded-md border border-maref-border px-2 py-1 text-[11px] text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt transition-colors"
                            >
                              <Eye className="h-3 w-3" />
                              详情
                            </button>
                            {isCancellable && (
                              <button
                                onClick={() => cancelMutation.mutate(task.id)}
                                disabled={cancelMutation.isPending}
                                className="inline-flex items-center gap-1 rounded-md border border-maref-danger/30 px-2 py-1 text-[11px] text-maref-danger hover:bg-maref-danger/10 transition-colors disabled:opacity-50"
                              >
                                <XCircle className="h-3 w-3" />
                                取消
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detailTask && (
        <TaskDetailModal
          task={detailTask}
          onClose={() => setDetailTask(null)}
        />
      )}
    </div>
  );
}