import { useCallback, useRef } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import { api } from "@/api/client";

export function useChatStream() {
  const sendingRef = useRef(false);
  const { addMessage, startStreaming } = useChatStore();
  const { updateSession } = useSessionStore();
  const abortRef = useRef<AbortController | null>(null);

  const sendAndStream = useCallback(
    async (sessionId: string, content: string) => {
      if (sendingRef.current) return;
      sendingRef.current = true;

      try {
        await api.sendMessage(sessionId, content);
        addMessage(sessionId, {
          id: `msg-${Date.now()}`,
          sessionId,
          role: "user",
          content,
          timestamp: new Date().toISOString(),
        });

        updateSession(sessionId, { status: "thinking" });
        startStreaming(sessionId);

        const controller = new AbortController();
        abortRef.current = controller;

        const response = await fetch(`/api/sessions/${sessionId}/stream`, {
          signal: controller.signal,
          headers: { Accept: "text/event-stream" },
        });

        if (!response.body) return;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        const currentMsgId = `msg-${Date.now()}`;
        let fullContent = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            if (!part.trim()) continue;
            const eventMatch = part.match(/^event: (\w+)/m);
            const dataMatch = part.match(/^data: (.+)/m);

            if (!eventMatch || !dataMatch) continue;

            try {
              const data = JSON.parse(dataMatch[1]);

              if (data.type === "thinking") {
                updateSession(sessionId, { status: "thinking" });
              } else if (data.type === "response" && data.content) {
                fullContent += data.content;
                useChatStore.getState().applyStreamEvent(
                  sessionId,
                  { type: "response", content: data.content },
                  currentMsgId
                );
              } else if (data.type === "done") {
                useChatStore.getState().addMessage(sessionId, {
                  id: currentMsgId,
                  sessionId,
                  role: "assistant",
                  content: fullContent,
                  timestamp: new Date().toISOString(),
                  status: "complete",
                });
                updateSession(sessionId, { status: "idle" });
              } else if (data.type === "error") {
                updateSession(sessionId, { status: "error" });
              }
            } catch {
              // skip
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          updateSession(sessionId, { status: "error" });
        }
      } finally {
        sendingRef.current = false;
        abortRef.current = null;
        useChatStore.getState().applyStreamEvent(sessionId, { type: "done" }, "");
      }
    },
    [addMessage, startStreaming, updateSession]
  );

  const interrupt = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { sendAndStream, interrupt };
}
