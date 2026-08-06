import { useState, useEffect, useRef } from "react";
import {
  Play,
  Pause,
  Square,
  Monitor,
  MousePointer,
  Keyboard,
  Eye,
  Terminal,
  CheckCircle2,
  Clock,
  ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";

type PreviewState = "idle" | "running" | "paused" | "completed" | "error";

interface StepLog {
  id: number;
  action: string;
  description: string;
  status: "completed" | "in-progress" | "pending" | "failed";
  time: string;
}

interface ClickPosition {
  x: number;
  y: number;
  label: string;
}

const MOCK_TASK = "重构 Sidebar 组件 — 提取 AgentList 到独立组件";

const INITIAL_STEPS: StepLog[] = [
  { id: 1, action: "read", description: "读取 src/components/layout/Sidebar.tsx", status: "completed", time: "14:32:01" },
  { id: 2, action: "grep", description: "搜索 AgentList 相关的所有引用", status: "completed", time: "14:32:03" },
  { id: 3, action: "write", description: "创建 src/components/sidebar/AgentList.tsx", status: "completed", time: "14:32:08" },
  { id: 4, action: "edit", description: "更新 Sidebar.tsx 导入 AgentList 组件", status: "in-progress", time: "14:32:12" },
  { id: 5, action: "verify", description: "运行 npx tsc --noEmit 验证类型", status: "pending", time: "—" },
];

const INITIAL_CLICKS: ClickPosition[] = [
  { x: 48, y: 32, label: "点击 Sidebar 组件" },
  { x: 35, y: 45, label: "选中 AgentList 区域" },
  { x: 60, y: 60, label: "右键 → 提取组件" },
];

export function ExecutionPreview() {
  const [previewState, setPreviewState] = useState<PreviewState>("running");
  useState<StepLog[]>(INITIAL_STEPS);
  const [overlayClicks, setOverlayClicks] = useState<ClickPosition[]>(INITIAL_CLICKS);
  const [operationLog, setOperationLog] = useState<StepLog[]>(INITIAL_STEPS);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [operationLog]);

  const handlePause = () => {
    if (previewState === "running") {
      setPreviewState("paused");
    } else if (previewState === "paused") {
      setPreviewState("running");
    }
  };

  const handleStop = () => {
    setPreviewState("idle");
    setOperationLog([]);
    setOverlayClicks([]);
  };

  const completed = operationLog.filter((s) => s.status === "completed").length;
  const total = operationLog.length;

  if (previewState === "idle") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
        <Monitor className="h-10 w-10" />
        <p className="text-sm">Agent 等待任务</p>
        <p className="text-xs">从聊天面板发送任务以启动执行预览</p>
      </div>
    );
  }

  return (
    <div className="flex h-full bg-maref-bg">
      <div className="flex flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-maref-border bg-maref-surface px-4 py-2.5 flex-shrink-0">
          <div className={cn(
            "flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-medium",
            previewState === "running" ? "bg-maref-info/10 text-maref-info" :
            previewState === "paused" ? "bg-maref-warning/10 text-maref-warning" :
            previewState === "completed" ? "bg-maref-success/10 text-maref-success" :
            previewState === "error" ? "bg-maref-danger/10 text-maref-danger" :
            "bg-maref-surface-alt text-maref-text-muted"
          )}>
            <span className={cn(
              "h-1.5 w-1.5 rounded-full",
              previewState === "running" && "bg-maref-info animate-pulse",
              previewState === "completed" && "bg-maref-success",
              previewState === "error" && "bg-maref-danger",
              previewState === "paused" && "bg-maref-warning"
            )} />
            {previewState === "running" ? "运行中" :
             previewState === "paused" ? "已暂停" :
             previewState === "completed" ? "已完成" : "错误"}
          </div>
          <span className="text-xs text-maref-text truncate flex-1">{MOCK_TASK}</span>
          <span className="text-[10px] text-maref-text-muted">
            {total > 0 ? `${completed}/${total} 步骤` : "—"}
          </span>
          <div className="flex items-center gap-0.5">
            <button
              onClick={handlePause}
              className={cn(
                "rounded p-1 transition-colors",
                previewState === "paused"
                  ? "text-maref-warning bg-maref-warning/10 hover:bg-maref-warning/20"
                  : "text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt"
              )}
              title={previewState === "paused" ? "继续" : "暂停"}
            >
              {previewState === "paused" ? (
                <Play className="h-3.5 w-3.5" />
              ) : (
                <Pause className="h-3.5 w-3.5" />
              )}
            </button>
            <button
              onClick={handleStop}
              className="rounded p-1 text-maref-text-muted hover:text-maref-danger hover:bg-maref-danger/10 transition-colors"
              title="停止"
            >
              <Square className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto bg-[#1a1a2e] p-4">
          <div className="relative mx-auto max-w-3xl rounded-lg border border-maref-border bg-maref-surface-alt overflow-hidden" style={{ aspectRatio: "16/10" }}>
            <div className="flex items-center gap-1.5 border-b border-maref-border bg-maref-surface px-3 py-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-maref-danger/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-maref-warning/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-maref-success/60" />
              <span className="ml-2 text-[10px] text-maref-text-muted font-mono">Sidebar.tsx — Visual Studio Code</span>
            </div>
            <div className="p-4 font-mono text-xs space-y-1">
              <Line num={1} content='import { Search, Store, Home, ChevronLeft } from "lucide-react";' />
              <Line num={2} content='import { cn } from "@/lib/utils";' highlight />
              <Line num={3} content='import { useUIStore } from "@/stores/uiStore";' />
              <Line num={4} content='import { useSessionStore } from "@/stores/sessionStore";' />
              <Line num={5} content='import { useTasks } from "@/hooks/useSession";' />
              <Line num={6} content='import { FileTree } from "@/components/sidebar/FileTree";' />
              <Line num={7} content='import { AgentList } from "@/components/sidebar/AgentList";' highlight />
              <Line num={8} content="" />
              <Line num={9} content='export type MarefSection =' />
              <Line num={10} content='  | "home" | "desktop" | "governance"' highlight />
            </div>

            {previewState !== "paused" && overlayClicks.map((click, i) => (
              <div
                key={i}
                className="absolute"
                style={{ left: `${click.x}%`, top: `${click.y}%` }}
              >
                <div className="relative">
                  <span className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-maref-danger/70 ring-2 ring-maref-danger/30 animate-pulse" />
                  <span className="absolute left-3 -translate-y-1/2 rounded bg-maref-surface px-2 py-0.5 text-[10px] text-maref-text shadow-lg whitespace-nowrap border border-maref-border">
                    {click.label}
                  </span>
                </div>
              </div>
            ))}

            {previewState === "paused" && (
              <div className="absolute inset-0 bg-maref-bg/60 flex items-center justify-center backdrop-blur-[2px]">
                <div className="flex flex-col items-center gap-2">
                  <Pause className="h-8 w-8 text-maref-warning" />
                  <span className="text-sm text-maref-text">执行已暂停</span>
                  <span className="text-[10px] text-maref-text-muted">点击 ▶ 继续执行</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="w-72 flex-shrink-0 border-l border-maref-border bg-maref-surface flex flex-col">
        <div className="flex items-center justify-between border-b border-maref-border px-3 py-2.5">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-maref-text">
            <Eye className="h-3.5 w-3.5 text-maref-accent" />
            操作日志
          </h3>
          <ChevronDown className="h-3.5 w-3.5 text-maref-text-muted" />
        </div>

        <div className="flex-1 overflow-y-auto">
          {operationLog.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-maref-text-muted">
              <Clock className="h-5 w-5" />
              <p className="text-xs">无操作记录</p>
            </div>
          ) : (
            operationLog.map((step) => {
              const StepIcon = {
                read: Eye,
                grep: Terminal,
                write: Keyboard,
                edit: MousePointer,
                verify: CheckCircle2,
              }[step.action] ?? Monitor;

              return (
                <div
                  key={step.id}
                  className={cn(
                    "flex items-start gap-2.5 border-b border-maref-border px-3 py-2.5",
                    step.status === "in-progress" && "bg-maref-accent/5"
                  )}
                >
                  <div className={cn(
                    "mt-0.5 rounded p-1 flex-shrink-0",
                    step.status === "completed" ? "bg-maref-success/10 text-maref-success" :
                    step.status === "in-progress" ? "bg-maref-accent/10 text-maref-accent" :
                    step.status === "failed" ? "bg-maref-danger/10 text-maref-danger" :
                    "bg-maref-surface-alt text-maref-text-muted"
                  )}>
                    <StepIcon className="h-3 w-3" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={cn(
                        "text-[10px] font-medium uppercase",
                        step.action === "grep" ? "text-maref-info" :
                        step.action === "write" ? "text-maref-success" :
                        step.action === "edit" ? "text-maref-warning" :
                        "text-maref-text-muted"
                      )}>
                        {step.action}
                      </span>
                      {step.status === "in-progress" && (
                        <span className="h-1.5 w-1.5 rounded-full bg-maref-accent animate-pulse" />
                      )}
                    </div>
                    <p className="mt-0.5 text-[11px] text-maref-text leading-snug">{step.description}</p>
                  </div>
                  <span className="text-[10px] text-maref-text-muted flex-shrink-0">{step.time}</span>
                </div>
              );
            })
          )}
          <div ref={logEndRef} />
        </div>

        {operationLog.length > 0 && (
          <div className="border-t border-maref-border px-3 py-2">
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-maref-text-muted">进度</span>
              <div className="flex-1 h-1 rounded-full bg-maref-surface-alt">
                <div
                  className="h-full rounded-full bg-maref-accent transition-all"
                  style={{ width: `${total > 0 ? (completed / total) * 100 : 0}%` }}
                />
              </div>
              <span className="text-maref-text font-mono">{completed}/{total}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Line({ num, content, highlight }: { num: number; content: string; highlight?: boolean }) {
  return (
    <div className={cn(
      "flex gap-4",
      highlight && "bg-maref-accent/10 -mx-4 px-4 rounded-sm"
    )}>
      <span className="w-6 text-right text-maref-text-muted select-none">{num}</span>
      <span className="text-maref-text">{content}</span>
    </div>
  );
}
