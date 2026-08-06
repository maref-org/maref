import { useState, useCallback } from "react";
import { MessageList } from "@/components/chat/MessageList";
import { ChatInput } from "@/components/chat/ChatInput";
import { SceneCards } from "@/components/chat/SceneCards";
import { ControlBar } from "@/components/chat/ControlBar";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useMessages } from "@/hooks/useSession";
import type { SceneId } from "@/types";

export function ChatPanel() {
  const { activeSessionId } = useSessionStore();
  const [activeScene, setActiveScene] = useState<SceneId | null>(null);
  const session = useSessionStore((s) =>
    s.sessions.find((sess) => sess.id === activeSessionId)
  );
  const isStreaming = useChatStore(
    (s) => activeSessionId && s.isStreaming[activeSessionId]
  );
  const { data } = useMessages(activeSessionId ?? "");

  const handleSceneSelect = useCallback((sceneId: SceneId) => {
    setActiveScene(sceneId);
  }, []);

  const messages = data?.messages ?? [];
  const hasMessages = messages.length > 0;

  const modeLabel =
    session?.mode === "chat"
      ? "对话"
      : session?.mode === "agent"
        ? "Agent 模式"
        : "完全访问";

  if (!activeSessionId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
        <div className="text-4xl">⚡</div>
        <p className="text-sm">选择或创建一个 Agent 会话开始</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0 flex items-center gap-3 border-b border-maref-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              session?.status === "thinking"
                ? "bg-maref-warning animate-pulse"
                : session?.status === "active"
                  ? "bg-maref-success"
                  : "bg-maref-text-muted"
            }`}
          />
          <span className="text-sm font-medium">
            {session?.title ?? "Agent"}
          </span>
        </div>
        {activeScene && (
          <span className="rounded bg-maref-surface-alt px-2 py-0.5 text-[10px] text-maref-accent">
            {activeScene === "web_reader"
              ? "网页读取"
              : activeScene === "research"
                ? "调研分析"
                : activeScene === "data_mining"
                  ? "数据挖掘"
                  : "文件管理"}
          </span>
        )}
        <span className="ml-auto text-xs text-maref-text-muted">
          {session?.model ?? "deepseek-v4-pro"} · {modeLabel}
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {hasMessages ? (
          <div className="max-w-[720px] mx-auto">
            <MessageList messages={messages} />
            {isStreaming && <ThinkingIndicator />}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-8 py-8">
            <SceneCards onSceneSelect={handleSceneSelect} />
          </div>
        )}
      </div>

      <ChatInput sessionId={activeSessionId} activeScene={hasMessages ? null : activeScene} hideSceneHint={hasMessages} />
      <ControlBar />
    </div>
  );
}
