import { useSessionStore } from "@/stores/sessionStore";
import { useUIStore } from "@/stores/uiStore";
import { ContextGauge } from "@/components/status/ContextGauge";
import { GovernanceStatus } from "@/components/status/GovernanceStatus";
import { PetIndicator } from "@/components/status/PetIndicator";
import { TokenUsage } from "@/components/status/TokenUsage";
import { Monitor, GitBranch } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { getBackendMode } from "@/api/client";
import { useEffect, useState } from "react";

function BackendIndicator() {
  const [mode, setMode] = useState(getBackendMode());

  useEffect(() => {
    const interval = setInterval(() => {
      setMode(getBackendMode());
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  if (mode === "checking") {
    return (
      <span className="flex items-center gap-1 flex-shrink-0">
        <span className="h-2 w-2 rounded-full bg-maref-danger" />
        <span className="text-maref-danger">未连接</span>
      </span>
    );
  }

  if (mode === "mock") {
    return (
      <span className="flex items-center gap-1 flex-shrink-0">
        <span className="h-2 w-2 rounded-full bg-maref-warning" />
        <span className="text-maref-warning">模拟模式</span>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1 flex-shrink-0">
      <span className="h-2 w-2 rounded-full bg-maref-success" />
      <span className="text-maref-success">已连接</span>
    </span>
  );
}

export function StatusBar() {
  const { activeSessionId, sessions } = useSessionStore();
  const { theme, toggleTheme } = useUIStore();
  const session = sessions.find((s) => s.id === activeSessionId);
  const isStreaming = useChatStore(
    (s) => activeSessionId && s.isStreaming[activeSessionId]
  );

  return (
    <footer className="flex h-8 items-center gap-3 border-t border-maref-border bg-maref-surface px-3 text-[11px] text-maref-text-muted flex-shrink-0 select-none overflow-x-auto">
      <span className="flex items-center gap-1 flex-shrink-0">
        <Monitor className="h-3 w-3 text-maref-success" />
        本机
      </span>

      <span className="text-maref-border flex-shrink-0">|</span>

      <GovernanceStatus
        state="OBSERVE"
        entropy={2}
        cbState="CLOSED"
        anomalyCount={0}
      />

      {session && (
        <>
          <span className="text-maref-border flex-shrink-0">|</span>
          <ContextGauge percent={session.contextPercent} isStreaming={!!isStreaming} />
          <span className="text-maref-border flex-shrink-0">|</span>
          <BackendIndicator />
          <span className="flex items-center gap-1 flex-shrink-0">
            <GitBranch className="h-3 w-3" />
            main
          </span>
          <span className="text-maref-border flex-shrink-0">|</span>
          <span className="flex items-center gap-1 flex-shrink-0">
            <Monitor className="h-3 w-3" />
            {session.model}
          </span>
          <span className="text-maref-border flex-shrink-0">|</span>
          <div className="w-24 flex-shrink-0">
            <TokenUsage used={125_000} total={1_000_000} compact />
          </div>
        </>
      )}

      <PetIndicator />

      <button
        onClick={toggleTheme}
        className="flex-shrink-0 rounded px-1 hover:bg-maref-surface-alt transition-colors ml-1"
      >
        {theme === "dark" ? "🌙" : "☀️"}
      </button>
    </footer>
  );
}
