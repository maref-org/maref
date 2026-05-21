import { useTasks } from "@/hooks/useSession";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, Loader2, Clock, Ban, Timer } from "lucide-react";

const STATUS_ICONS = {
  pending: Clock,
  queued: Timer,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
  cancelled: Ban,
  timeout: Timer,
} as const;

const STATUS_COLORS = {
  pending: "text-maref-text-muted",
  queued: "text-maref-info",
  running: "text-maref-info",
  completed: "text-maref-success",
  failed: "text-maref-danger",
  cancelled: "text-maref-warning",
  timeout: "text-maref-warning",
};

export function TaskList() {
  const { data } = useTasks();
  const tasks = data?.tasks ?? [];

  if (tasks.length === 0) {
    return (
      <div className="px-3 py-2 text-[11px] text-maref-text-muted">
        No recent tasks
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {tasks.map((task) => {
        const Icon = STATUS_ICONS[task.status];
        return (
          <div
            key={task.id}
            className="flex items-center gap-2 py-1 px-2 rounded-md text-xs text-maref-text-muted hover:bg-maref-surface-alt/50 transition-colors"
          >
            <Icon
              className={cn(
                "h-3 w-3 flex-shrink-0",
                STATUS_COLORS[task.status],
                task.status === "running" && "animate-spin"
              )}
            />
            <span className="truncate flex-1">{task.name}</span>
          </div>
        );
      })}
    </div>
  );
}