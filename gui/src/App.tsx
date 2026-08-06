import { useEffect, useState, useCallback, useMemo } from "react";
import { Sidebar, type MarefSection } from "@/components/layout/Sidebar";
import { ChatPanel } from "@/components/layout/ChatPanel";
import { TerminalPanel } from "@/components/layout/TerminalPanel";
import { StatusBar } from "@/components/layout/StatusBar";
import { GovernanceBanner } from "@/components/status/GovernanceBanner";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { MarefDrawer } from "@/components/layout/MarefDrawer";
import { TabBar } from "@/components/layout/TabBar";
import { BrowserView } from "@/components/views/BrowserView";
import { GitView } from "@/components/views/GitView";
import { GovernanceView } from "@/components/views/GovernanceView";
import { HomeDashboard } from "@/components/layout/HomeDashboard";
import { ImmunityDashboard } from "@/components/immunity/ImmunityDashboard";
import { SettingsView } from "@/components/views/SettingsView";
import { WelcomeFlow } from "@/components/onboarding/WelcomeFlow";
import { SkillsPanel } from "@/components/views/SkillsPanel";
import { AutomationView } from "@/components/views/AutomationView";
import TaskPanelView from "@/components/views/TaskPanelView";
import { ToolPanelView } from "@/components/tools";
import { HITLView } from "@/components/views/HITLView";
import { FederationView } from "@/components/views/FederationView";
import {
  DesktopAgentView,
  AuditLogView,
  DriftDetectionView,
  AnomalyMonitorView,
  TrustScoreView,
  FormalVerificationView,
  GuardrailsView,
  ErrorBudgetView,
  EvolutionTimeline,
} from "@/components/views/MarefViews";
import { useUIStore } from "@/stores/uiStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useTerminalStore } from "@/stores/terminalStore";
import { useSessions } from "@/hooks/useSession";
import { useKeyboard } from "@/hooks/useKeyboard";
import { createShortcuts } from "@/stores/shortcutDefs";
import { detectBackend, api, getBackendMode, checkBackendHealth } from "@/api/client";
import type { Shortcut } from "@/stores/shortcuts";
import type { TabView } from "@/types";

const SECTION_VIEWS: Record<MarefSection, React.ComponentType> = {
  home: HomeDashboard,
  desktop: DesktopAgentView,
  governance: GovernanceView,
  immunity: ImmunityDashboard,
  hitl: HITLView,
  audit: AuditLogView,
  drift: DriftDetectionView,
  anomaly: AnomalyMonitorView,
  trust: TrustScoreView,
  formal: FormalVerificationView,
  rsi: EvolutionTimeline,
  guardrails: GuardrailsView,
  error_budget: ErrorBudgetView,
  federation: FederationView,
  skills: SkillsPanel,
  automation: AutomationView,
  tasks: TaskPanelView,
  tools: ToolPanelView,
  settings: SettingsView,
};

function MainContent({ activeTab }: { activeTab: TabView }) {
  switch (activeTab) {
    case "chat":
      return <ChatPanel />;
    case "browser":
      return <BrowserView />;
    case "terminal":
      return <TerminalPanel />;
    case "git":
      return <GitView />;
    case "governance":
      return <GovernanceView />;
  }
}

