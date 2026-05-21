import type { KeyboardEvent as ReactKeyboardEvent } from "react";

export interface Shortcut {
  key: string;
  mod: "none" | "ctrl" | "ctrl+shift" | "alt" | "meta";
  description: string;
  category: ShortcutCategory;
  action: () => void;
}

export type ShortcutCategory =
  | "global"
  | "navigation"
  | "chat"
  | "terminal"
  | "maref";

const modKey = (e: KeyboardEvent | ReactKeyboardEvent): string => {
  const parts: string[] = [];
  if (e.metaKey || e.ctrlKey) parts.push("ctrl");
  if (e.shiftKey) parts.push("ctrl+shift");
  if (e.altKey && !e.metaKey && !e.ctrlKey) parts.push("alt");
  return parts.length > 0 ? parts.join("+") : "none";
};

export function matchShortcut(
  e: KeyboardEvent | ReactKeyboardEvent,
  shortcut: Shortcut
): boolean {
  const actualMod = modKey(e);
  if (shortcut.mod === "ctrl+shift") {
    return (
      (e.metaKey || e.ctrlKey) &&
      e.shiftKey &&
      !e.altKey &&
      (e.key.toLowerCase() === shortcut.key.toLowerCase() ||
        e.code === `Key${shortcut.key.toUpperCase()}`)
    );
  }
  if (actualMod !== shortcut.mod) return false;
  if (shortcut.key === "`" || shortcut.key === "/") {
    return e.key === shortcut.key || e.code === "Backquote";
  }
  return (
    e.key.toLowerCase() === shortcut.key.toLowerCase() ||
    e.code === `Key${shortcut.key.toUpperCase()}`
  );
}

export function formatShortcutLabel(key: string, mod: Shortcut["mod"]): string {
  const prefix = mod === "ctrl" ? "⌃" : mod === "ctrl+shift" ? "⌃⇧" : mod === "alt" ? "⌥" : mod === "meta" ? "⌘" : "";
  return `${prefix}${mod !== "none" ? "＋" : ""}${key.toUpperCase()}`;
}