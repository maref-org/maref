import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { injectNonce } from "./middleware/csp";
import { initWebVitals, setVitalReportHandler } from "./lib/web-vitals";
import "./lib/i18n";
import "./index.css";
import App from "./App";

(function restoreFontSize() {
  try {
    const saved = localStorage.getItem("maref_font_size");
    if (saved) {
      document.documentElement.style.fontSize = `${saved}px`;
    }
  } catch {
    // ignore storage errors
  }
})();

// 注入 CSP nonce
injectNonce();

// 启动真实用户性能监控
setVitalReportHandler((metrics) => {
  console.log("[Web Vitals]", metrics);
  fetch("/api/vitals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metrics),
  }).catch(() => {});
});
initWebVitals();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary
      onError={(error, info) => {
        console.error("[MAREF] Fatal render error:", error, info);
      }}
    >
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
);