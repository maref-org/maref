import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MarefSection } from "@/components/layout/Sidebar";
import { HomeDashboard } from "@/components/layout/HomeDashboard";
import { SkillsPanel } from "@/components/views/SkillsPanel";
import { SettingsView } from "@/components/views/SettingsView";
import { AutomationView } from "@/components/views/AutomationView";
import TaskPanelView from "@/components/views/TaskPanelView";
import { ToolPanelView } from "@/components/tools";
import {
  DesktopAgentView,
  GovernanceView,
  AuditLogView,
  DriftDetectionView,
  AnomalyMonitorView,
  TrustScoreView,
  FormalVerificationView,
} from "@/components/views/MarefViews";

const DRAWER_LABELS: Record<MarefSection, string> = {
  home: "首页仪表盘",
  desktop: "桌面 Agent",
  governance: "治理看板",
  audit: "审计日志",
  drift: "漂移检测",
  anomaly: "异常监控",
  trust: "信任评分",
  formal: "形式验证",
  skills: "技能市场",
  automation: "自动化",
  tasks: "任务面板",
  tools: "工具管理",
  settings: "设置",
};

const SECTION_VIEWS: Record<MarefSection, React.ComponentType> = {
  home: HomeDashboard,
  desktop: DesktopAgentView,
  governance: GovernanceView,
  audit: AuditLogView,
  drift: DriftDetectionView,
  anomaly: AnomalyMonitorView,
  trust: TrustScoreView,
  formal: FormalVerificationView,
  skills: SkillsPanel,
  automation: AutomationView,
  tasks: TaskPanelView,
  tools: ToolPanelView,
  settings: SettingsView,
};

interface Props {
  section: MarefSection | null;
  onClose: () => void;
}

export function MarefDrawer({ section, onClose }: Props) {
  if (!section) return null;

  const ViewComponent = SECTION_VIEWS[section];
  const label = DRAWER_LABELS[section];

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex justify-end",
        "animate-[fadeIn_150ms_ease-out]"
      )}
    >
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      <div
        className={cn(
          "relative z-10 h-full w-[450px] flex-shrink-0 overflow-hidden",
          "border-l border-maref-border bg-maref-bg shadow-2xl",
          "animate-[slideInRight_150ms_ease-out]"
        )}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-maref-border px-4 py-3 flex-shrink-0">
            <h2 className="text-sm font-semibold text-maref-text">{label}</h2>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <ViewComponent />
          </div>
        </div>
      </div>
    </div>
  );
}

// Tailwind needs these custom animations
// @keyframes slideInRight { from { transform: translateX(100%) } to { transform: translateX(0) } }
// @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
