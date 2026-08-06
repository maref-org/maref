import { create } from "zustand";
import { api } from "@/api/client";

interface GuardrailsState {
  totalChecks: number;
  allowRate: number;
  denyRate: number;
  auditRate: number;
  riskScores: { agentId: string; score: number }[];
  openCircuitBreakers: number;
  activeDenials: number;
  recentEvents: { verdict: string; gate: string; duration: number; timestamp: string }[];
  loading: boolean;
  error: string | null;
  pollingInterval: ReturnType<typeof setInterval> | null;

  fetchStats: () => Promise<void>;
  fetchRecentEvents: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}

export const useGuardrailsStore = create<GuardrailsState>((set, get) => ({
  totalChecks: 0,
  allowRate: 0,
  denyRate: 0,
  auditRate: 0,
  riskScores: [],
  openCircuitBreakers: 0,
  activeDenials: 0,
  recentEvents: [],
  loading: false,
  error: null,
  pollingInterval: null,

  fetchStats: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.getGuardrailsStats();
      set({
        totalChecks: res.total_checks,
        allowRate: res.allow_rate,
        denyRate: res.deny_rate,
        auditRate: res.audit_rate,
        riskScores: res.risk_scores.map((rs) => ({
          agentId: rs.agent_id,
          score: rs.score,
        })),
        openCircuitBreakers: res.open_circuit_breakers,
        activeDenials: res.active_denials,
        loading: false,
      });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  fetchRecentEvents: async () => {
    try {
      const res = await api.getGuardrailsEvents(50);
      set({
        recentEvents: res.events.map((e) => ({
          verdict: e.verdict,
          gate: e.gate,
          duration: e.duration,
          timestamp: new Date(e.timestamp * 1000).toLocaleString(),
        })),
        error: null,
      });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  startPolling: (intervalMs = 3000) => {
    const existing = get().pollingInterval;
    if (existing) clearInterval(existing);
    const id = setInterval(() => {
      get().fetchStats();
      get().fetchRecentEvents();
    }, intervalMs);
    set({ pollingInterval: id });
  },

  stopPolling: () => {
    const existing = get().pollingInterval;
    if (existing) {
      clearInterval(existing);
      set({ pollingInterval: null });
    }
  },
}));
