import { useState } from "react";
import { Zap, Clock, Play, Cloud, Folder, Calendar, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

type AutomationTab = "configured" | "history" | "templates";

interface AutomationTask {
  id: string;
  name: string;
  description: string;
  schedule: string;
  location: "cloud" | "local";
  localPath?: string;
  enabled: boolean;
  source: "template" | "manual" | "chat";
}

interface TemplateItem {
  id: string;
  name: string;
  description: string;
  category: string;
  schedule: string;
  icon: string;
  color: string;
}

const TEMPLATES: TemplateItem[] = [
  { id: "t1", name: "每日 AI 新闻简报", description: "热点抓取、摘要生成、趋势分析", category: "信息聚合", schedule: "每日", icon: "📰", color: "#6366f1" },
  { id: "t2", name: "品牌舆情监控周报", description: "社媒抓取、情感分析、摘要输出", category: "舆情监控", schedule: "每周", icon: "📊", color: "#f59e0b" },
  { id: "t3", name: "每周竞品动态追踪", description: "产品更新追踪、社区反馈聚合", category: "竞争情报", schedule: "每周", icon: "🔍", color: "#22c55e" },
  { id: "t4", name: "股价监控与预警", description: "价格追踪、异常波动检测、预警推送", category: "金融监控", schedule: "每日", icon: "📈", color: "#ef4444" },
  { id: "t5", name: "安全漏洞扫描", description: "仓库扫描、CVE 匹配、风险分级", category: "代码安全", schedule: "定期", icon: "🛡", color: "#3b82f6" },
  { id: "t6", name: "扫描提交发现 Bug", description: "Diff 分析、静态扫描、高危识别", category: "代码质量", schedule: "触发/定期", icon: "🐛", color: "#8b5cf6" },
  { id: "t7", name: "补充测试覆盖", description: "变更分析、风险代码定位、测试生成", category: "工程效能", schedule: "触发", icon: "✅", color: "#06b6d4" },
  { id: "t8", name: "每日变更摘要", description: "Commit 聚合、可读化日报生成", category: "团队协作", schedule: "每日", icon: "📋", color: "#e11d48" },
];

const CONFIGURED_TASKS: AutomationTask[] = [
  {
    id: "at-001", name: "每日 AI 新闻简报", description: "多角色情报分析师 Prompt，聚合当天 AI 领域重大进展与技术突破", schedule: "每天 09:00",
    location: "local", localPath: "Downloads", enabled: true, source: "template",
  },
  {
    id: "at-002", name: "coding plan pro 订阅提醒", description: "监控阿里百炼套餐售罄状态，配额不足时推送通知", schedule: "每天 09:32",
    location: "cloud", enabled: true, source: "template",
  },
];

interface HistoryEntry {
  id: string;
  taskId: string;
  taskName: string;
  triggeredAt: string;
  status: "success" | "failed" | "running";
  executionType: "cloud" | "local";
  duration: string;
  summary: string;
}

const HISTORY_ENTRIES: HistoryEntry[] = [];

function AutomationTemplates() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-maref-text mb-1">任务模板</h2>
        <p className="text-sm text-maref-text-muted">选择一个模板快速创建自动化任务</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 max-w-4xl">
        {TEMPLATES.map((t) => (
          <button
            key={t.id}
            onClick={() => {}}
            className="flex items-start gap-3 rounded-xl border border-maref-border bg-maref-surface p-4 text-left transition-colors hover:border-maref-accent hover:bg-maref-surface-alt group"
          >
            <div
              className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg text-xl"
              style={{ backgroundColor: `${t.color}18` }}
            >
              {t.icon}
            </div>
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-medium text-maref-text group-hover:text-maref-accent transition-colors">
                {t.name}
              </h4>
              <p className="mt-0.5 text-xs text-maref-text-muted line-clamp-2">{t.description}</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-maref-border px-2 py-0.5 text-[10px] text-maref-text-muted">
                  <Calendar className="h-2.5 w-2.5" />
                  {t.schedule}
                </span>
                <span className="text-[10px] text-maref-text-muted">{t.category}</span>
              </div>
            </div>
            <ChevronRight className="mt-3 h-4 w-4 flex-shrink-0 text-maref-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
          </button>
        ))}
      </div>
    </div>
  );
}

