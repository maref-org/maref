import { create } from "zustand";
import { api } from "@/api/client";

export interface TimelineEvent {
  type: "version" | "gate" | "conflict" | "heal" | "alert";
  label: string;
  detail: string;
  timestamp: string;
}

export interface DaySnapshot {
  day: number;
  date: string;
  avgScore: number;
  adoptionRate: number;
  dimensions: Record<string, number>;
  events: TimelineEvent[];
  selfHealCount: number;
  selfHealSuccesses: number;
  version?: string;
}

interface EvolutionState {
  daySnapshots: DaySnapshot[];
  loading: boolean;
  error: string | null;

  fetchEvolution: () => Promise<void>;
}

export const useEvolutionStore = create<EvolutionState>((set) => ({
  daySnapshots: [],
  loading: false,
  error: null,

  fetchEvolution: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.getEvolutionTimeline();
      set({ daySnapshots: res });
    } catch (err) {
      set({ error: (err as Error).message });
    } finally {
      set({ loading: false });
    }
  },
}));
