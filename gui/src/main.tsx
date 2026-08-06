import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { injectNonce } from "./middleware/csp";
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
