import { create } from "zustand";
import { api } from "@/api/client";
import type { HITLEvent, HITLStats } from "@/types";

interface HITLState {
  pendingEvents: HITLEvent[];
  historyEvents: HITLEvent[];
  stats: HITLStats | null;
  loading: boolean;
  error: string | null;
  pollingInterval: ReturnType<typeof setInterval> | null;

  fetchPending: (tier?: string) => Promise<void>;
  fetchHistory: (limit?: number, offset?: number) => Promise<void>;
  fetchStats: () => Promise<void>;
  approveEvent: (eventId: string) => Promise<boolean>;
  denyEvent: (eventId: string) => Promise<boolean>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}

export const useHITLStore = create<HITLState>((set, get) => ({
  pendingEvents: [],
  historyEvents: [],
  stats: null,
  loading: false,
  error: null,
  pollingInterval: null,

  fetchPending: async (tier?: string) => {
    set({ loading: true, error: null });
    try {
      const res = await api.hitlPending(tier);
      set({ pendingEvents: res.events, loading: false });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  fetchHistory: async (limit = 50, offset = 0) => {
    set({ loading: true, error: null });
    try {
      const res = await api.hitlHistory(limit, offset);
      set({ historyEvents: res.events, loading: false });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  fetchStats: async () => {
    try {
      const res = await api.hitlStats();
      set({ stats: res.stats as unknown as HITLStats });
    } catch {
      // silent fail for stats
    }
  },

  approveEvent: async (eventId: string) => {
    try {
      const res = await api.hitlApprove(eventId);
      if (res.approved) {
        set((s) => ({
          pendingEvents: s.pendingEvents.filter((e) => e.event_id !== eventId),
        }));
      }
      return res.approved;
    } catch (err) {
      set({ error: (err as Error).message });
      return false;
    }
  },

  denyEvent: async (eventId: string) => {
    try {
      const res = await api.hitlDeny(eventId);
      if (res.cancelled) {
        set((s) => ({
          pendingEvents: s.pendingEvents.filter((e) => e.event_id !== eventId),
        }));
      }
      return res.cancelled;
    } catch (err) {
      set({ error: (err as Error).message });
      return false;
    }
  },

  startPolling: (intervalMs = 2000) => {
    const existing = get().pollingInterval;
    if (existing) clearInterval(existing);
    const id = setInterval(() => {
      get().fetchPending();
      get().fetchStats();
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
