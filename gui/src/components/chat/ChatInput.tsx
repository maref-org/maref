import { useState, useRef, useCallback, useEffect } from "react";
import { ArrowUp, Paperclip, Mic, ChevronDown, Square, X, FileText, FileImage, FileCode, FileArchive } from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStream } from "@/hooks/useChatStream";
import { cn } from "@/lib/utils";
import type { SceneId } from "@/types";

interface Props {
  sessionId: string;
  activeScene?: SceneId | null;
  hideSceneHint?: boolean;
}

interface AttachedFile {
  name: string;
  size: number;
  type: string;
}

const MODELS = [
  { id: "auto", label: "自动选择" },
  { id: "deepseek-v4-pro", label: "DeepSeek-V4" },
  { id: "kimi-k2", label: "Kimi-K2" },
  { id: "gemma-4", label: "Gemma-4" },
];

const SCENE_HINTS: Record<SceneId, string> = {
  web_reader: "帮您抓取、解析在线文档和论文，提取关键信息并生成摘要。",
  research: "多平台信息聚合、对比分析，输出结构化调研报告。",
  data_mining: "市场数据抓取、清洗、趋势分析和可视化呈现。",
  file_management: "本地文件批量整理、重命名、清单生成和管理。",
};

const SCENE_PLACEHOLDERS: Record<SceneId, string> = {
  web_reader: "输入网页链接或文档地址…",
  research: "输入调研主题或关键词…",
  data_mining: "描述数据需求，如市场数据、行业报告…",
  file_management: "描述文件操作，如批量重命名、整理文件夹…",
};

const DEFAULT_HINT = "帮你整理论文综述、编写PPT、分析Excel等日常工作，输出专业级工作成果。";
const DEFAULT_PLACEHOLDER = "发送消息…";

function getFileIcon(name: string): React.ElementType {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const imageExts = ["png", "jpg", "jpeg", "gif", "svg", "webp", "ico"];
  const codeExts = ["ts", "tsx", "js", "jsx", "py", "rs", "go", "java", "c", "cpp", "h", "css", "html", "json", "yaml", "yml", "toml"];
  const archiveExts = ["zip", "tar", "gz", "rar", "7z"];
  if (imageExts.includes(ext)) return FileImage;
  if (codeExts.includes(ext)) return FileCode;
  if (archiveExts.includes(ext)) return FileArchive;
  return FileText;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function ChatInput({ sessionId, activeScene, hideSceneHint }: Props) {
  const [input, setInput] = useState("");
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [micToast, setMicToast] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const session = useSessionStore((s) => s.sessions.find((ss) => ss.id === sessionId));
  const updateSessionProvider = useSessionStore((s) => s.updateSessionProvider);
  const { sendAndStream, interrupt } = useChatStream();
  const isStreaming = session?.status === "thinking";

  useEffect(() => {
    if (micToast) {
      const timer = setTimeout(() => setMicToast(false), 2500);
      return () => clearTimeout(timer);
    }
  }, [micToast]);

  const handleSend = useCallback(() => {
    const content = input.trim();
    if (!content && attachedFiles.length === 0) return;
    sendAndStream(sessionId, content);
    setInput("");
    setAttachedFiles([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, sessionId, sendAndStream, attachedFiles]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    const newFiles: AttachedFile[] = Array.from(files).map((f) => ({
      name: f.name,
      size: f.size,
      type: f.type,
    }));
    setAttachedFiles((prev) => [...prev, ...newFiles]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const hint = activeScene ? SCENE_HINTS[activeScene] : DEFAULT_HINT;
  const placeholder = activeScene ? SCENE_PLACEHOLDERS[activeScene] : DEFAULT_PLACEHOLDER;
  const currentModel = MODELS.find((m) => m.id === session?.model) ?? MODELS[0];

  return (
    <div className="border-t border-maref-border bg-maref-surface p-4">
      {!hideSceneHint && (
        <p className="text-xs text-maref-text-muted text-center mb-3 leading-relaxed">
          {hint}
        </p>
      )}

      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {attachedFiles.map((file, i) => {
            const FileIcon = getFileIcon(file.name);
            return (
              <div
                key={`${file.name}-${i}`}
                className="flex items-center gap-1.5 rounded-md border border-maref-border bg-maref-surface-alt px-2 py-1 text-[10px] text-maref-text"
              >
                <FileIcon className="h-3 w-3 text-maref-text-muted flex-shrink-0" />
                <span className="max-w-[120px] truncate">{file.name}</span>
                <span className="text-maref-text-muted">{formatFileSize(file.size)}</span>
                <button
                  onClick={() => removeFile(i)}
                  className="ml-0.5 rounded p-0.5 text-maref-text-muted hover:text-maref-danger hover:bg-maref-danger/10 transition-colors"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-end gap-2 rounded-2xl border border-maref-border bg-maref-bg px-3 py-2 focus-within:border-maref-accent/50 transition-colors">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          multiple
          className="hidden"
        />

        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex-shrink-0 rounded p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          title="附件"
        >
          <Paperclip className="h-4 w-4" />
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="flex-1 resize-none bg-transparent text-sm text-maref-text placeholder-maref-text-muted outline-none max-h-[160px]"
        />

        <div className="relative flex-shrink-0">
          <button
            onClick={() => setMicToast(true)}
            className={cn(
              "flex-shrink-0 rounded p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-all",
              micToast && "text-maref-accent"
            )}
            title="语音输入"
          >
            <Mic className={cn("h-4 w-4", micToast && "animate-pulse")} />
          </button>
          {micToast && (
            <div className="absolute right-0 bottom-full mb-2 w-40 rounded-lg border border-maref-border bg-maref-surface px-3 py-2 shadow-lg z-50">
              <p className="text-[11px] text-maref-text text-center">语音输入即将上线</p>
              <div className="absolute bottom-0 right-3 translate-y-1/2 rotate-45 w-2 h-2 bg-maref-surface border-b border-r border-maref-border" />
            </div>
          )}
        </div>

        <div className="relative flex-shrink-0">
          <button
            onClick={() => setShowModelDropdown(!showModelDropdown)}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-maref-text-muted hover:bg-maref-surface-alt transition-colors"
          >
            {currentModel.label}
            <ChevronDown className="h-3 w-3" />
          </button>
          {showModelDropdown && (
            <div className="absolute bottom-full right-0 mb-1 w-36 rounded-lg border border-maref-border bg-maref-surface py-1 shadow-lg z-50">
              {MODELS.map((model) => (
                <button
                  key={model.id}
                  onClick={() => {
                    updateSessionProvider(sessionId, session?.provider ?? "bailian", model.id);
                    setShowModelDropdown(false);
                  }}
                  className={cn(
                    "w-full px-3 py-1.5 text-left text-xs transition-colors",
                    currentModel.id === model.id
                      ? "text-maref-accent bg-maref-surface-alt"
                      : "text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt/50"
                  )}
                >
                  {model.label}
                  {currentModel.id === model.id && (
                    <span className="ml-1 text-[10px] text-maref-success">✓</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {isStreaming ? (
          <button
            onClick={interrupt}
            className="flex-shrink-0 rounded-lg bg-maref-danger p-1.5 text-white hover:bg-red-500 transition-colors"
          >
            <Square className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim() && attachedFiles.length === 0}
            className="flex-shrink-0 rounded-full bg-maref-accent p-2 text-white hover:bg-maref-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
