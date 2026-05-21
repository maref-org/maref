import { useEffect, useRef } from "react";
import type { Message } from "@/types";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { AgentCapabilities } from "@/components/chat/AgentCapabilities";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

interface Props {
  messages: Message[];
}

export function MessageList({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isStreaming = useChatStore((s) =>
    Object.values(s.isStreaming).some(Boolean)
  );
  const sessions = useSessionStore((s) => s.sessions);
  const agentColorMap = useSessionStore((s) => s.agentColorMap);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-maref-text-muted">
        发送消息启动 Agent 会话
      </div>
    );
  }

  const uniqueAgents = [...new Set(messages.map((m) => m.sessionId))];
  const multiAgent = uniqueAgents.length > 1;

  return (
    <div className="flex flex-col gap-0 px-4 py-4">
      {messages.map((msg) => {
        const agent = sessions.find((s) => s.id === msg.sessionId);
        const agentColor = agentColorMap[msg.sessionId] ?? "#6366f1";

        return (
          <div key={msg.id}>
            {multiAgent && msg.role === "assistant" && agent && (
              <div className="ml-10 mt-2 mb-0.5 flex items-center gap-1.5">
                <span
                  className="h-2 w-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: agentColor }}
                />
                <span
                  className="text-[10px] font-medium"
                  style={{ color: agentColor }}
                >
                  {agent.title}
                </span>
              </div>
            )}
            <MessageBubble message={msg} agentColor={multiAgent ? agentColor : undefined} />
            {msg.capabilities && msg.capabilities.length > 0 && (
              <AgentCapabilities capabilities={msg.capabilities} />
            )}
          </div>
        );
      })}
      {isStreaming && <ThinkingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
