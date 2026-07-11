import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Sidebar, type MarefSection } from "@/components/layout/Sidebar";
import { HomeDashboard } from "@/components/layout/HomeDashboard";
import { SettingsView } from "@/components/views/SettingsView";
import { AutomationView } from "@/components/views/AutomationView";
import {
  DesktopAgentView,
  AuditLogView,
  DriftDetectionView,
  AnomalyMonitorView,
  TrustScoreView,
  FormalVerificationView,
} from "@/components/views/MarefViews";
import { GovernanceView } from "@/components/views/GovernanceView";
import { SkillsPanel } from "@/components/views/SkillsPanel";

const SECTION_VIEWS: Record<MarefSection, React.ComponentType> = {
  home: HomeDashboard,
  desktop: DesktopAgentView,
  governance: GovernanceView,
  audit: AuditLogView,
  drift: DriftDetectionView,
  anomaly: AnomalyMonitorView,
  trust: TrustScoreView,
  formal: FormalVerificationView,
  skills: SkillsPanel,
  automation: AutomationView,
  settings: SettingsView,
};

function withProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function assert(desc: string, fn: () => void | Promise<void>) {
  return it(desc, async () => {
    try {
      await fn();
    } catch (e) {
      console.error(`  FAIL: ${desc} — ${e instanceof Error ? e.message : String(e)}`);
      throw e;
    }
  });
}

describe("GUI Smoke Tests", () => {
  describe("MarefSection Views", () => {
    const sections = Object.keys(SECTION_VIEWS) as MarefSection[];
    for (const section of sections) {
      assert(`renders section: ${section}`, () => {
        const View = SECTION_VIEWS[section];
        withProviders(<View />);
      });
    }
  });

  describe("Sidebar Navigation", () => {
    assert("renders sidebar with navigation items", () => {
      withProviders(
        <Sidebar activeSection="home" onSectionChange={() => {}} />
      );
      expect(screen.getByText("首页仪表盘")).toBeInTheDocument();
      expect(screen.getByText("桌面 Agent")).toBeInTheDocument();
    });
  });
});