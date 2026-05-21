import { useState, useMemo, useEffect } from "react";
import {
  Search,
  Download,
  Power,
  PowerOff,
  Trash2,
  Code2,
  FolderOpen,
  Globe,
  Terminal,
  Puzzle,
  Wrench,
  Loader2,
  PackageOpen,
  CheckCircle2,
  AlertTriangle,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Skill } from "@/types";

type SkillCategory = "code" | "files" | "browser" | "terminal" | "integration" | "custom";
type SkillStatus = "available" | "installed" | "enabled" | "disabled";

const CATEGORY_CONFIG: Record<SkillCategory, { label: string; icon: React.ElementType }> = {
  code: { label: "代码", icon: Code2 },
  files: { label: "文件", icon: FolderOpen },
  browser: { label: "浏览器", icon: Globe },
  terminal: { label: "终端", icon: Terminal },
  integration: { label: "集成", icon: Puzzle },
  custom: { label: "自定义", icon: Wrench },
};

interface SkillItem extends Skill {
  category: SkillCategory;
}

const MOCK_SKILLS: SkillItem[] = [
  { id: "sk-1", name: "brainstorming", description: "创建功能、构建组件前的需求探索与设计", version: "2.1.0", installed: true, author: "maref", category: "code" },
  { id: "sk-2", name: "test-driven-development", description: "编写实现代码前先写测试的红绿重构循环", version: "1.5.0", installed: true, author: "maref", category: "code" },
  { id: "sk-3", name: "systematic-debugging", description: "系统化调试：复现、诊断、修复、验证", version: "1.3.0", installed: true, author: "maref", category: "code" },
  { id: "sk-4", name: "planning-with-files", description: "Manus 风格文件化任务规划与进度追踪", version: "1.0.0", installed: true, author: "maref", category: "files" },
  { id: "sk-5", name: "cloud-manage", description: "管理云 AI 提供商：百炼/腾讯云/英伟达", version: "1.2.0", installed: false, author: "maref", category: "integration" },
  { id: "sk-6", name: "browser-automation", description: "Playwright 驱动的浏览器自动化操作", version: "0.9.0", installed: false, author: "maref", category: "browser" },
  { id: "sk-7", name: "file-scanner", description: "递归扫描项目结构、检测安全漏洞", version: "1.1.0", installed: true, author: "community", category: "files" },
  { id: "sk-8", name: "git-worktrees", description: "隔离的 Git 工作树创建与安全验证", version: "1.0.0", installed: false, author: "maref", category: "terminal" },
  { id: "sk-9", name: "verification-before-completion", description: "声明完成前强制运行验证命令", version: "1.4.0", installed: true, author: "maref", category: "code" },
  { id: "sk-10", name: "writing-plans", description: "有规范或需求时的多步骤实施计划", version: "1.1.0", installed: false, author: "maref", category: "files" },
  { id: "sk-11", name: "writing-skills", description: "创建和编辑 Agent 技能定义文件", version: "0.8.0", installed: false, author: "maref", category: "custom" },
  { id: "sk-12", name: "cpp-performance-analyzer", description: "C++ 性能热点分析与火焰图生成", version: "2.0.0", installed: false, author: "community", category: "code" },
];

const STATUS_LABELS: Record<SkillStatus, string> = {
  available: "可用",
  installed: "已安装",
  enabled: "已启用",
  disabled: "已禁用",
};

const STATUS_STYLES: Record<SkillStatus, string> = {
  available: "bg-maref-surface-alt text-maref-text-muted",
  installed: "bg-maref-success/10 text-maref-success",
  enabled: "bg-maref-accent/10 text-maref-accent",
  disabled: "bg-maref-warning/10 text-maref-warning",
};

type PanelState = "loading" | "empty" | "error" | "loaded";

