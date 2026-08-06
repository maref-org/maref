import { create } from "zustand";
import type { Message, StreamEvent } from "@/types";

interface ChatState {
  messages: Record<string, Message[]>;
  streamingContent: Record<string, string>;
  isStreaming: Record<string, boolean>;

  addMessage: (sessionId: string, message: Message) => void;
  setMessages: (sessionId: string, messages: Message[]) => void;
  appendToStream: (sessionId: string, content: string) => void;
  startStreaming: (sessionId: string) => void;
  applyStreamEvent: (sessionId: string, event: StreamEvent, msgId: string) => void;
  clearMessages: (sessionId: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: {},
  streamingContent: {},
  isStreaming: {},

  addMessage: (sessionId, message) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [sessionId]: [...(state.messages[sessionId] ?? []), message],
      },
    })),

  setMessages: (sessionId, messages) =>
    set((state) => ({
      messages: { ...state.messages, [sessionId]: messages },
    })),

  appendToStream: (sessionId, content) =>
    set((state) => ({
      streamingContent: {
        ...state.streamingContent,
        [sessionId]: (state.streamingContent[sessionId] ?? "") + content,
      },
    })),

  startStreaming: (sessionId) =>
    set((state) => ({
      isStreaming: { ...state.isStreaming, [sessionId]: true },
      streamingContent: { ...state.streamingContent, [sessionId]: "" },
    })),

  applyStreamEvent: (sessionId, event, msgId) =>
    set((state) => {
      const msgs = state.messages[sessionId] ?? [];
      const messages = msgs.map((m) => {
        if (m.id !== msgId) return m;
        if (event.type === "response" && event.content) {
          return { ...m, content: m.content + event.content };
        }
        if (event.type === "done") {
          return { ...m, status: "complete" as const };
        }
        return m;
      });
      const isStreaming =
        event.type === "done"
          ? { ...state.isStreaming, [sessionId]: false }
          : state.isStreaming;
      const streamingContent =
        event.type === "done"
          ? { ...state.streamingContent, [sessionId]: "" }
          : state.streamingContent;
      return { messages: { ...state.messages, [sessionId]: messages }, isStreaming, streamingContent };
    }),

  clearMessages: (sessionId) =>
    set((state) => ({
      messages: { ...state.messages, [sessionId]: [] },
      streamingContent: { ...state.streamingContent, [sessionId]: "" },
      isStreaming: { ...state.isStreaming, [sessionId]: false },
    })),
}));
