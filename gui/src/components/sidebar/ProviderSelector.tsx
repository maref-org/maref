import { useProviders } from "@/hooks/useProviders";
import { ChevronDown } from "lucide-react";
import type { ProviderId } from "@/types";

interface Props {
  selectedProvider: ProviderId;
  selectedModel: string;
  onSelect: (provider: ProviderId, model: string) => void;
}

export function ProviderSelector({
  selectedProvider,
  selectedModel,
  onSelect,
}: Props) {
  const { data } = useProviders();
  const providers = data?.providers ?? [];

  if (providers.length === 0) {
    return (
      <div className="px-3 py-2 text-[11px] text-maref-text-muted">
        No providers
      </div>
    );
  }

  return (
    <div className="space-y-2 px-3 py-2">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-maref-text-muted">
        Model Provider
      </span>
      {providers.map((p) => (
        <div key={p.id} className="space-y-1">
          <button
            onClick={() => onSelect(p.id, p.defaultModel)}
            className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors ${
              selectedProvider === p.id
                ? "bg-maref-surface-alt text-maref-accent"
                : "text-maref-text-muted hover:text-maref-text"
            }`}
          >
            <ChevronDown className="h-3 w-3" />
            {p.label}
          </button>
          {selectedProvider === p.id && (
            <div className="ml-5 space-y-0.5">
              {p.models.map((model) => (
                <button
                  key={model}
                  onClick={() => onSelect(p.id, model)}
                  className={`block w-full rounded px-2 py-1 text-left text-xs transition-colors ${
                    selectedModel === model
                      ? "text-maref-accent bg-maref-surface-alt/50"
                      : "text-maref-text-muted hover:text-maref-text"
                  }`}
                >
                  {model}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
