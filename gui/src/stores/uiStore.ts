import { create } from "zustand";
import type { TabView } from "@/types";

function readLocalStorage(key: string, fallback: boolean): boolean {
  try {
    const val = localStorage.getItem(key);
    if (val === null) return fallback;
    return val === "true";
  } catch {
    return fallback;
  }
}

function writeLocalStorage(key: string, val: boolean) {
  try {
    localStorage.setItem(key, String(val));
  } catch {
    // ignore
  }
}

interface UIState {
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  terminalVisible: boolean;
  terminalWidth: number;
  theme: "dark" | "light";
  activeTab: TabView;
  hasSeenOnboarding: boolean;
  toastMessage: string | null;

  setSidebarWidth: (width: number) => void;
  toggleSidebar: () => void;
  toggleTerminal: () => void;
  setTerminalWidth: (width: number) => void;
  toggleTheme: () => void;
  setActiveTab: (tab: TabView) => void;
  completeOnboarding: () => void;
  showToast: (msg: string) => void;
  clearToast: () => void;
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarWidth: 240,
  sidebarCollapsed: false,
  terminalVisible: true,
  terminalWidth: 400,
  theme: "light",
  activeTab: "chat",
  hasSeenOnboarding: readLocalStorage("maref_onboarding_done", false),
  toastMessage: null,

  setSidebarWidth: (width) =>
    set({
      sidebarWidth: width <= 60 ? 60 : Math.max(180, Math.min(width, 400)),
      sidebarCollapsed: width <= 60,
    }),

  toggleSidebar: () => {
    const { sidebarCollapsed } = get();
    if (sidebarCollapsed) {
      set({ sidebarCollapsed: false, sidebarWidth: 240 });
    } else {
      set({ sidebarCollapsed: true, sidebarWidth: 60 });
    }
  },

  toggleTerminal: () => set((s) => ({ terminalVisible: !s.terminalVisible })),

  setTerminalWidth: (width) =>
    set({ terminalWidth: Math.max(280, Math.min(width, 480)) }),

  toggleTheme: () =>
    set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),

  setActiveTab: (tab) => set({ activeTab: tab }),

  completeOnboarding: () => {
    writeLocalStorage("maref_onboarding_done", true);
    set({ hasSeenOnboarding: true });
  },

  showToast: (msg) => {
    set({ toastMessage: msg });
    setTimeout(() => {
      const { toastMessage } = useUIStore.getState();
      if (toastMessage === msg) {
        set({ toastMessage: null });
      }
    }, 3000);
  },

  clearToast: () => set({ toastMessage: null }),
}));
