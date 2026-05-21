import { useState } from "react";
import {
  Monitor,
  GitBranch,
  Cloud,
  FolderOpen,
  ChevronDown,
  Check,
  FolderSearch,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Environment = "local" | "worktree" | "cloud";

interface ProjectItem {
  id: string;
  name: string;
  path: string;
}

const ENV_OPTIONS: { id: Environment; label: string; icon: React.ElementType }[] = [
  { id: "local", label: "本地", icon: Monitor },
  { id: "worktree", label: "工作树", icon: GitBranch },
  { id: "cloud", label: "云端", icon: Cloud },
];

const MOCK_PROJECTS: ProjectItem[] = [
  { id: "p1", name: "maref-experiments", path: "~/projects/maref-experiments" },
  { id: "p2", name: "athena-core", path: "~/projects/athena-core" },
  { id: "p3", name: "opencode", path: "~/projects/opencode" },
  { id: "p4", name: "data-pipeline", path: "~/projects/data-pipeline" },
];

const RECENT_PROJECTS = MOCK_PROJECTS.slice(0, 3);

export function ControlBar() {
  const [env, setEnv] = useState<Environment>("local");
  const [envOpen, setEnvOpen] = useState(false);
  const [project, setProject] = useState<ProjectItem>(MOCK_PROJECTS[0]);
  const [projectOpen, setProjectOpen] = useState(false);

  return (
    <div className="flex items-center gap-4 border-t border-maref-border bg-maref-surface-alt/60 px-4 py-2">
      <div className="relative">
        <button
          onClick={() => {
            setEnvOpen(!envOpen);
            setProjectOpen(false);
          }}
          className="flex items-center gap-1.5 rounded-md border border-maref-border bg-maref-surface px-2.5 py-1 text-xs text-maref-text transition-colors hover:border-maref-accent/40"
        >
          {env === "local" ? (
            <Monitor className="h-3.5 w-3.5 text-maref-success" />
          ) : env === "worktree" ? (
            <GitBranch className="h-3.5 w-3.5 text-maref-warning" />
          ) : (
            <Cloud className="h-3.5 w-3.5 text-maref-info" />
          )}
          <span>{ENV_OPTIONS.find((e) => e.id === env)?.label}</span>
          <ChevronDown className="h-3 w-3 text-maref-text-muted" />
        </button>

        {envOpen && (
          <div className="absolute bottom-full left-0 mb-1 w-36 rounded-lg border border-maref-border bg-maref-surface py-1 shadow-lg z-50">
            {ENV_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                onClick={() => {
                  setEnv(opt.id);
                  setEnvOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-1.5 text-xs transition-colors",
                  env === opt.id
                    ? "text-maref-accent bg-maref-surface-alt"
                    : "text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt/50"
                )}
              >
                <opt.icon className="h-3.5 w-3.5 flex-shrink-0" />
                <span>{opt.label}</span>
                {env === opt.id && <Check className="h-3 w-3 ml-auto text-maref-success flex-shrink-0" />}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="relative">
        <button
          onClick={() => {
            setProjectOpen(!projectOpen);
            setEnvOpen(false);
          }}
          className="flex items-center gap-1.5 rounded-md border border-maref-border bg-maref-surface px-2.5 py-1 text-xs text-maref-text transition-colors hover:border-maref-accent/40"
        >
          <FolderOpen className="h-3.5 w-3.5 text-maref-accent" />
          <span className="max-w-[160px] truncate">{project.name}</span>
          <span className="text-maref-text-muted truncate max-w-[100px] hidden sm:inline">
            {project.path.replace(/^~\/projects\//, "")}
          </span>
          <ChevronDown className="h-3 w-3 text-maref-text-muted flex-shrink-0" />
        </button>

        {projectOpen && (
          <div className="absolute bottom-full left-0 mb-1 w-72 rounded-lg border border-maref-border bg-maref-surface py-1 shadow-lg z-50">
            <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
              最近使用
            </div>
            {RECENT_PROJECTS.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  setProject(p);
                  setProjectOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-1.5 text-xs transition-colors",
                  project.id === p.id
                    ? "text-maref-accent bg-maref-surface-alt"
                    : "text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt/50"
                )}
              >
                <FolderOpen className="h-3.5 w-3.5 flex-shrink-0" />
                <span>{p.name}</span>
                <span className="ml-auto text-maref-text-muted truncate max-w-[120px]">{p.path}</span>
                {project.id === p.id && <Check className="h-3 w-3 text-maref-success flex-shrink-0" />}
              </button>
            ))}
            <div className="border-t border-maref-border mt-1 pt-1">
              <button
                onClick={() => setProjectOpen(false)}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt/50 transition-colors"
              >
                <FolderSearch className="h-3.5 w-3.5 flex-shrink-0" />
                <span>选择文件夹…</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
