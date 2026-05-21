import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Sidebar, type MarefSection } from "@/components/layout/Sidebar";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatPanel } from "@/components/layout/ChatPanel";
import { HomeDashboard } from "@/components/layout/HomeDashboard";
import { SettingsView } from "@/components/views/SettingsView";
import { AutomationView } from "@/components/views/AutomationView";
import { FileTree } from "@/components/sidebar/FileTree";
import { MarefDrawer } from "@/components/layout/MarefDrawer";
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

let passed = 0;
let failed = 0;

function assert(desc: string, fn: () => void | Promise<void>) {
  return it(desc, async () => {
    try {
      await fn();
      passed++;
    } catch (e) {
      failed++;
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
      expect(screen.getByText("MAREF 功能")).toBeInTheDocument();
    });

    assert("sidebar buttons have onClick handlers", () => {
      let lastSection = "";
      withProviders(
        <Sidebar activeSection="home" onSectionChange={(s) => { lastSection = s; }} />
      );
      const desktopBtn = screen.getByText("首页仪表盘");
      fireEvent.click(desktopBtn);
      expect(lastSection).toBe("home");
    });
  });

  describe("Chat", () => {
    assert("renders chat input with send button", () => {
      withProviders(<ChatInput sessionId="test-sess" />);
      expect(screen.getByPlaceholderText(/发送消息/)).toBeInTheDocument();
    });

    assert("renders chat panel", () => {
      withProviders(<ChatPanel />);
    });
  });

  describe("Settings", () => {
    assert("renders settings with all sections", () => {
      withProviders(<SettingsView />);
      expect(screen.getByText("外观主题")).toBeInTheDocument();
      expect(screen.getByText("字体大小")).toBeInTheDocument();
      expect(screen.getByText("语言")).toBeInTheDocument();
      expect(screen.getByText("快捷键参考")).toBeInTheDocument();
      expect(screen.getByText("关于")).toBeInTheDocument();
    });

    assert("theme toggle works", () => {
      withProviders(<SettingsView />);
      const lightBtn = screen.getByText("浅色");
      const darkBtn = screen.getByText("深色");
      expect(lightBtn).toBeInTheDocument();
      expect(darkBtn).toBeInTheDocument();
      fireEvent.click(darkBtn);
    });

    assert("font size slider renders", () => {
      withProviders(<SettingsView />);
      const slider = screen.getByRole("slider");
      expect(slider).toBeInTheDocument();
      fireEvent.change(slider, { target: { value: "18" } });
    });
  });

  describe("Automation", () => {
    assert("renders automation with 3 tabs", () => {
      withProviders(<AutomationView />);
      expect(screen.getByText("已配置")).toBeInTheDocument();
      expect(screen.getByText("执行历史")).toBeInTheDocument();
      expect(screen.getByText("任务模板")).toBeInTheDocument();
    });

    assert("switches between tabs", () => {
      withProviders(<AutomationView />);
      fireEvent.click(screen.getByText("任务模板"));
      expect(screen.getByText("选择一个模板快速创建自动化任务")).toBeInTheDocument();
    });
  });

  describe("FileTree", () => {
    assert("renders file tree", () => {
      withProviders(<FileTree />);
      expect(screen.getByPlaceholderText(/搜索文件/)).toBeInTheDocument();
    });
  });

  describe("MarefDrawer", () => {
    const drawerSections: MarefSection[] = [
      "home", "desktop", "governance", "audit",
      "drift", "anomaly", "trust", "formal",
    ];

    for (const section of drawerSections) {
      assert(`renders drawer for: ${section}`, () => {
        withProviders(
          <MarefDrawer section={section} onClose={() => {}} />
        );
      });
    }
  });

  afterAll(() => {
    const total = passed + failed;
    console.log(`\n📊 Results: ${passed}/${total} passed, ${failed}/${total} failed`);
    expect(failed).toBe(0);
  });
});
