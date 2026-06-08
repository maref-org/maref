import { create } from "zustand";
import { api } from "@/api/client";
import type {
  AuditEventItem,
  AuditStats,
  GovernanceSnapshot,
  AgentHealthInfo,
} from "@/types";

interface AuditState {
  events: AuditEventItem[];
  stats: AuditStats | null;
  snapshot: GovernanceSnapshot | null;
  agents: AgentHealthInfo[];
  integrity: { intact: boolean; tampered: number } | null;
  loading: boolean;
  error: string | null;
  pollingId: ReturnType<typeof setInterval> | null;
  lastFetched: number | null;

  fetchEvents: (params?: {
    category?: string;
    severity?: string;
    limit?: number;
  }) => Promise<void>;
  fetchStats: () => Promise<void>;
  fetchIntegrity: () => Promise<void>;
  setSnapshot: (snapshot: GovernanceSnapshot) => void;
  setAgents: (agents: AgentHealthInfo[]) => void;
  updateAgentStatus: (id: string, status: AgentHealthInfo["status"]) => void;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}

function deriveSnapshot(
  stats: AuditStats | null,
  agents: AgentHealthInfo[]
): GovernanceSnapshot {
  const haltedCount = agents.filter((a) => a.status === "halted").length;
  const faultyCount = agents.filter((a) => a.status === "faulty").length;

  let circuitBreaker = "CLOSED";
  if (haltedCount > 0) circuitBreaker = "OPEN";
  else if (faultyCount > 0) circuitBreaker = "HALF_OPEN";

  const entropy = Math.min(
    10,
    Math.ceil(
      ((stats?.by_severity?.ERROR ?? 0) +
        (stats?.by_severity?.FATAL ?? 0) * 3) /
        Math.max(1, (stats?.total_events ?? 1)) *
        10
    )
  );

  return {
    state_machine: haltedCount > 0 ? "HALT" : "OBSERVE",
    circuit_breaker: circuitBreaker,
    entropy,
    oscillation_rate: (stats?.by_severity?.WARN ?? 0) / Math.max(1, (stats?.total_events ?? 1)) * 100,
    active_sessions: agents.filter((a) => a.status === "healthy" || a.status === "idle").length,
    halted: haltedCount > 0,
  };
}

export const useAuditStore = create<AuditState>((set, get) => ({
  events: [],
  stats: null,
  snapshot: null,
  agents: [],
  integrity: null,
  loading: false,
  error: null,
  pollingId: null,
  lastFetched: null,

  fetchEvents: async (params) => {
    set({ loading: true, error: null });
    try {
      const res = await api.auditEvents({
        ...params,
        limit: params?.limit ?? 20,
      });
      set({
        events: res.events,
        loading: false,
        lastFetched: Date.now(),
      });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  fetchStats: async () => {
    try {
      const res = await api.auditStats();
      const { agents } = get();
      const snapshot = deriveSnapshot(res, agents);
      set({ stats: res, snapshot });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  fetchIntegrity: async () => {
    try {
      const res = await api.auditVerify();
      set({
        integrity: {
          intact: res.integrity_intact,
          tampered: res.tampered_entries.length,
        },
      });
    } catch {
      // silent fail for integrity check
    }
  },

  setSnapshot: (snapshot) => set({ snapshot }),

  setAgents: (agents) => {
    const { stats } = get();
    const snapshot = deriveSnapshot(stats, agents);
    set({ agents, snapshot });
  },

  updateAgentStatus: (id, status) =>
    set((state) => {
      const agents = state.agents.map((a) =>
        a.id === id ? { ...a, status } : a
      );
      const snapshot = deriveSnapshot(state.stats, agents);
      return { agents, snapshot };
    }),

  startPolling: (intervalMs = 5000) => {
    const existing = get().pollingId;
    if (existing) clearInterval(existing);

    get().fetchStats();
    get().fetchEvents();
    get().fetchIntegrity();

    const id = setInterval(() => {
      get().fetchStats();
      get().fetchEvents();
      get().fetchIntegrity();
    }, intervalMs);
    set({ pollingId: id });
  },

  stopPolling: () => {
    const existing = get().pollingId;
    if (existing) {
      clearInterval(existing);
      set({ pollingId: null });
    }
  },
}));