function AutomationConfigured() {
  const [wakeEnabled, setWakeEnabled] = useState(true);

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="text-lg font-semibold text-maref-text mb-4">已配置</h2>

      <div className="flex items-center justify-between rounded-lg border border-maref-info/30 bg-maref-info/10 px-4 py-3 mb-5 max-w-3xl">
        <div className="flex items-center gap-2.5">
          <Zap className="h-4 w-4 text-maref-info flex-shrink-0" />
          <span className="text-sm text-maref-text">
            本地任务仅在 <strong>电脑保持唤醒</strong> 时运行
          </span>
        </div>
        <button
          onClick={() => setWakeEnabled(!wakeEnabled)}
          className={cn(
            "relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors",
            wakeEnabled ? "bg-maref-success" : "bg-maref-border"
          )}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform",
              wakeEnabled ? "translate-x-6" : "translate-x-1"
            )}
          />
        </button>
      </div>

      <div className="space-y-3 max-w-3xl">
        {CONFIGURED_TASKS.map((task) => (
          <div key={task.id} className="rounded-xl border border-maref-border bg-maref-surface p-4 flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="text-sm font-medium text-maref-text">{task.name}</h4>
                <span className="inline-flex items-center rounded-full bg-maref-accent/20 px-2 py-0.5 text-[10px] font-medium text-maref-accent">
                  MTC
                </span>
              </div>
              <p className="text-xs text-maref-text-muted line-clamp-2 mb-2">{task.description}</p>
              <div className="flex items-center gap-4">
                <span className="inline-flex items-center gap-1 text-[11px] text-maref-text-muted">
                  <Clock className="h-3 w-3" />
                  {task.schedule}
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] text-maref-text-muted">
                  {task.location === "cloud" ? (
                    <Cloud className="h-3 w-3" />
                  ) : (
                    <Folder className="h-3 w-3" />
                  )}
                  {task.location === "cloud" ? "云端" : task.localPath || "本地"}
                </span>
              </div>
            </div>
            <button
              onClick={() => {}}
              className={cn(
                "relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors",
                task.enabled ? "bg-maref-success" : "bg-maref-border"
              )}
            >
              <span
                className={cn(
                  "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform",
                  task.enabled ? "translate-x-6" : "translate-x-1"
                )}
              />
            </button>
          </div>
        ))}
        {CONFIGURED_TASKS.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-maref-text-muted">
            <Play className="h-8 w-8 mb-3 opacity-40" />
            <p className="text-sm">暂无已配置的任务</p>
            <p className="text-xs mt-1">从任务模板中创建你的第一个自动化任务</p>
          </div>
        )}
      </div>
    </div>
  );
}

function AutomationHistory() {
  const [taskType, setTaskType] = useState("all");
  const [env, setEnv] = useState("all-cloud");
  const [dateRange] = useState("2026/05/05 - 2026/05/11");

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="text-lg font-semibold text-maref-text mb-4">执行历史</h2>

      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <select
          value={taskType}
          onChange={(e) => setTaskType(e.target.value)}
          className="rounded-lg border border-maref-border bg-maref-surface px-3 py-2 text-sm text-maref-text focus:outline-none focus:border-maref-accent"
        >
          <option value="all">全部</option>
        </select>
        <select
          value={env}
          onChange={(e) => setEnv(e.target.value)}
          className="rounded-lg border border-maref-border bg-maref-surface px-3 py-2 text-sm text-maref-text focus:outline-none focus:border-maref-accent"
        >
          <option value="all-cloud">所有云端任务</option>
        </select>
        <div className="flex items-center gap-2 rounded-lg border border-maref-border bg-maref-surface px-3 py-2 text-sm text-maref-text-muted">
          <Calendar className="h-3.5 w-3.5" />
          <span>{dateRange}</span>
        </div>
      </div>

      {HISTORY_ENTRIES.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-maref-text-muted">
          <Clock className="h-10 w-10 mb-4 opacity-30" />
          <p className="text-sm font-medium">暂无执行记录</p>
          <p className="text-xs mt-1.5">配置自动化任务后，执行历史将在这里展示</p>
        </div>
      ) : (
        <div className="space-y-2 max-w-3xl">
          {HISTORY_ENTRIES.map((entry) => (
            <div key={entry.id} className="rounded-lg border border-maref-border bg-maref-surface p-4 flex items-center gap-4">
              <div className={cn(
                "h-2.5 w-2.5 rounded-full flex-shrink-0",
                entry.status === "success" ? "bg-maref-success" : entry.status === "failed" ? "bg-maref-danger" : "bg-maref-warning"
              )} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-maref-text font-medium">{entry.taskName}</p>
                <p className="text-xs text-maref-text-muted">{entry.summary}</p>
              </div>
              <span className="text-xs text-maref-text-muted">{entry.duration}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const TABS: { id: AutomationTab; label: string }[] = [
  { id: "configured", label: "已配置" },
  { id: "history", label: "执行历史" },
  { id: "templates", label: "任务模板" },
];

export function AutomationView() {
  const [activeTab, setActiveTab] = useState<AutomationTab>("configured");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-maref-border px-6 pt-4">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px",
              activeTab === tab.id
                ? "border-maref-accent text-maref-accent"
                : "border-transparent text-maref-text-muted hover:text-maref-text"
            )}
          >
            {tab.label}
          </button>
        ))}
        <div className="flex-1" />
        <div className="flex items-center gap-2 pr-2">
          <button className="rounded-lg border border-maref-border bg-maref-surface px-3 py-1.5 text-xs text-maref-text-muted hover:text-maref-text transition-colors">
            手动新建
          </button>
          <button className="rounded-lg bg-maref-accent px-3 py-1.5 text-xs text-white hover:bg-maref-accent-hover transition-colors">
            在对话中创建
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        {activeTab === "configured" && <AutomationConfigured />}
        {activeTab === "history" && <AutomationHistory />}
        {activeTab === "templates" && <AutomationTemplates />}
      </div>
    </div>
  );
}
