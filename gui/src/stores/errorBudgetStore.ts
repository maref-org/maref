import { create } from "zustand";
import { api } from "@/api/client";

export interface ErrorEvent {
  id: string;
  severity: string;
  source: string;
  message: string;
  timestamp: string;
}

interface ErrorBudgetState {
  sloTarget: number;
  budgetRemaining: number;
  burnRate: number;
  totalErrors: number;
  recentErrors: ErrorEvent[];
  alerts: Array<{
    level: string;
    burn_rate: number;
    threshold: number;
    triggered: boolean;
  }>;
  loading: boolean;
  error: string | null;
  fetchData: () => Promise<void>;
}

export const useErrorBudgetStore = create<ErrorBudgetState>((set) => ({
  sloTarget: 0.995,
  budgetRemaining: 100,
  burnRate: 0,
  totalErrors: 0,
  recentErrors: [],
  alerts: [],
  loading: false,
  error: null,

  fetchData: async () => {
    set({ loading: true, error: null });
    try {
      const res = await api.getErrorBudget();
      set({
        sloTarget: res.slo_target,
        budgetRemaining: res.budget.remaining_pct,
        burnRate: res.burn_rate,
        totalErrors: res.total_errors ?? 0,
        recentErrors: res.recent_errors ?? [],
        alerts: res.alerts ?? [],
      });
    } catch (err) {
      set({ error: (err as Error).message });
    } finally {
      set({ loading: false });
    }
  },
}));
