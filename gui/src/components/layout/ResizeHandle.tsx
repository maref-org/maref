import { cn } from "@/lib/utils";

interface Props {
  onMouseDown: (e: React.MouseEvent) => void;
  direction?: "horizontal" | "vertical";
}

export function ResizeHandle({ onMouseDown, direction = "horizontal" }: Props) {
  return (
    <div
      onMouseDown={onMouseDown}
      role="separator"
      aria-orientation={direction === "horizontal" ? "vertical" : "horizontal"}
      tabIndex={0}
      className={cn(
        "group relative z-10 flex-shrink-0 transition-colors",
        direction === "horizontal"
          ? "w-1.5 cursor-col-resize hover:bg-maref-accent/40 active:bg-maref-accent/60"
          : "h-1.5 cursor-row-resize hover:bg-maref-accent/40 active:bg-maref-accent/60"
      )}
    >
      <div
        className={cn(
          "absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity",
          direction === "horizontal"
            ? "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-8 w-0.5 rounded-full bg-maref-accent/50"
            : "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-0.5 rounded-full bg-maref-accent/50"
        )}
      />
    </div>
  );
}
