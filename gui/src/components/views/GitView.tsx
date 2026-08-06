import { useState } from "react";
import {
  GitBranch,
  GitCommit,
  FileText,
  Plus,
  Minus,
  Diff,
  FolderGit2,
  AlertTriangle,
  Loader2,
  Circle,
  SquareStack,
  ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface GitFile {
  path: string;
  status: "M" | "A" | "D" | "??";
  staged: boolean;
}

interface GitCommitItem {
  hash: string;
  message: string;
  author: string;
  date: string;
}

const MOCK_BRANCH = "main";

const INITIAL_MODIFIED: GitFile[] = [
  { path: "src/App.tsx", status: "M", staged: false },
  { path: "src/stores/uiStore.ts", status: "M", staged: false },
  { path: "src/types/index.ts", status: "M", staged: false },
  { path: "src/components/chat/MessageBubble.tsx", status: "M", staged: false },
];

const INITIAL_STAGED: GitFile[] = [
  { path: "src/components/layout/TabBar.tsx", status: "A", staged: true },
  { path: "src/components/views/BrowserView.tsx", status: "A", staged: true },
];

const INITIAL_UNTRACKED: GitFile[] = [
  { path: "src/components/views/GitView.tsx", status: "??", staged: false },
  { path: "src/components/views/SkillsPanel.tsx", status: "??", staged: false },
];

const MOCK_COMMITS: GitCommitItem[] = [
  { hash: "a1b2c3d", message: "feat: add multi-view tab system (G5)", author: "frankie", date: "2 分钟前" },
  { hash: "e4f5g6h", message: "feat: add MarefDrawer with dashboard views (G4)", author: "frankie", date: "15 分钟前" },
  { hash: "i7j8k9l", message: "refactor: consolidate sidebar with FileTree + AgentList (G3)", author: "frankie", date: "1 小时前" },
  { hash: "m0n1o2p", message: "feat: integrate xterm.js WebSocket terminal (G2)", author: "frankie", date: "2 小时前" },
  { hash: "q3r4s5t", message: "chore: scaffold zustand stores and UI layout (G1)", author: "frankie", date: "3 小时前" },
  { hash: "u6v7w8x", message: "fix: resolve sidebar collapse animation", author: "frankie", date: "昨天" },
  { hash: "y9z0a1b", message: "feat: add chat streaming with SSE", author: "frankie", date: "昨天" },
  { hash: "c2d3e4f", message: "feat: add multi-provider model selection", author: "frankie", date: "2 天前" },
  { hash: "g5h6i7j", message: "chore: initial project setup with Vite + React 19", author: "frankie", date: "2 天前" },
  { hash: "k8l9m0n", message: "docs: add README with architecture overview", author: "frankie", date: "3 天前" },
];

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  M: { label: "M", color: "text-maref-warning", bg: "bg-maref-warning/10", icon: Circle },
  A: { label: "A", color: "text-maref-success", bg: "bg-maref-success/10", icon: Plus },
  D: { label: "D", color: "text-maref-danger", bg: "bg-maref-danger/10", icon: Minus },
  "??": { label: "??", color: "text-maref-text-muted", bg: "bg-maref-surface-alt", icon: Circle },
};

type GitState = "loading" | "no-repo" | "error" | "loaded";

const MOCK_DIFF = `@@ -1,5 +1,7 @@
 import { useState } from "react";
-import { cn } from "@/lib/utils";
+import { cn } from "@/lib/utils";
+import { useUIStore } from "@/stores/uiStore";

 export function App() {
-  const [open, setOpen] = useState(false);
+  const { sidebarOpen, toggleSidebar } = useUIStore();`;

