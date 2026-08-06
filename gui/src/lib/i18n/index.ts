import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zhCN from "./zh-CN.json";
import enUS from "./en-US.json";

function detectLanguage(): string {
  try {
    const stored = localStorage.getItem("maref_lang");
    if (stored === "zh-CN" || stored === "en-US") return stored;
  } catch {
    // ignore storage errors
  }
  const browser = navigator.language;
  if (browser.startsWith("zh")) return "zh-CN";
  return "en-US";
}

i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": { translation: zhCN },
    "en-US": { translation: enUS },
  },
  lng: detectLanguage(),
  fallbackLng: "en-US",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
