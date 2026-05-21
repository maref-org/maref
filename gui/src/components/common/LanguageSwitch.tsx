import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

const LANGUAGES = [
  { code: "zh-CN", label: "中文" },
  { code: "en-US", label: "English" },
] as const;

export function LanguageSwitch({ className }: { className?: string }) {
  const { i18n } = useTranslation();

  const handleChange = (code: string) => {
    i18n.changeLanguage(code);
    try {
      localStorage.setItem("maref_lang", code);
    } catch {}
  };

  return (
    <div
      className={cn(
        "flex items-center gap-1 rounded-md border border-maref-border bg-maref-surface p-0.5",
        className
      )}
      role="radiogroup"
      aria-label="Language"
    >
      {LANGUAGES.map((lang) => {
        const active = i18n.language === lang.code;
        return (
          <button
            key={lang.code}
            onClick={() => handleChange(lang.code)}
            className={cn(
              "rounded px-2 py-1 text-xs font-medium transition-colors",
              active
                ? "bg-maref-accent text-white"
                : "text-maref-text-muted hover:text-maref-text"
            )}
            role="radio"
            aria-checked={active}
          >
            {lang.label}
          </button>
        );
      })}
    </div>
  );
}
