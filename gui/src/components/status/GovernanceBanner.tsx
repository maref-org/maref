import { useEffect, useState } from "react";

export function GovernanceBanner() {
  const [offline, setOffline] = useState(false);
  const [backendMode, setBackendMode] = useState<"checking" | "real" | "mock">("checking");

  useEffect(() => {
    const onOffline = () => {
      setOffline(true);
      setBackendMode("mock");
    };
    const onOnline = () => {
      setOffline(false);
      setBackendMode("real");
    };
    const onBackendMode = (e: CustomEvent) => {
      setBackendMode(e.detail?.mode ?? "mock");
      setOffline(e.detail?.mode === "mock");
    };

    window.addEventListener("governance:offline", onOffline);
    window.addEventListener("governance:online", onOnline);
    window.addEventListener("governance:backend-mode", onBackendMode as EventListener);

    return () => {
      window.removeEventListener("governance:offline", onOffline);
      window.removeEventListener("governance:online", onOnline);
      window.removeEventListener("governance:backend-mode", onBackendMode as EventListener);
    };
  }, []);

  if (!offline) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-yellow-600/20 border-b border-yellow-600/30 px-4 py-1.5 text-xs text-yellow-500 select-none">
      <span className="inline-block w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
      <span>治理离线 — Sidecar 未连接，GUI 运行于模拟模式</span>
      <span className="text-yellow-600">({backendMode})</span>
    </div>
  );
}
