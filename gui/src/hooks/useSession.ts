import { useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, getBackendMode, connectSSE } from "@/api/client";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import type { ExecutionMode, ProviderId } from "@/types";

export function useSessions() {
  const { setSessions } = useSessionStore();
  return useQuery({
    queryKey: ["sessions"],
    queryFn: async () => {
      try {
        const data = await api.getSessions();
        setSessions(data.sessions);
        return data;
      } catch {
        return { sessions: [] };
      }
    },
    staleTime: 10_000,
  });
}

export function useSession(id: string) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => api.getSession(id),
    enabled: !!id,
  });
}

export function useMessages(sessionId: string) {
  const { setMessages } = useChatStore();
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: async () => {
      try {
        const data = await api.getMessages(sessionId);
        setMessages(sessionId, data.messages);
        return data;
      } catch {
        return { messages: [] };
      }
    },
    enabled: !!sessionId,
    staleTime: 5_000,
  });
}

export function useCreateSession() {
  const { addSession } = useSessionStore();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      title: string;
      mode: ExecutionMode;
      provider: ProviderId;
      model: string;
    }) => api.createSession(body),
    onSuccess: (session) => {
      addSession(session);
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}

export function useTasks() {
  return useQuery({
    queryKey: ["tasks"],
    queryFn: async () => {
      try {
        return await api.getTasks();
      } catch {
        return { tasks: [] };
      }
    },
    staleTime: 10_000,
  });
}

export function useSSEConnection(sessionId: string | null) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const connectRef = useRef<(() => void) | null>(null);
  const { appendToStream, startStreaming, addMessage } = useChatStore();

  const connect = useCallback(() => {
    if (!sessionId) return;
    if (getBackendMode() !== "real") return;

    eventSourceRef.current?.close();
    const es = connectSSE(`/sessions/${sessionId}/stream`);
    eventSourceRef.current = es;

    es.addEventListener("message", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "response" && data.content) {
          appendToStream(sessionId, data.content as string);
        }
      } catch {
        appendToStream(sessionId, e.data);
      }
    });

    es.addEventListener("tool_call", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const msgId = `msg-${Date.now()}`;
        addMessage(sessionId, {
          id: msgId,
          sessionId,
          role: "tool",
          content: "",
          timestamp: new Date().toISOString(),
          toolCalls: [data],
        });
      } catch {
        // ignore parse errors
      }
    });

    es.addEventListener("done", () => {
      addMessage(sessionId, {
        id: `msg-${Date.now()}`,
        sessionId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        status: "complete",
      });
      eventSourceRef.current?.close();
      retriesRef.current = 0;
    });

    es.addEventListener("error", () => {
      if (es.readyState === EventSource.CLOSED) {
        retriesRef.current = 0;
        return;
      }
      es.close();
    });

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      const backoff = Math.min(1000 * 2 ** retriesRef.current, 30000);
      retriesRef.current += 1;
      timerRef.current = setTimeout(() => {
        connectRef.current?.();
      }, backoff);
    };

    retriesRef.current = 0;
  }, [sessionId, appendToStream, addMessage]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    if (getBackendMode() !== "real" || !sessionId) return;
    startStreaming(sessionId);
    connect();

    return () => {
      clearTimeout(timerRef.current);
      eventSourceRef.current?.close();
    };
  }, [sessionId, connect, startStreaming]);
}
