import { useEffect, useRef, useState, useCallback } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { X, Plus, Settings, Wifi, WifiOff, ChevronDown } from "lucide-react";
import { useTerminalStore } from "@/stores/terminalStore";
import { useUIStore } from "@/stores/uiStore";
import { useSessionStore } from "@/stores/sessionStore";

interface TerminalSettings {
  fontSize: number;
  fontFamily: string;
  cursorStyle: "block" | "underline" | "bar";
  cursorBlink: boolean;
  theme: "dark" | "light";
}

const FONT_FAMILIES = [
  "JetBrains Mono",
  "Fira Code",
  "Source Code Pro",
  "Menlo",
];

const DARK_THEME = {
  background: "#0d0f15",
  foreground: "#e1e4ea",
  cursor: "#6366f1",
  selectionBackground: "#6366f144",
};

const LIGHT_THEME = {
  background: "#f5f5f5",
  foreground: "#1a1a2e",
  cursor: "#6366f1",
  selectionBackground: "#6366f144",
};

const STORAGE_KEY = "maref-terminal-settings";

function loadSettings(): TerminalSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return {
    fontSize: 13,
    fontFamily: "JetBrains Mono",
    cursorStyle: "block",
    cursorBlink: true,
    theme: "dark",
  };
}

function saveSettings(settings: TerminalSettings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {}
}

