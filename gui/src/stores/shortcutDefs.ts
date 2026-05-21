import type { Shortcut } from "@/stores/shortcuts";

export function createShortcuts(actions: ShortcutActions): Shortcut[] {
  return [
    {
      key: "k",
      mod: "ctrl",
      description: "命令面板",
      category: "global",
      action: () => {},
    },
    {
      key: "b",
      mod: "ctrl",
      description: "切换侧边栏",
      category: "global",
      action: actions.toggleSidebar,
    },
    {
      key: "`",
      mod: "ctrl",
      description: "切换终端",
      category: "global",
      action: actions.toggleTerminal,
    },
    {
      key: "j",
      mod: "ctrl",
      description: "切换主题",
      category: "global",
      action: actions.toggleTheme,
    },

    {
      key: "n",
      mod: "ctrl",
      description: "新建 Agent 会话",
      category: "navigation",
      action: actions.newSession,
    },
    {
      key: "1",
      mod: "ctrl",
      description: "首页面板",
      category: "navigation",
      action: actions.goHome,
    },
    {
      key: "2",
      mod: "ctrl",
      description: "桌面 Agent",
      category: "navigation",
      action: () => actions.goToSection("desktop"),
    },
    {
      key: "3",
      mod: "ctrl",
      description: "治理看板",
      category: "navigation",
      action: () => actions.goToSection("governance"),
    },
    {
      key: "4",
      mod: "ctrl",
      description: "审计日志",
      category: "navigation",
      action: () => actions.goToSection("audit"),
    },
    {
      key: "5",
      mod: "ctrl",
      description: "漂移检测",
      category: "navigation",
      action: () => actions.goToSection("drift"),
    },
    {
      key: "6",
      mod: "ctrl",
      description: "异常监控",
      category: "navigation",
      action: () => actions.goToSection("anomaly"),
    },
    {
      key: "7",
      mod: "ctrl",
      description: "信任评分",
      category: "navigation",
      action: () => actions.goToSection("trust"),
    },
    {
      key: "8",
      mod: "ctrl",
      description: "形式验证",
      category: "navigation",
      action: () => actions.goToSection("formal"),
    },

    {
      key: "w",
      mod: "ctrl",
      description: "关闭当前会话",
      category: "navigation",
      action: actions.closeSession,
    },

    {
      key: "Enter",
      mod: "none",
      description: "发送消息",
      category: "chat",
      action: () => {},
    },
    {
      key: "Enter",
      mod: "ctrl",
      description: "换行输入",
      category: "chat",
      action: () => {},
    },
    {
      key: "l",
      mod: "ctrl",
      description: "清空对话",
      category: "chat",
      action: actions.clearChat,
    },
    {
      key: "i",
      mod: "ctrl",
      description: "打断 Agent 执行",
      category: "chat",
      action: actions.interruptAgent,
    },

    {
      key: "t",
      mod: "ctrl+shift",
      description: "新建终端",
      category: "terminal",
      action: actions.newTerminal,
    },
    {
      key: "c",
      mod: "ctrl",
      description: "中断终端命令 (Ctrl+C)",
      category: "terminal",
      action: actions.terminalBreak,
    },

    {
      key: "g",
      mod: "ctrl+shift",
      description: "治理状态快照",
      category: "maref",
      action: actions.governanceSnapshot,
    },
    {
      key: "d",
      mod: "ctrl+shift",
      description: "桌面 Agent 演示",
      category: "maref",
      action: actions.desktopDemo,
    },
    {
      key: "a",
      mod: "ctrl+shift",
      description: "打开审计日志",
      category: "maref",
      action: () => actions.goToSection("audit"),
    },
    {
      key: "s",
      mod: "ctrl+shift",
      description: "Sidecar 服务器状态",
      category: "maref",
      action: actions.sidecarStatus,
    },
    {
      key: "r",
      mod: "ctrl+shift",
      description: "漂移检测报告",
      category: "maref",
      action: actions.driftCheck,
    },
  ];
}

export interface ShortcutActions {
  toggleSidebar: () => void;
  toggleTerminal: () => void;
  toggleTheme: () => void;
  newSession: () => void;
  goHome: () => void;
  goToSection: (section: string) => void;
  closeSession: () => void;
  clearChat: () => void;
  interruptAgent: () => void;
  newTerminal: () => void;
  terminalBreak: () => void;
  governanceSnapshot: () => void;
  desktopDemo: () => void;
  sidecarStatus: () => void;
  driftCheck: () => void;
}