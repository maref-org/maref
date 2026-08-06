import { create } from "zustand";

export interface TerminalTab {
  id: string;
  label: string;
  isAgentOwned: boolean;
  sessionId?: string;
}

interface TerminalState {
  tabs: TerminalTab[];
  activeTabId: string | null;
  output: Record<string, string[]>;
  isConnected: boolean;
  terminalSendFn: ((data: string) => void) | null;

  addTab: (tab: TerminalTab) => void;
  removeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  appendOutput: (tabId: string, text: string) => void;
  clearOutput: (tabId: string) => void;
  setConnected: (connected: boolean) => void;
  registerTerminalSend: (fn: ((data: string) => void) | null) => void;
}

export const useTerminalStore = create<TerminalState>((set) => ({
  tabs: [{ id: "default", label: "zsh", isAgentOwned: false }],
  activeTabId: "default",
  output: { default: [] },
  isConnected: false,
  terminalSendFn: null,

  addTab: (tab) =>
    set((state) => ({
      tabs: [...state.tabs, tab],
      output: { ...state.output, [tab.id]: [] },
      activeTabId: tab.id,
    })),

  removeTab: (id) =>
    set((state) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [id]: _removed, ...rest } = state.output;
      const tabs = state.tabs.filter((t) => t.id !== id);
      return {
        tabs,
        output: rest,
        activeTabId: state.activeTabId === id ? tabs[0]?.id ?? null : state.activeTabId,
      };
    }),

  setActiveTab: (id) => set({ activeTabId: id }),

  appendOutput: (tabId, text) =>
    set((state) => ({
      output: {
        ...state.output,
        [tabId]: [...(state.output[tabId] ?? []), text],
      },
    })),

  clearOutput: (tabId) =>
    set((state) => ({
      output: { ...state.output, [tabId]: [] },
    })),

  setConnected: (isConnected) => set({ isConnected }),

  registerTerminalSend: (fn) => set({ terminalSendFn: fn }),
}));
