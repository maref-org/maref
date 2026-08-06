import { MessageSquare, Globe, Terminal, GitBranch, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TabView } from "@/types";

const TABS: { id: TabView; label: string; icon: React.ElementType }[] = [
  { id: "chat", label: "💬对话", icon: MessageSquare },
  { id: "browser", label: "🌐浏览器", icon: Globe },
  { id: "terminal", label: "⬛终端", icon: Terminal },
  { id: "git", label: "🔀Git", icon: GitBranch },
  { id: "governance", label: "🛡治理", icon: Shield },
];

interface Props {
  activeTab: TabView;
  onTabChange: (tab: TabView) => void;
  tabCounts?: Partial<Record<TabView, number>>;
}

export function TabBar({ activeTab, onTabChange, tabCounts = {} }: Props) {
  return (
    <div className="flex items-center border-b border-maref-border bg-maref-surface">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        const Icon = tab.icon;
        const count = tabCounts[tab.id];

        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative flex items-center gap-1.5 border-b-2 px-4 py-2 text-xs font-medium transition-colors",
              isActive
                ? "border-maref-accent text-maref-text"
                : "border-transparent text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt/50"
            )}
          >
            <Icon className="h-3.5 w-3.5 md:hidden" />
            <span className="hidden md:inline">{tab.label}</span>
            <span className="md:hidden">{tab.label.slice(0, 2)}</span>
            {count !== undefined && count > 0 && (
              <span className="ml-0.5 rounded-full bg-maref-danger px-1.5 py-0.5 text-[10px] leading-none text-white">
                {count > 99 ? "99+" : count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
