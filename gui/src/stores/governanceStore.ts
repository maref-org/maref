import { create } from "zustand";
import { api } from "@/api/client";

interface GovernanceState {
  state: string;
  entropy: number;
  entropyMax: number;
  transitionCount: number;
  circuitBreaker: string;
  transitions: Array<{ from: string; to: string; reason: string; time: string; valid: boolean }>;
  cbEvents: Array<{ from: string; to: string; reason: string; time: string }>;
  oscEvents: Array<{ stage: string; desc: string; time: string }>;
  loading: boolean;
  error: string | null;

  fetchState: () => Promise<void>;
  fetchTransitions: () => Promise<void>;
  fetchCbEvents: () => Promise<void>;
  fetchOscEvents: () => Promise<void>;
  refreshAll: () => Promise<void>;
}

export const useGovernanceStore = create<GovernanceState>((set, get) => ({
  state: "INIT",
  entropy: 0,
  entropyMax: 10,
  transitionCount: 0,
  circuitBreaker: "CLOSED",
  transitions: [],
  cbEvents: [],
  oscEvents: [],
  loading: false,
  error: null,

  fetchState: async () => {
    try {
      const res = await api.getGovernanceState();
      set({
        state: res.state,
        entropy: res.entropy,
        entropyMax: res.entropy_max,
        transitionCount: res.transition_count,
        circuitBreaker: res.circuit_breaker,
      });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  fetchTransitions: async () => {
    try {
      const res = await api.getGovernanceTransitions();
      set({ transitions: res.transitions });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  fetchCbEvents: async () => {
    try {
      const res = await api.getCircuitBreakerEvents();
      set({ cbEvents: res.events });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  fetchOscEvents: async () => {
    try {
      const res = await api.getOscillationEvents();
      set({ oscEvents: res.events });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  refreshAll: async () => {
    set({ loading: true, error: null });
    try {
      await Promise.all([
        get().fetchState(),
        get().fetchTransitions(),
        get().fetchCbEvents(),
        get().fetchOscEvents(),
      ]);
    } finally {
      set({ loading: false });
    }
  },
}));
