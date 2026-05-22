import {
  Search,
  Store,
  Home,
  ChevronLeft,
  ChevronRight,
  Plus,
  MessageSquare,
  Monitor,
  Shield,
  FileText,
  BarChart3,
  AlertTriangle,
  TrendingUp,
  GitBranch,
  FolderOpen,
  Settings,
  Zap,
  ListTodo,
  Wrench,
  UserCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useTasks } from "@/hooks/useSession";
import { FileTree } from "@/components/sidebar/FileTree";

export type MarefSection =
  | "home"
  | "desktop"
  | "governance"
  | "audit"
  | "drift"
  | "anomaly"
  | "trust"
  | "formal"
  | "skills"
  | "automation"
  | "hitl"
  | "tasks"
  | "tools"
  | "settings";

interface Props {
  activeSection: MarefSection;
  onSectionChange: (section: MarefSection) => void;
}

const TOP_NAV_ITEMS = [
  { id: "new-agent", icon: Search, label: "新建 Agent" },
  { id: "marketplace", icon: Store, label: "技能市场" },
  { id: "automation", icon: Zap, label: "自动化" },
] as const;

const MAREF_NAV_ITEMS: {
  id: MarefSection;
  icon: React.ElementType;
  label: string;
  shortcut: string;
}[] = [
  { id: "home", icon: Home, label: "首页仪表盘", shortcut: "⌃1" },
  { id: "desktop", icon: Monitor, label: "桌面 Agent", shortcut: "⌃2" },
  { id: "governance", icon: Shield, label: "治理看板", shortcut: "⌃3" },
  { id: "hitl", icon: UserCheck, label: "HITL 审核", shortcut: "⌃4" },
  { id: "audit", icon: FileText, label: "审计日志", shortcut: "⌃5" },
  { id: "drift", icon: BarChart3, label: "漂移检测", shortcut: "⌃6" },
  { id: "anomaly", icon: AlertTriangle, label: "异常监控", shortcut: "⌃7" },
  { id: "trust", icon: TrendingUp, label: "信任评分", shortcut: "⌃8" },
  { id: "formal", icon: GitBranch, label: "形式验证", shortcut: "⌃9" },
  { id: "tasks", icon: ListTodo, label: "任务面板", shortcut: "⌃0" },
  { id: "tools", icon: Wrench, label: "工具管理", shortcut: "⌃," },
  { id: "settings", icon: Settings, label: "设置", shortcut: "⌃." },
];

export function Sidebar({ activeSection, onSectionChange }: Props) {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();
  const { sessions, activeSessionId, setActiveSession, addSession } =
    useSessionStore();
  const { data: tasksData } = useTasks();

  const handleNewAgent = () => {
    addSession({
      id: `sess-${Date.now()}`,
      title: "新 Agent",
      mode: "agent",
      provider: "bailian",
      model: "deepseek-v4-pro",
      contextPercent: 0,
      status: "idle",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
  };

  const taskCount = tasksData?.tasks.filter((t) => t.status === "running").length ?? 0;

  return (
    <aside
      className="flex h-full flex-col border-r border-maref-border bg-maref-surface"
      style={{ width: "100%" }}
    >
      <div className="flex items-center justify-between px-3 py-3 border-b border-maref-border">
        {!sidebarCollapsed && (
          <span className="text-sm font-semibold tracking-wide text-maref-accent">
            MAREF
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="ml-auto rounded-md p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        {!sidebarCollapsed && (
          <>
            <div className="px-3 pt-1 pb-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
                Agent 会话
              </span>
            </div>
            {TOP_NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  if (item.id === "new-agent") handleNewAgent();
                  if (item.id === "marketplace") onSectionChange("skills");
                  if (item.id === "automation") onSectionChange("automation");
                }}
                className={cn(
                  "flex w-full items-center gap-3 px-3 py-2 text-sm transition-colors",
                  (item.id === "new-agent" && activeSessionId) || (activeSection === item.id)
                    ? "bg-maref-surface-alt text-maref-text"
                    : "text-maref-text-muted hover:bg-maref-surface-alt/50 hover:text-maref-text"
                )}
              >
                <item.icon className="h-4 w-4 flex-shrink-0" />
                <span className="flex-1 text-left">{item.label}</span>
                {item.id === "marketplace" && taskCount > 0 && (
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-maref-accent px-1.5 text-[11px] font-medium text-white">
                    {taskCount}
                  </span>
                )}
              </button>
            ))}

            <div className="flex items-center justify-between px-3 py-1.5 mt-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
                会话列表
              </span>
              <button
                onClick={handleNewAgent}
                className="rounded p-0.5 text-maref-text-muted hover:text-maref-accent transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => {
                  setActiveSession(session.id);
                  onSectionChange("home");
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-1.5 text-xs transition-colors",
                  activeSessionId === session.id
                    ? "bg-maref-surface-alt text-maref-text"
                    : "text-maref-text-muted hover:bg-maref-surface-alt/50"
                )}
              >
                <MessageSquare className="h-3.5 w-3.5 flex-shrink-0" />
                <span className="truncate">{session.title}</span>
                <span
                  className={cn(
                    "ml-auto h-1.5 w-1.5 rounded-full flex-shrink-0",
                    session.status === "active" || session.status === "thinking"
                      ? "bg-maref-success"
                      : session.status === "error"
                        ? "bg-maref-danger"
                        : "bg-maref-text-muted"
                  )}
                />
              </button>
            ))}
            {sessions.length === 0 && (
              <div className="px-3 py-1 text-[11px] text-maref-text-muted">
                无活跃会话
              </div>
            )}

            <div className="mt-3 border-t border-maref-border pt-2">
              <div className="flex items-center gap-1.5 px-3 py-1.5">
                <FolderOpen className="h-3 w-3 text-maref-text-muted" />
                <span className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
                  文件浏览器
                </span>
              </div>
              <div className="px-1">
                <FileTree />
              </div>
            </div>

            <div className="mt-3 border-t border-maref-border pt-2">
              <div className="px-3 py-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
                  MAREF 功能
                </span>
              </div>
              {MAREF_NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => onSectionChange(item.id)}
                  className={cn(
                    "flex w-full items-center gap-2.5 px-3 py-1.5 text-xs transition-colors",
                    activeSection === item.id
                      ? "bg-maref-surface-alt text-maref-accent"
                      : "text-maref-text-muted hover:bg-maref-surface-alt/50 hover:text-maref-text"
                  )}
                >
                  <item.icon className="h-3.5 w-3.5 flex-shrink-0" />
                  <span className="flex-1 text-left">{item.label}</span>
                  <kbd className="text-[10px] text-maref-text-muted/50 font-mono">
                    {item.shortcut}
                  </kbd>
                </button>
              ))}
            </div>
          </>
        )}

        {sidebarCollapsed && (
          <>
            <div className="flex flex-col items-center gap-1 pt-1">
              <button
                onClick={handleNewAgent}
                className="p-2 text-maref-text-muted hover:text-maref-text transition-colors"
                title="新建 Agent"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 border-t border-maref-border pt-2 flex flex-col items-center gap-1">
              {MAREF_NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => onSectionChange(item.id)}
                  className={cn(
                    "p-2 transition-colors",
                    activeSection === item.id
                      ? "text-maref-accent"
                      : "text-maref-text-muted hover:text-maref-text"
                  )}
                  title={item.label}
                >
                  <item.icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          </>
        )}
      </nav>
    </aside>
  );
}