export function SkillsPanel() {
  const [state] = useState<PanelState>("loaded");
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<SkillCategory | "all">("all");
  const [installedFilter, setInstalledFilter] = useState<"all" | "installed" | "available">("all");
  const [skillStatuses, setSkillStatuses] = useState<Record<string, SkillStatus>>(() =>
    Object.fromEntries(MOCK_SKILLS.map((s) => [s.id, s.installed ? ("installed" as SkillStatus) : ("available" as SkillStatus)]))
  );
  const [toast, setToast] = useState<{ message: string; type: "success" | "warning" } | null>(null);
  const [confirmUninstall, setConfirmUninstall] = useState<string | null>(null);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const handleInstall = (skillId: string) => {
    setSkillStatuses((prev) => ({ ...prev, [skillId]: "installed" }));
    setToast({ message: "技能安装成功", type: "success" });
  };

  const handleEnable = (skillId: string) => {
    setSkillStatuses((prev) => ({ ...prev, [skillId]: "enabled" }));
    setToast({ message: "技能已启用", type: "success" });
  };

  const handleDisable = (skillId: string) => {
    setSkillStatuses((prev) => ({ ...prev, [skillId]: "disabled" }));
    setToast({ message: "技能已禁用", type: "warning" });
  };

  const handleUninstall = (skillId: string) => {
    setSkillStatuses((prev) => ({ ...prev, [skillId]: "available" }));
    setToast({ message: "技能已卸载", type: "success" });
    setConfirmUninstall(null);
  };

  const filterCategories = ["all", ...Object.keys(CATEGORY_CONFIG)] as Array<SkillCategory | "all">;

  const filtered = useMemo(() => {
    let items = MOCK_SKILLS;
    if (search) {
      const q = search.toLowerCase();
      items = items.filter((s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q));
    }
    if (activeCategory !== "all") {
      items = items.filter((s) => s.category === activeCategory);
    }
    if (installedFilter === "installed") {
      items = items.filter((s) => skillStatuses[s.id] !== "available");
    } else if (installedFilter === "available") {
      items = items.filter((s) => skillStatuses[s.id] === "available");
    }
    return items;
  }, [search, activeCategory, installedFilter, skillStatuses]);

  if (state === "loading") {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-maref-text-muted">
        <Loader2 className="h-5 w-5 animate-spin text-maref-accent" />
        <span className="text-sm">加载技能列表…</span>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
        <PackageOpen className="h-8 w-8" />
        <p className="text-sm">没有可用的技能</p>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
        <p className="text-sm text-maref-danger">技能列表加载失败</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-auto bg-maref-bg relative">
      {toast && (
        <div className="absolute top-3 right-4 z-50 flex items-center gap-2 rounded-lg border border-maref-border bg-maref-surface px-3 py-2 shadow-lg animate-in fade-in slide-in-from-top-2">
          {toast.type === "success" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-maref-success" />
          ) : (
            <AlertTriangle className="h-3.5 w-3.5 text-maref-warning" />
          )}
          <span className="text-xs text-maref-text">{toast.message}</span>
          <button onClick={() => setToast(null)} className="ml-1 rounded p-0.5 text-maref-text-muted hover:text-maref-text">
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-4 py-3 space-y-3">
        <div className="flex items-center gap-2 rounded-md border border-maref-border bg-maref-surface-alt px-3 py-1.5">
          <Search className="h-3.5 w-3.5 text-maref-text-muted flex-shrink-0" />
          <input
            className="flex-1 bg-transparent text-xs text-maref-text outline-none placeholder:text-maref-text-muted"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索技能名称或描述…"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto">
          {filterCategories.map((cat) => {
            const isActive = activeCategory === cat;
            const config = cat !== "all" ? CATEGORY_CONFIG[cat as SkillCategory] : null;
            const CatIcon = config?.icon;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={cn(
                  "flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors flex-shrink-0",
                  isActive
                    ? "border-maref-accent/40 bg-maref-accent/10 text-maref-accent"
                    : "border-maref-border bg-maref-surface-alt text-maref-text-muted hover:text-maref-text"
                )}
              >
                {CatIcon && <CatIcon className="h-3 w-3" />}
                {cat === "all" ? "全部" : config?.label ?? cat}
              </button>
            );
          })}
        </div>

        <div className="flex gap-1">
          {(["all", "installed", "available"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setInstalledFilter(f)}
              className={cn(
                "rounded px-2 py-0.5 text-[10px] transition-colors",
                installedFilter === f
                  ? "bg-maref-accent/15 text-maref-accent"
                  : "text-maref-text-muted hover:text-maref-text"
              )}
            >
              {f === "all" ? "全部" : f === "installed" ? "已安装" : "可用"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 p-4">
        <div className="grid grid-cols-1 gap-2">
          {filtered.map((skill) => {
            const catConfig = CATEGORY_CONFIG[skill.category];
            const CatIcon = catConfig.icon;
            const status = skillStatuses[skill.id] ?? "available";
            return (
              <div
                key={skill.id}
                className="flex items-start gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3 hover:border-maref-accent/30 transition-colors"
              >
                <div className="rounded-lg bg-maref-accent/10 p-2 flex-shrink-0">
                  <CatIcon className="h-4 w-4 text-maref-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-maref-text">{skill.name}</span>
                    <span className="text-[10px] text-maref-text-muted">v{skill.version}</span>
                    <span className={cn(
                      "ml-auto rounded-full px-1.5 py-0.5 text-[10px] transition-colors",
                      STATUS_STYLES[status]
                    )}>
                      {STATUS_LABELS[status]}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-maref-text-muted line-clamp-2">
                    {skill.description}
                  </p>
                  <div className="mt-2 flex items-center gap-1.5">
                    <span className="text-[10px] text-maref-text-muted">
                      {catConfig.label}
                    </span>
                    <span className="text-[10px] text-maref-text-muted">·</span>
                    <span className="text-[10px] text-maref-text-muted">{skill.author}</span>
                    <div className="ml-auto flex items-center gap-1">
                      {status === "available" && (
                        <button
                          onClick={() => handleInstall(skill.id)}
                          className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-maref-success hover:bg-maref-success/10 transition-colors"
                          title="安装"
                        >
                          <Download className="h-3 w-3" />
                          安装
                        </button>
                      )}

                      {status === "disabled" && (
                        <button
                          onClick={() => handleEnable(skill.id)}
                          className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-maref-success hover:bg-maref-success/10 transition-colors"
                          title="启用"
                        >
                          <Power className="h-3 w-3" />
                          启用
                        </button>
                      )}

                      {(status === "installed" || status === "enabled") && (
                        <button
                          onClick={() => handleDisable(skill.id)}
                          className="rounded p-1 text-maref-text-muted hover:text-maref-danger hover:bg-maref-danger/10 transition-colors"
                          title="禁用"
                        >
                          <PowerOff className="h-3 w-3" />
                        </button>
                      )}

                      {(status === "installed" || status === "disabled" || status === "enabled") && (
                        confirmUninstall === skill.id ? (
                          <div className="flex items-center gap-1">
                            <span className="text-[10px] text-maref-warning">确认?</span>
                            <button
                              onClick={() => handleUninstall(skill.id)}
                              className="rounded px-1.5 py-0.5 text-[10px] text-maref-success hover:bg-maref-success/10 transition-colors"
                            >
                              是
                            </button>
                            <button
                              onClick={() => setConfirmUninstall(null)}
                              className="rounded px-1.5 py-0.5 text-[10px] text-maref-text-muted hover:bg-maref-surface-alt transition-colors"
                            >
                              否
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmUninstall(skill.id)}
                            className="rounded p-1 text-maref-text-muted hover:text-maref-danger hover:bg-maref-danger/10 transition-colors"
                            title="卸载"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        )
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-maref-text-muted">
            <PackageOpen className="h-6 w-6" />
            <p className="text-xs">没有匹配的技能</p>
          </div>
        )}
      </div>
    </div>
  );
}
