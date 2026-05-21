import { useEffect, useState, useCallback } from "react";
import type { Shortcut } from "@/stores/shortcuts";
import { matchShortcut } from "@/stores/shortcuts";

interface UseKeyboardOptions {
  shortcuts: Shortcut[];
  enabled?: boolean;
}

export function useKeyboard({ shortcuts, enabled = true }: UseKeyboardOptions) {
  const [showPalette, setShowPalette] = useState(false);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;

      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowPalette((prev) => !prev);
        return;
      }

      if (e.key === "Escape") {
        setShowPalette(false);
        return;
      }

      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      for (const shortcut of shortcuts) {
        if (matchShortcut(e, shortcut)) {
          if (isInput && shortcut.category !== "global") continue;
          e.preventDefault();
          shortcut.action();
          return;
        }
      }
    },
    [shortcuts, enabled]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return {
    showPalette,
    setShowPalette,
    closePalette: () => setShowPalette(false),
  };
}