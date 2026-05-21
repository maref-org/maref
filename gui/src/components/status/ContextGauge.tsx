import { useMemo } from "react";

interface Props {
  percent: number;
  isStreaming: boolean;
}

export function ContextGauge({ percent, isStreaming }: Props) {
  const color = useMemo(() => {
    if (percent > 80) return "bg-maref-danger";
    if (percent > 50) return "bg-maref-warning";
    return "bg-maref-info";
  }, [percent]);

  return (
    <span className="flex items-center gap-1.5">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${isStreaming ? "animate-pulse" : ""} ${color}`}
      />
      <span>{percent}% 上下文</span>
    </span>
  );
}