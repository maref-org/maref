export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 px-14 py-2">
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-maref-accent animate-[pulse_1.5s_ease-in-out_infinite]" />
        <span
          className="h-2 w-2 rounded-full bg-maref-accent animate-[pulse_1.5s_ease-in-out_infinite]"
          style={{ animationDelay: "0.2s" }}
        />
        <span
          className="h-2 w-2 rounded-full bg-maref-accent animate-[pulse_1.5s_ease-in-out_infinite]"
          style={{ animationDelay: "0.4s" }}
        />
      </div>
      <span className="text-xs text-maref-text-muted">思考中…</span>
    </div>
  );
}