export function TerminalPanel() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const { tabs, activeTabId, setActiveTab, addTab, removeTab } =
    useTerminalStore();
  const { toggleTerminal } = useUIStore();
  const { activeSessionId } = useSessionStore();
  const connectedRef = useRef(false);

  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<TerminalSettings>(loadSettings);

  const applySettings = useCallback((s: TerminalSettings) => {
    const term = xtermRef.current;
    if (!term) return;
    term.options.fontSize = s.fontSize;
    term.options.fontFamily = `"${s.fontFamily}", "Fira Code", ui-monospace, monospace`;
    term.options.cursorStyle = s.cursorStyle;
    term.options.cursorBlink = s.cursorBlink;
    term.options.theme = s.theme === "dark" ? DARK_THEME : LIGHT_THEME;
  }, []);

  const updateSetting = useCallback(
    <K extends keyof TerminalSettings>(key: K, value: TerminalSettings[K]) => {
      setSettings((prev) => {
        const next = { ...prev, [key]: value };
        saveSettings(next);
        return next;
      });
    },
    []
  );

  useEffect(() => {
    applySettings(settings);
  }, [settings, applySettings]);

  useEffect(() => {
    if (!terminalRef.current) return;

    const term = new Terminal({
      cursorBlink: settings.cursorBlink,
      fontSize: settings.fontSize,
      fontFamily: `"${settings.fontFamily}", "Fira Code", ui-monospace, monospace`,
      cursorStyle: settings.cursorStyle,
      theme: settings.theme === "dark" ? DARK_THEME : LIGHT_THEME,
      allowProposedApi: true,
    });

    const fit = new FitAddon();
    const webLinks = new WebLinksAddon();
    term.loadAddon(fit);
    term.loadAddon(webLinks);
    term.open(terminalRef.current);
    fit.fit();

    term.writeln("\x1b[32m┌─ MAREF Terminal ──────────────────────────┐\x1b[0m");
    term.writeln("\x1b[32m│ 等待后端连接…                              │\x1b[0m");
    term.writeln("\x1b[32m└────────────────────────────────────────────┘\x1b[0m\r\n");

    xtermRef.current = term;
    fitAddonRef.current = fit;

    const handleResize = () => {
      fit.fit();
      if (term.rows && term.cols) {
        wsRef.current?.send(
          JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols })
        );
      }
    };
    window.addEventListener("resize", handleResize);

    function connectWS() {
      const sid = activeSessionId ?? "default";
      const ws = new WebSocket(`ws://localhost:8000/api/sessions/${sid}/terminal`);
      wsRef.current = ws;

      ws.onopen = () => {
        connectedRef.current = true;
        term.clear();
        term.write("\x1b[?25h");
        if (term.rows && term.cols) {
          ws.send(JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols }));
        }
      };

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          const arr = new Uint8Array(event.data);
          term.write(arr);
        } else {
          term.write(event.data);
        }
      };

      ws.onclose = () => {
        connectedRef.current = false;
        term.write("\r\n\x1b[33m[ 连接断开 — 5秒后重连 ]\x1b[0m\r\n");
        setTimeout(connectWS, 5000);
      };

      ws.onerror = () => {
        connectedRef.current = false;
      };
    }

    term.onData((data) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(data);
      }
    });

    setTimeout(connectWS, 300);

    return () => {
      window.removeEventListener("resize", handleResize);
      wsRef.current?.close();
      term.dispose();
    };
  }, [activeSessionId]);

  const handleNewTerminal = () => {
    const id = `term-${Date.now()}`;
    addTab({ id, label: `终端 #${tabs.length + 1}`, isAgentOwned: false });
  };

  return (
    <div className="flex h-full flex-col border-l border-maref-border bg-maref-bg">
      <div className="flex items-center border-b border-maref-border bg-maref-surface px-2">
        <div className="flex flex-1 items-center gap-0.5 overflow-x-auto">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex cursor-pointer items-center gap-1.5 border-b-2 px-3 py-2 text-xs transition-colors ${
                activeTabId === tab.id
                  ? "border-maref-accent text-maref-text"
                  : "border-transparent text-maref-text-muted hover:text-maref-text"
              }`}
            >
              <span>{tab.label}</span>
              {!tab.isAgentOwned && tabs.length > 1 && (
                <X
                  className="h-3 w-3 hover:text-maref-danger"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeTab(tab.id);
                  }}
                />
              )}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-0.5 px-1 relative">
          <span className="text-maref-text-muted">
            {connectedRef.current ? (
              <Wifi className="h-3.5 w-3.5 text-maref-success" />
            ) : (
              <WifiOff className="h-3.5 w-3.5 text-maref-danger" />
            )}
          </span>
          <button
            onClick={handleNewTerminal}
            className="rounded p-1 text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="rounded p-1 text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt transition-colors"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={toggleTerminal}
            className="rounded p-1 text-maref-text-muted hover:text-maref-text hover:bg-maref-surface-alt transition-colors ml-1"
          >
            <X className="h-3.5 w-3.5" />
          </button>

          {showSettings && (
            <div className="absolute right-0 top-full mt-1 w-72 rounded-lg border border-maref-border bg-maref-surface shadow-xl z-50 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-maref-text">终端设置</h4>
                <button
                  onClick={() => setShowSettings(false)}
                  className="rounded p-0.5 text-maref-text-muted hover:text-maref-text"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text-maref-text-muted">
                  字号: {settings.fontSize}px
                </label>
                <input
                  type="range"
                  min={12}
                  max={24}
                  value={settings.fontSize}
                  onChange={(e) => updateSetting("fontSize", Number(e.target.value))}
                  className="w-full h-1.5 rounded-full appearance-none bg-maref-surface-alt accent-maref-accent cursor-pointer"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text-maref-text-muted">字体</label>
                <div className="relative">
                  <select
                    value={settings.fontFamily}
                    onChange={(e) => updateSetting("fontFamily", e.target.value)}
                    className="w-full appearance-none rounded-md border border-maref-border bg-maref-surface-alt px-2.5 py-1.5 pr-7 text-xs text-maref-text outline-none focus:border-maref-accent/50 transition-colors cursor-pointer"
                  >
                    {FONT_FAMILIES.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-maref-text-muted pointer-events-none" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text-maref-text-muted">光标样式</label>
                <div className="flex gap-1.5">
                  {(["block", "underline", "bar"] as const).map((style) => (
                    <button
                      key={style}
                      onClick={() => updateSetting("cursorStyle", style)}
                      className={`flex-1 rounded-md border px-2 py-1.5 text-[10px] transition-colors ${
                        settings.cursorStyle === style
                          ? "border-maref-accent/40 bg-maref-accent/10 text-maref-accent"
                          : "border-maref-border bg-maref-surface-alt text-maref-text-muted hover:text-maref-text"
                      }`}
                    >
                      {style === "block" ? "块" : style === "underline" ? "下划线" : "竖线"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[10px] text-maref-text-muted">光标闪烁</span>
                <button
                  onClick={() => updateSetting("cursorBlink", !settings.cursorBlink)}
                  className={`relative inline-flex h-4 w-8 items-center rounded-full transition-colors ${
                    settings.cursorBlink ? "bg-maref-accent" : "bg-maref-surface-alt"
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${
                      settings.cursorBlink ? "translate-x-[18px]" : "translate-x-[2px]"
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[10px] text-maref-text-muted">主题</span>
                <button
                  onClick={() => updateSetting("theme", settings.theme === "dark" ? "light" : "dark")}
                  className={`relative inline-flex h-4 w-8 items-center rounded-full transition-colors ${
                    settings.theme === "light" ? "bg-maref-accent" : "bg-maref-surface-alt"
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${
                      settings.theme === "light" ? "translate-x-[18px]" : "translate-x-[2px]"
                    }`}
                  />
                </button>
              </div>
              <span className="block text-[10px] text-maref-text-muted">
                {settings.theme === "dark" ? "深色" : "浅色"}
              </span>
            </div>
          )}
        </div>
      </div>
      <div ref={terminalRef} className="flex-1 overflow-hidden p-1" />
    </div>
  );
}
