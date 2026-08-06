import { create } from "zustand";
import { api } from "@/api/client";

export interface ParetoFrontData {
  dimensions: string[];
  current_scores: Record<string, number>;
  recommended_weights: Record<string, number>;
  rationale: string;
}

export interface CrossEffect {
  source_dim: string;
  target_dim: string;
  effect_size: number;
  direction: string;
  confidence: number;
}

export interface AdaptiveAllocation {
  target: string;
  rounds_allocated: number;
  success_rate: number;
  current_weight: number;
}

interface RsiState {
  paretoFront: ParetoFrontData | null;
  crossEffects: CrossEffect[];
  adaptiveAllocation: AdaptiveAllocation[];
  loading: boolean;
  error: string | null;

  fetchParetoFront: () => Promise<void>;
  fetchCrossEffects: () => Promise<void>;
  fetchAdaptiveAllocation: () => Promise<void>;
  refreshAll: () => Promise<void>;
}

export const useRsiStore = create<RsiState>((set) => ({
  paretoFront: null,
  crossEffects: [],
  adaptiveAllocation: [],
  loading: false,
  error: null,

  fetchParetoFront: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.getParetoFront();
      set({ paretoFront: res });
    } catch (err) {
      set({ error: (err as Error).message });
    } finally {
      set({ loading: false });
    }
  },

  fetchCrossEffects: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.getCrossEffects();
      set({ crossEffects: res });
    } catch (err) {
      set({ error: (err as Error).message });
    } finally {
      set({ loading: false });
    }
  },

  fetchAdaptiveAllocation: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.getAdaptiveAllocation();
      set({ adaptiveAllocation: res });
    } catch (err) {
      set({ error: (err as Error).message });
    } finally {
      set({ loading: false });
    }
  },

  refreshAll: async () => {
    set({ loading: true, error: null });
    try {
      const [pareto, effects, allocation] = await Promise.all([
        api.getParetoFront(),
        api.getCrossEffects(),
        api.getAdaptiveAllocation(),
      ]);
      set({
        paretoFront: pareto,
        crossEffects: effects,
        adaptiveAllocation: allocation,
      });
    } catch (err) {
      set({ error: (err as Error).message });
    } finally {
      set({ loading: false });
    }
  },
}));