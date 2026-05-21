import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
import { User, Bot, Coins } from "lucide-react";
import { ToolCall } from "@/components/chat/ToolCall";
import { ArtifactCard } from "@/components/chat/ArtifactCard";
import type { Message, ToolCallResult } from "@/types";

interface Props {
  message: Message;
  toolResults?: Record<string, ToolCallResult>;
  agentColor?: string;
}

export function MessageBubble({ message, toolResults = {}, agentColor }: Props) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const isStreaming = message.status === "streaming";

  if (isSystem) {
    return (
      <div className="flex justify-center py-2">
        <p className="text-xs text-maref-text-muted italic bg-maref-surface-alt/50 rounded-full px-4 py-1">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex gap-3 py-2 animate-[fadeIn_200ms_ease-in]",
        isUser ? "flex-row-reverse" : ""
      )}
    >
      <div
        className={cn(
          "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-maref-accent"
            : "bg-maref-success/20 text-maref-success"
        )}
        style={!isUser && agentColor ? { backgroundColor: `${agentColor}20`, color: agentColor } : undefined}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-white" />
        ) : (
          <Bot className="h-3.5 w-3.5" />
        )}
      </div>

      <div className={cn("min-w-0", isUser ? "flex flex-col items-end" : "flex flex-col items-start")}>
        {!isUser && message.modelUsed && (
          <span className="mb-1 rounded-full bg-maref-surface-alt px-2 py-0.5 text-[10px] font-medium text-maref-text-muted">
            {message.modelUsed}
          </span>
        )}

        <div
          className={cn(
            "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-maref-accent text-white"
              : "bg-maref-surface text-maref-text"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">
              {message.content}
              {isStreaming && (
                <span className="inline-block w-1.5 h-4 ml-0.5 bg-white/60 animate-pulse align-middle" />
              )}
            </p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none [&_pre]:bg-maref-bg [&_pre]:rounded-lg [&_pre]:p-3 [&_code]:text-xs [&_li]:list-disc [&_ul]:pl-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                {message.content + (isStreaming ? " ▌" : "")}
              </ReactMarkdown>
              {isStreaming && (
                <div className="flex items-center gap-1 mt-1 text-[10px] text-maref-text-muted">
                  <Coins className="h-3 w-3" />
                  <span>生成中... {message.content.length} tokens</span>
                </div>
              )}
            </div>
          )}

          {message.toolCalls && message.toolCalls.length > 0 && (
            <details className="mt-2 group">
              <summary className="cursor-pointer text-[10px] text-maref-text-muted hover:text-maref-text transition-colors select-none">
                工具调用 ({message.toolCalls.length})
              </summary>
              <div className="mt-1.5 space-y-1">
                {message.toolCalls.map((tc) => {
                  const result = toolResults[tc.id];
                  return (
                    <ToolCall
                      key={tc.id}
                      toolName={tc.name}
                      input={tc.arguments}
                      output={result?.output}
                      status={result?.status ?? "pending"}
                      duration={result?.duration}
                    />
                  );
                })}
              </div>
            </details>
          )}
        </div>

        {message.artifacts && message.artifacts.length > 0 && (
          <div className="mt-2 space-y-2 max-w-[80%]">
            {message.artifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
