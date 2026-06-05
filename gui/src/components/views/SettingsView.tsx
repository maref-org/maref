import { useState } from "react";
import { Sun, Moon, Type, Globe, Keyboard, Info, Heart } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";
import { PetBuddy } from "@/components/views/PetBuddy";

export function SettingsView() {
  const { theme, toggleTheme } = useUIStore();
  const [fontSize, setFontSize] = useState(() => {
    try {
      return parseInt(localStorage.getItem("maref_font_size") || "14", 10);
    } catch {
      return 14;
    }
  });

  const setTheme = (t: "light" | "dark") => {
    if (theme !== t) toggleTheme();
  };

  const handleFontSizeChange = (size: number) => {
    setFontSize(size);
  };

  const commitFontSize = (size: number) => {
    try {
      localStorage.setItem("maref_font_size", String(size));
    } catch {
      // ignore storage errors
    }
    document.documentElement.style.fontSize = `${size}px`;
  };

  return (
    <div className="overflow-y-auto p-6">
      <h2 className="text-lg font-semibold text-maref-text mb-6">设置</h2>

      <section className="mb-8 rounded-xl border-2 border-purple-200 dark:border-purple-800 bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-950/20 dark:to-indigo-950/20 p-5 max-w-xl">
        <div className="flex items-center gap-2 mb-4">
          <Heart className="h-4 w-4 text-purple-500" />
          <h3 className="text-sm font-semibold text-maref-text">修行伙伴</h3>
        </div>
        <PetBuddy />
      </section>

      <div className="space-y-6 max-w-xl">
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Sun className="h-4 w-4 text-maref-text-muted" />
            <h3 className="text-sm font-medium text-maref-text">外观主题</h3>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setTheme("light")}
              className={cn(
                "flex items-center gap-2 rounded-lg border-2 px-4 py-2.5 text-sm transition-colors",
                theme === "light"
                  ? "border-maref-accent bg-maref-surface-alt text-maref-text"
                  : "border-maref-border text-maref-text-muted hover:border-maref-text-muted"
              )}
            >
              <Sun className="h-4 w-4" />
              浅色
            </button>
            <button
              onClick={() => setTheme("dark")}
              className={cn(
                "flex items-center gap-2 rounded-lg border-2 px-4 py-2.5 text-sm transition-colors",
                theme === "dark"
                  ? "border-maref-accent bg-maref-surface-alt text-maref-text"
                  : "border-maref-border text-maref-text-muted hover:border-maref-text-muted"
              )}
            >
              <Moon className="h-4 w-4" />
              深色
            </button>
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3">
            <Type className="h-4 w-4 text-maref-text-muted" />
            <h3 className="text-sm font-medium text-maref-text">字体大小</h3>
          </div>
          <div className="flex items-center gap-3 max-w-xs">
            <span className="text-xs text-maref-text-muted">A</span>
            <input
              type="range"
              min="11"
              max="24"
              value={fontSize}
              onChange={(e) => handleFontSizeChange(parseInt(e.target.value, 10))}
              onMouseUp={(e) => commitFontSize(parseInt((e.target as HTMLInputElement).value, 10))}
              onTouchEnd={(e) => commitFontSize(parseInt((e.target as HTMLInputElement).value, 10))}
              className="flex-1 h-1.5 rounded-full appearance-none bg-maref-border cursor-pointer accent-maref-accent"
            />
            <span className="text-sm text-maref-text-muted">A</span>
            <span className="text-xs text-maref-text-muted tabular-nums w-9 text-right">{fontSize}px</span>
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3">
            <Globe className="h-4 w-4 text-maref-text-muted" />
            <h3 className="text-sm font-medium text-maref-text">语言</h3>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                try { localStorage.setItem("maref_language", "zh"); } catch { /* ignore */ }
              }}
              className={cn(
                "rounded-lg border-2 px-4 py-2 text-sm transition-colors",
                "border-maref-accent bg-maref-surface-alt text-maref-text"
              )}
            >
              中文
            </button>
            <button
              onClick={() => {
                try { localStorage.setItem("maref_language", "en"); } catch { /* ignore */ }
              }}
              className={cn(
                "rounded-lg border-2 px-4 py-2 text-sm transition-colors",
                "border-maref-border text-maref-text-muted cursor-not-allowed opacity-50"
              )}
            >
              English
            </button>
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3">
            <Keyboard className="h-4 w-4 text-maref-text-muted" />
            <h3 className="text-sm font-medium text-maref-text">快捷键参考</h3>
          </div>
          <div className="grid grid-cols-2 gap-1.5 max-w-lg">
            {[
              { key: "⌃K", desc: "命令面板" },
              { key: "⌃B", desc: "切换侧边栏" },
              { key: "⌃`", desc: "切换终端" },
              { key: "⌃J", desc: "切换主题" },
              { key: "⌃N", desc: "新建会话" },
              { key: "⌃1-⌃8", desc: "切换功能看板" },
              { key: "⌃I", desc: "中断 Agent" },
              { key: "⌃⇧T", desc: "新建终端 Tab" },
              { key: "⌃⇧S", desc: "Sidecar 状态" },
              { key: "Enter", desc: "发送消息" },
              { key: "Shift+Enter", desc: "换行" },
            ].map(({ key, desc }) => (
              <div key={key} className="flex items-center gap-2 text-xs">
                <kbd className="rounded bg-maref-surface-alt border border-maref-border px-1.5 py-0.5 font-mono text-[11px] text-maref-text-muted min-w-[3.5rem] text-center">
                  {key}
                </kbd>
                <span className="text-maref-text-muted truncate">{desc}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3">
            <Info className="h-4 w-4 text-maref-text-muted" />
            <h3 className="text-sm font-medium text-maref-text">关于</h3>
          </div>
          <div className="text-xs text-maref-text-muted space-y-0.5">
            <p>MAREF v0.23.0-rc</p>
            <p>Multi-Agent Recursive Evolution Framework</p>
            <p>Apache 2.0 License</p>
          </div>
        </section>
      </div>
    </div>
  );
}
