import { useState, useMemo, useCallback } from "react";
import { Command, Search } from "lucide-react";
import type { Shortcut, ShortcutCategory } from "@/stores/shortcuts";
import { formatShortcutLabel } from "@/stores/shortcuts";
import { cn } from "@/lib/utils";

interface Props {
  shortcuts: Shortcut[];
  isOpen: boolean;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<ShortcutCategory, string> = {
  global: "全局",
  navigation: "导航",
  chat: "对话",
  terminal: "终端",
  maref: "MAREF",
};

export function CommandPalette({ shortcuts, isOpen, onClose }: Props) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query.trim()) return shortcuts;
    const q = query.toLowerCase();
    return shortcuts.filter(
      (s) =>
        s.description.toLowerCase().includes(q) ||
        s.key.toLowerCase().includes(q) ||
        CATEGORY_LABELS[s.category].includes(q)
    );
  }, [shortcuts, query]);

  const grouped = useMemo(() => {
    const map = new Map<ShortcutCategory, Shortcut[]>();
    for (const s of filtered) {
      const arr = map.get(s.category) ?? [];
      arr.push(s);
      map.set(s.category, arr);
    }
    return Array.from(map.entries());
  }, [filtered]);

  const handleSelect = useCallback(
    (s: Shortcut) => {
      s.action();
      onClose();
    },
    [onClose]
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} />
      <div className="relative z-10 w-[560px] max-h-[480px] rounded-xl border border-maref-border bg-maref-surface shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-center gap-2 border-b border-maref-border px-4 py-3">
          <Search className="h-4 w-4 text-maref-text-muted flex-shrink-0" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索命令或快捷键…"
            className="flex-1 bg-transparent text-sm text-maref-text placeholder-maref-text-muted outline-none"
          />
          <kbd className="flex items-center gap-1 rounded border border-maref-border px-1.5 py-0.5 text-[10px] text-maref-text-muted">
            <span>Esc</span>
          </kbd>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {grouped.map(([category, items]) => (
            <div key={category} className="mb-1">
              <div className="px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
                {CATEGORY_LABELS[category]}
              </div>
              {items.map((s) => (
                <button
                  key={`${s.category}-${s.key}-${s.description}`}
                  onClick={() => handleSelect(s)}
                  className={cn(
                    "flex w-full items-center gap-3 px-4 py-2 text-sm transition-colors",
                    "hover:bg-maref-surface-alt text-left"
                  )}
                >
                  <Command className="h-3.5 w-3.5 text-maref-accent flex-shrink-0" />
                  <span className="flex-1 text-maref-text">{s.description}</span>
                  <kbd className="rounded bg-maref-bg border border-maref-border px-1.5 py-0.5 text-[10px] text-maref-text-muted font-mono whitespace-nowrap">
                    {formatShortcutLabel(s.key, s.mod)}
                  </kbd>
                </button>
              ))}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-maref-text-muted">
              未找到匹配的命令
            </div>
          )}
        </div>

        <div className="border-t border-maref-border px-4 py-2 text-[10px] text-maref-text-muted flex items-center gap-3">
          <span>↑↓ 导航</span>
          <span>↵ 执行</span>
          <span>Esc 关闭</span>
        </div>
      </div>
    </div>
  );
}