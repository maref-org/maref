import { useSessionStore } from "@/stores/sessionStore";
import { MessageSquare, X } from "lucide-react";
import { cn } from "@/lib/utils";

export function AgentList() {
  const { sessions, activeSessionId, setActiveSession, removeSession } =
    useSessionStore();

  if (sessions.length === 0) {
    return (
      <div className="px-3 py-2 text-[11px] text-maref-text-muted">
        No active agents
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {sessions.map((session) => (
        <button
          key={session.id}
          onClick={() => setActiveSession(session.id)}
          className={cn(
            "flex w-full items-center gap-2 py-1.5 px-2 rounded-md text-xs transition-colors group",
            activeSessionId === session.id
              ? "bg-maref-surface-alt text-maref-text"
              : "text-maref-text-muted hover:bg-maref-surface-alt/50"
          )}
        >
          <MessageSquare className="h-3 w-3 flex-shrink-0" />
          <span className="truncate flex-1 text-left">{session.title}</span>
          <X
            className="h-3 w-3 opacity-0 group-hover:opacity-100 hover:text-maref-danger flex-shrink-0 transition-opacity"
            onClick={(e) => {
              e.stopPropagation();
              removeSession(session.id);
            }}
          />
        </button>
      ))}
    </div>
  );
}