export default function App() {
  const [activeSection, setActiveSection] = useState<MarefSection>("home");
  const [drawerSection, setDrawerSection] = useState<MarefSection | null>(null);
  const {
    sidebarWidth,
    sidebarCollapsed,
    terminalVisible,
    terminalWidth,
    theme,
    activeTab,
    hasSeenOnboarding,
    toastMessage,
    setSidebarWidth,
    setTerminalWidth,
    toggleSidebar,
    toggleTerminal,
    toggleTheme,
    setActiveTab,
    showToast,
    clearToast,
  } = useUIStore();

  const {
    activeSessionId,
    addSession,
    removeSession,
  } = useSessionStore();

  const { clearMessages } = useChatStore();
  const { addTab: addTerminalTab, tabs: terminalTabs } = useTerminalStore();

  useSessions();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  useEffect(() => {
    detectBackend();
  }, []);

  const handleNewSession = useCallback(() => {
    addSession({
      id: `sess-${Date.now()}`,
      title: "新 Agent",
      mode: "agent",
      provider: "bailian",
      model: "deepseek-v4-pro",
      contextPercent: 0,
      status: "idle",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
  }, [addSession]);

  const handleCloseSession = useCallback(() => {
    if (activeSessionId) {
      removeSession(activeSessionId);
    }
  }, [activeSessionId, removeSession]);

  const shortcutActions = useMemo(
    () => ({
      toggleSidebar,
      toggleTerminal,
      toggleTheme,
      newSession: handleNewSession,
      goHome: () => {
        setActiveSection("home");
      },
      goToSection: (section: string) => {
        setActiveSection(section as MarefSection);
      },
      closeSession: handleCloseSession,
      clearChat: () => activeSessionId && clearMessages(activeSessionId),
      interruptAgent: () => {
        if (!activeSessionId) return;
        api.interrupt(activeSessionId);
        useSessionStore.getState().updateSession(activeSessionId, { status: "idle" });
        useChatStore.getState().applyStreamEvent(activeSessionId, { type: "done" }, "");
        showToast("Agent 已中断");
      },
      newTerminal: () =>
        addTerminalTab({
          id: `term-${Date.now()}`,
          label: `终端 #${terminalTabs.length + 1}`,
          isAgentOwned: false,
        }),
      terminalBreak: () => {
        const sendFn = useTerminalStore.getState().terminalSendFn;
        if (sendFn) {
          sendFn("\x03");
        } else {
          showToast("无活跃终端");
        }
      },
      governanceSnapshot: () => setActiveSection("governance"),
      desktopDemo: () => setActiveSection("desktop"),
      sidecarStatus: async () => {
        const start = performance.now();
        const healthy = await checkBackendHealth();
        const latency = Math.round(performance.now() - start);
        const mode = getBackendMode();
        const status = healthy ? "已连接" : mode === "mock" ? "模拟模式" : "未连接";
        showToast(`Backend ${status} · ${latency}ms`);
      },
      driftCheck: () => setActiveSection("drift"),
    }),
    [
      toggleSidebar,
      toggleTerminal,
      toggleTheme,
      handleNewSession,
      handleCloseSession,
      activeSessionId,
      clearMessages,
      addTerminalTab,
      showToast,
      terminalTabs.length,
    ]
  );

  const shortcuts: Shortcut[] = useMemo(
    () => createShortcuts(shortcutActions),
    [shortcutActions]
  );

  const { showPalette, setShowPalette } = useKeyboard({
    shortcuts,
    enabled: true,
  });

  const displaySidebarWidth = sidebarCollapsed ? 60 : sidebarWidth;
  const isTerminalTab = activeTab === "terminal";
  const isHome = activeSection === "home";
  const SectionView = SECTION_VIEWS[activeSection];

  if (!hasSeenOnboarding) {
    return (
      <WelcomeFlow onComplete={() => {}} />
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-maref-bg text-maref-text">
      <GovernanceBanner />
      <div className="flex flex-1 overflow-hidden">
        <div
          className="flex-shrink-0 overflow-hidden transition-[width] duration-75"
          style={{ width: displaySidebarWidth }}
        >
          <Sidebar
            activeSection={activeSection}
            onSectionChange={(section) => {
              setActiveSection(section);
              setDrawerSection(null);
            }}
          />
        </div>

        <ResizeHandle
          onMouseDown={(e) => {
            const startX = e.clientX;
            const startW = displaySidebarWidth;
            const onMove = (ev: MouseEvent) => {
              setSidebarWidth(startW + (ev.clientX - startX));
            };
            const onUp = () => {
              document.removeEventListener("mousemove", onMove);
              document.removeEventListener("mouseup", onUp);
              document.body.style.cursor = "";
              document.body.style.userSelect = "";
            };
            e.preventDefault();
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
          }}
        />

        <div className="flex flex-1 min-w-0 overflow-hidden">
          <div className="flex flex-1 min-w-[320px] flex-col">
            {isHome && <TabBar activeTab={activeTab} onTabChange={(tab) => { setActiveTab(tab); setActiveSection("home"); }} />}
            <div className="flex-1 min-h-0 overflow-hidden">
              {isHome ? (
                <MainContent activeTab={activeTab} />
              ) : (
                <div className="h-full overflow-y-auto">
                  <SectionView />
                </div>
              )}
            </div>
          </div>

          {!isTerminalTab && terminalVisible && (
            <>
              <ResizeHandle
                onMouseDown={(e) => {
                  const startX = e.clientX;
                  const startW = terminalWidth;
                  const onMove = (ev: MouseEvent) => {
                    setTerminalWidth(startW - (ev.clientX - startX));
                  };
                  const onUp = () => {
                    document.removeEventListener("mousemove", onMove);
                    document.removeEventListener("mouseup", onUp);
                    document.body.style.cursor = "";
                    document.body.style.userSelect = "";
                  };
                  e.preventDefault();
                  document.body.style.cursor = "col-resize";
                  document.body.style.userSelect = "none";
                  document.addEventListener("mousemove", onMove);
                  document.addEventListener("mouseup", onUp);
                }}
              />

              <div
                className="flex-shrink-0 overflow-hidden transition-[width] duration-75"
                style={{ width: terminalWidth }}
              >
                <TerminalPanel />
              </div>
            </>
          )}
        </div>
      </div>

      <MarefDrawer
        section={drawerSection}
        onClose={() => setDrawerSection(null)}
      />

      <CommandPalette
        shortcuts={shortcuts}
        isOpen={showPalette}
        onClose={() => setShowPalette(false)}
      />

      <StatusBar />

      {toastMessage && (
        <div
          className="fixed bottom-10 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-maref-surface border border-maref-border px-4 py-2 text-sm text-maref-text shadow-lg animate-[fadeIn_200ms_ease-out] cursor-pointer"
          onClick={clearToast}
        >
          {toastMessage}
        </div>
      )}
    </div>
  );
}