export function GitView() {
  const [state] = useState<GitState>("loaded");
  const [stagedFiles, setStagedFiles] = useState<GitFile[]>(INITIAL_STAGED);
  const [modifiedFiles, setModifiedFiles] = useState<GitFile[]>(INITIAL_MODIFIED);
  const [untrackedFiles, setUntrackedFiles] = useState<GitFile[]>(INITIAL_UNTRACKED);
  const [expandedDiff, setExpandedDiff] = useState<string | null>(null);

  const handleStage = (file: GitFile) => {
    if (file.status === "??") {
      setUntrackedFiles((prev) => prev.filter((f) => f.path !== file.path));
    } else {
      setModifiedFiles((prev) => prev.filter((f) => f.path !== file.path));
    }
    setStagedFiles((prev) => [
      ...prev,
      { ...file, status: "A" as const, staged: true },
    ]);
  };

  const handleUnstage = (file: GitFile) => {
    setStagedFiles((prev) => prev.filter((f) => f.path !== file.path));
    setModifiedFiles((prev) => [
      ...prev,
      { ...file, status: "M" as const, staged: false },
    ]);
  };

  const handleDiff = (file: GitFile) => {
    if (expandedDiff === file.path) {
      setExpandedDiff(null);
    } else {
      setExpandedDiff(file.path);
    }
  };

  if (state === "loading") {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-maref-text-muted">
        <Loader2 className="h-5 w-5 animate-spin text-maref-accent" />
        <span className="text-sm">读取 Git 状态…</span>
      </div>
    );
  }

  if (state === "no-repo") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
        <FolderGit2 className="h-8 w-8" />
        <p className="text-sm">当前目录不是 Git 仓库</p>
        <code className="rounded bg-maref-surface-alt px-3 py-1.5 text-xs font-mono text-maref-text">
          git init &amp;&amp; git add . &amp;&amp; git commit -m "init"
        </code>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
        <AlertTriangle className="h-8 w-8 text-maref-danger" />
        <p className="text-sm text-maref-danger">Git 状态读取失败</p>
      </div>
    );
  }

  const totalFiles = stagedFiles.length + modifiedFiles.length + untrackedFiles.length;

  return (
    <div className="flex h-full flex-col overflow-auto bg-maref-bg">
      <div className="flex items-center gap-3 border-b border-maref-border bg-maref-surface px-4 py-3 flex-shrink-0">
        <GitBranch className="h-4 w-4 text-maref-accent" />
        <span className="text-sm font-medium text-maref-text">当前分支</span>
        <span className="rounded-full bg-maref-accent/15 px-2.5 py-0.5 text-xs font-mono text-maref-accent">
          {MOCK_BRANCH}
        </span>
        <span className="ml-auto text-[11px] text-maref-text-muted">
          10 次提交 · {totalFiles} 个文件变更
        </span>
      </div>

      <div className="flex-1 space-y-6 p-5">
        <FileSection
          title="暂存的文件"
          icon={SquareStack}
          files={stagedFiles}
          actionLabel="取消暂存"
          actionIcon={Minus}
          onAction={handleUnstage}
          onDiff={handleDiff}
          expandedDiff={expandedDiff}
        />

        <FileSection
          title="已修改"
          icon={Circle}
          files={modifiedFiles}
          actionLabel="暂存"
          actionIcon={Plus}
          onAction={handleStage}
          onDiff={handleDiff}
          expandedDiff={expandedDiff}
        />

        <FileSection
          title="未跟踪的文件"
          icon={Circle}
          files={untrackedFiles}
          actionLabel="添加"
          actionIcon={Plus}
          onAction={handleStage}
          onDiff={handleDiff}
          expandedDiff={expandedDiff}
        />

        <section>
          <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <GitCommit className="h-3.5 w-3.5" />
            最近提交
          </h3>
          <div className="overflow-hidden rounded-lg border border-maref-border">
            <div className="divide-y divide-maref-border">
              {MOCK_COMMITS.map((commit) => (
                <div
                  key={commit.hash}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-maref-surface-alt/30 transition-colors"
                >
                  <span className="font-mono text-xs text-maref-accent">
                    {commit.hash}
                  </span>
                  <span className="flex-1 text-xs text-maref-text truncate">
                    {commit.message}
                  </span>
                  <span className="text-[11px] text-maref-text-muted">
                    {commit.author}
                  </span>
                  <span className="text-[11px] text-maref-text-muted flex-shrink-0">
                    {commit.date}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function FileSection({
  title,
  icon: TitleIcon,
  files,
  actionLabel,
  actionIcon: ActionIcon,
  onAction,
  onDiff,
  expandedDiff,
}: {
  title: string;
  icon: React.ElementType;
  files: GitFile[];
  actionLabel: string;
  actionIcon: React.ElementType;
  onAction: (file: GitFile) => void;
  onDiff: (file: GitFile) => void;
  expandedDiff: string | null;
}) {
  if (files.length === 0) return null;

  return (
    <section>
      <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
        <TitleIcon className="h-3.5 w-3.5" />
        {title}
        <span className="rounded-full bg-maref-surface-alt px-1.5 py-0.5 text-[10px]">
          {files.length}
        </span>
      </h3>
      <div className="overflow-hidden rounded-lg border border-maref-border">
        {files.map((file) => {
          const status = STATUS_CONFIG[file.status] ?? STATUS_CONFIG["??"];
          const isExpanded = expandedDiff === file.path;
          return (
            <div key={file.path}>
              <div className="flex items-center gap-3 border-b border-maref-border px-4 py-2.5 last:border-0 hover:bg-maref-surface-alt/30 transition-colors">
                <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-mono font-medium", status.bg, status.color)}>
                  {status.label}
                </span>
                <FileText className="h-3.5 w-3.5 text-maref-text-muted flex-shrink-0" />
                <span className="flex-1 text-xs font-mono text-maref-text truncate">
                  {file.path}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => onDiff(file)}
                    className={cn(
                      "rounded p-1 transition-colors",
                      isExpanded
                        ? "text-maref-accent bg-maref-accent/10"
                        : "text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt"
                    )}
                  >
                    <Diff className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => onAction(file)}
                    className="rounded px-2 py-0.5 text-[10px] text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt transition-colors flex items-center gap-1"
                  >
                    <ActionIcon className="h-3 w-3" />
                    {actionLabel}
                  </button>
                </div>
              </div>
              {isExpanded && (
                <div className="border-b border-maref-border bg-[#0d0f15] p-4 last:border-0">
                  <div className="flex items-center gap-2 mb-2">
                    <ChevronDown className="h-3 w-3 text-maref-text-muted" />
                    <span className="text-[11px] font-medium text-maref-text">{file.path}</span>
                  </div>
                  <pre className="text-[11px] font-mono text-maref-text-muted leading-relaxed overflow-x-auto whitespace-pre">
                    <code>{MOCK_DIFF}</code>
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
