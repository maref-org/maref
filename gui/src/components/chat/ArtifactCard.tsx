import {
  FileText,
  Code2,
  Sheet,
  FileSpreadsheet,
  Eye,
  Download,
  Copy,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import type { Artifact } from "@/types";

interface Props {
  artifact: Artifact;
}

const TYPE_CONFIG: Record<
  Artifact["type"],
  { icon: React.ElementType; label: string; color: string }
> = {
  markdown: { icon: FileText, label: "Markdown", color: "text-maref-accent" },
  code: { icon: Code2, label: "代码", color: "text-maref-success" },
  excel: { icon: Sheet, label: "Excel", color: "text-maref-success" },
  ppt: { icon: FileSpreadsheet, label: "PPT", color: "text-maref-warning" },
  pdf: { icon: FileText, label: "PDF", color: "text-maref-danger" },
  image: { icon: FileText, label: "图片", color: "text-maref-info" },
  csv: { icon: Sheet, label: "CSV", color: "text-maref-success" },
};

function formatSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function ArtifactCard({ artifact }: Props) {
  const showToast = useUIStore((s) => s.showToast);
  const config = TYPE_CONFIG[artifact.type];
  const Icon = config.icon;

  const handlePreview = () => {
    showToast(`预览 "${artifact.name}" 即将上线`);
  };

  const handleDownload = () => {
    if (artifact.status === "generating") return;
    showToast(`下载 "${artifact.name}" 即将上线`);
  };

  const handleCopy = () => {
    if (artifact.preview) {
      navigator.clipboard.writeText(artifact.preview).then(() => {
        showToast("已复制到剪贴板");
      }).catch(() => {
        showToast("复制失败");
      });
    } else {
      showToast("无可复制内容");
    }
  };

  if (artifact.status === "generating") {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-maref-border bg-maref-surface px-3 py-2.5 animate-pulse">
        <Loader2 className="h-4 w-4 text-maref-accent animate-spin flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-maref-text truncate">{artifact.name}</p>
          <p className="text-[10px] text-maref-text-muted">生成中…</p>
        </div>
      </div>
    );
  }

  if (artifact.status === "error") {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-maref-danger/30 bg-maref-danger/5 px-3 py-2.5">
        <AlertCircle className="h-4 w-4 text-maref-danger flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-maref-text truncate">{artifact.name}</p>
          <p className="text-[10px] text-maref-danger">生成失败</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-maref-border bg-maref-surface overflow-hidden">
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Icon className={cn("h-5 w-5 flex-shrink-0", config.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-maref-text truncate">{artifact.name}</p>
            <span className="flex-shrink-0 rounded bg-maref-surface-alt px-1.5 py-0.5 text-[10px] text-maref-text-muted">
              {config.label}
            </span>
            {artifact.size && (
              <span className="text-[10px] text-maref-text-muted flex-shrink-0">
                {formatSize(artifact.size)}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1 border-t border-maref-border px-2 py-1.5">
        <button
          onClick={handlePreview}
          className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          title="预览"
        >
          <Eye className="h-3 w-3" />
          <span>预览</span>
        </button>
        <button
          onClick={handleDownload}
          className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          title="下载"
        >
          <Download className="h-3 w-3" />
          <span>下载</span>
        </button>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          title="复制"
        >
          <Copy className="h-3 w-3" />
          <span>复制</span>
        </button>
      </div>
    </div>
  );
}
