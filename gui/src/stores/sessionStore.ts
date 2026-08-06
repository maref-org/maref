import { create } from "zustand";
import type { Session, ExecutionMode, ProviderId } from "@/types";

const AGENT_COLORS = [
  "#6366f1", "#22c55e", "#f59e0b", "#3b82f6", "#ef4444",
  "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#06b6d4",
];

function hashColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0;
  }
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length];
}

interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  isLoading: boolean;
  agentColorMap: Record<string, string>;

  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  removeSession: (id: string) => void;
  setActiveSession: (id: string | null) => void;
  updateSession: (id: string, updates: Partial<Session>) => void;
  updateSessionMode: (id: string, mode: ExecutionMode) => void;
  updateSessionProvider: (id: string, provider: ProviderId, model: string) => void;
  setLoading: (loading: boolean) => void;
  getActiveSession: () => Session | undefined;
  getAgentColor: (sessionId: string) => string;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  isLoading: false,
  agentColorMap: {},

  setSessions: (sessions) =>
    set((state) => {
      const agentColorMap = { ...state.agentColorMap };
      for (const s of sessions) {
        if (!agentColorMap[s.id]) {
          agentColorMap[s.id] = hashColor(s.id);
        }
      }
      return { sessions, agentColorMap };
    }),

  addSession: (session) =>
    set((state) => ({
      sessions: [...state.sessions, session],
      activeSessionId: state.activeSessionId ?? session.id,
      agentColorMap: {
        ...state.agentColorMap,
        [session.id]: state.agentColorMap[session.id] ?? hashColor(session.id),
      },
    })),

  removeSession: (id) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== id),
      activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
    })),

  setActiveSession: (id) => set({ activeSessionId: id }),

  updateSession: (id, updates) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, ...updates } : s)),
    })),

  updateSessionMode: (id, mode) =>
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === id ? { ...s, mode } : s)),
    })),

  updateSessionProvider: (id, provider, model) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, provider, model } : s
      ),
    })),

  setLoading: (isLoading) => set({ isLoading }),

  getActiveSession: () => {
    const { sessions, activeSessionId } = get();
    return sessions.find((s) => s.id === activeSessionId);
  },

  getAgentColor: (sessionId: string) => {
    const { agentColorMap } = get();
    return agentColorMap[sessionId] ?? AGENT_COLORS[0];
  },
}));
