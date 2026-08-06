const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "textarea:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

let announceTimer: ReturnType<typeof setTimeout> | null = null;

export function announce(message: string, priority: "polite" | "assertive" = "polite") {
  const id = "maref-announce";
  let region = document.getElementById(id) as HTMLDivElement | null;

  if (!region) {
    region = document.createElement("div");
    region.id = id;
    region.setAttribute("role", "status");
    region.setAttribute("aria-live", priority);
    region.className = "sr-only";
    document.body.appendChild(region);
  }

  if (announceTimer) clearTimeout(announceTimer);

  announceTimer = setTimeout(() => {
    if (region) {
      region.textContent = "";
      requestAnimationFrame(() => {
        region!.textContent = message;
      });
    }
  }, 50);
}

export function createFocusTrap(container: HTMLElement) {
  const previouslyFocused = document.activeElement as HTMLElement | null;

  function getFocusableElements(): HTMLElement[] {
    return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  }

  function focusFirst() {
    const elements = getFocusableElements();
    if (elements.length > 0) {
      elements[0].focus();
    } else {
      container.focus();
    }
  }

  function focusLast() {
    const elements = getFocusableElements();
    if (elements.length > 0) {
      elements[elements.length - 1].focus();
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key !== "Tab") return;

    const elements = getFocusableElements();
    if (elements.length === 0) {
      e.preventDefault();
      return;
    }

    const first = elements[0];
    const last = elements[elements.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  function activate() {
    container.addEventListener("keydown", handleKeyDown);
    focusFirst();
  }

  function deactivate() {
    container.removeEventListener("keydown", handleKeyDown);
    if (previouslyFocused && typeof previouslyFocused.focus === "function") {
      previouslyFocused.focus();
    }
  }

  return { activate, deactivate, focusFirst, focusLast };
}

export function handleListNavigation(
  e: KeyboardEvent,
  items: HTMLElement[],
  currentIndex: number
): number {
  switch (e.key) {
    case "ArrowDown":
      e.preventDefault();
      currentIndex = Math.min(currentIndex + 1, items.length - 1);
      break;
    case "ArrowUp":
      e.preventDefault();
      currentIndex = Math.max(currentIndex - 1, 0);
      break;
    case "Home":
      e.preventDefault();
      currentIndex = 0;
      break;
    case "End":
      e.preventDefault();
      currentIndex = items.length - 1;
      break;
    default:
      return currentIndex;
  }

  items[currentIndex]?.focus();
  return currentIndex;
}
