import { useState, useEffect, useRef, useCallback } from "react";
import {
  Globe,
  ArrowLeft,
  ArrowRight,
  RotateCw,
  Home,
  Wifi,
  WifiOff,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { detectBackend, connectWebSocket } from "@/api/client";

const HOME_URL = "https://maref.io";

export function BrowserView() {
  const [url, setUrl] = useState(HOME_URL);
  const [inputUrl, setInputUrl] = useState(HOME_URL);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([HOME_URL]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [backendMode, setBackendMode] = useState<"checking" | "real" | "mock">("checking");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const pushHistory = useCallback((target: string) => {
    setHistory((prev) => {
      const trimmed = prev.slice(0, historyIndex + 1);
      return [...trimmed, target];
    });
    setHistoryIndex((prev) => prev + 1);
  }, [historyIndex]);

  const handleGo = () => {
    setLoading(true);
    setError(null);
    const target = inputUrl.startsWith("http") ? inputUrl : `https://${inputUrl}`;
    setUrl(target);
    pushHistory(target);
    setLoading(false);
  };

  const handleBack = () => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setHistoryIndex(newIndex);
      const target = history[newIndex];
      setUrl(target);
      setInputUrl(target);
    }
  };

  const handleForward = () => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      const target = history[newIndex];
      setUrl(target);
      setInputUrl(target);
    }
  };

  const handleRefresh = () => {
    setLoading(true);
    setError(null);
    if (iframeRef.current) {
      iframeRef.current.src = url;
    }
    setTimeout(() => setLoading(false), 300);
  };

  const handleHome = () => {
    setInputUrl(HOME_URL);
    setUrl(HOME_URL);
    pushHistory(HOME_URL);
  };

  const connectToBrowser = useCallback(async () => {
    setBackendMode("checking");
    try {
      const mode = await detectBackend();
      setBackendMode(mode);
      if (mode === "real") {
        try {
          const ws = connectWebSocket("/api/sessions/default/browser");
          ws.onopen = () => setConnected(true);
          ws.onclose = () => setConnected(false);
          ws.onerror = () => setConnected(false);
        } catch {
          setConnected(false);
        }
      } else {
        setConnected(false);
      }
    } catch {
      setBackendMode("mock");
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    connectToBrowser();
  }, [connectToBrowser]);

  return (
    <div className="flex h-full flex-col bg-maref-bg">
      <div className="flex items-center gap-1.5 border-b border-maref-border bg-maref-surface px-3 py-2">
        <button
          onClick={handleBack}
          disabled={historyIndex === 0}
          className="rounded p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          title="后退"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <button
          onClick={handleForward}
          disabled={historyIndex >= history.length - 1}
          className="rounded p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          title="前进"
        >
          <ArrowRight className="h-4 w-4" />
        </button>
        <button
          onClick={handleRefresh}
          className="rounded p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          title="刷新"
        >
          <RotateCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </button>
        <button
          onClick={handleHome}
          className="rounded p-1 text-maref-text-muted hover:bg-maref-surface-alt hover:text-maref-text transition-colors"
          title="主页"
        >
          <Home className="h-4 w-4" />
        </button>

        <div className="flex flex-1 items-center gap-2 rounded-md border border-maref-border bg-maref-surface-alt px-3 py-1.5">
          <Globe className="h-3.5 w-3.5 text-maref-text-muted flex-shrink-0" />
          <input
            className="flex-1 bg-transparent text-xs text-maref-text outline-none placeholder:text-maref-text-muted"
            value={inputUrl}
            onChange={(e) => setInputUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleGo()}
            placeholder="输入 URL..."
          />
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {connected ? (
            <Wifi className="h-3.5 w-3.5 text-maref-success" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-maref-danger" />
          )}
          <span className="text-[10px] text-maref-text-muted">
            {connected ? "已连接" : "未连接"}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {loading && (
          <div className="flex h-full items-center justify-center gap-2 text-maref-text-muted">
            <Loader2 className="h-5 w-5 animate-spin text-maref-accent" />
            <span className="text-sm">加载中…</span>
          </div>
        )}

        {error && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-maref-text-muted">
            <div className="rounded-full bg-maref-danger/10 p-3">
              <WifiOff className="h-6 w-6 text-maref-danger" />
            </div>
            <p className="text-sm text-maref-danger">{error}</p>
            <button
              onClick={handleRefresh}
              className="rounded-md bg-maref-surface-alt px-3 py-1.5 text-xs text-maref-text hover:bg-maref-border transition-colors"
            >
              重试
            </button>
          </div>
        )}

        {!loading && !error && !connected && backendMode === "mock" && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-maref-text-muted px-8">
            <div className="rounded-full bg-maref-surface-alt p-4">
              <Globe className="h-8 w-8 text-maref-accent" />
            </div>
            <h3 className="text-sm font-medium text-maref-text">浏览器后端需要 Playwright 远程连接</h3>
            <div className="text-xs text-center space-y-1 max-w-md">
              <p className="text-maref-text-muted">
                启动方式: <code className="text-maref-success font-mono">maref serve --browser</code>
              </p>
              <div className="mt-3 rounded-lg border border-maref-border bg-maref-surface-alt p-4 text-left font-mono text-[11px]">
                <p className="text-maref-success"># 安装 Playwright 后端</p>
                <p className="text-maref-text-muted">pip install playwright</p>
                <p className="text-maref-text-muted">playwright install chromium</p>
                <p className="text-maref-text-muted mt-1">maref browser --port 9222</p>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && !connected && backendMode !== "mock" && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-maref-text-muted px-8">
            <div className="rounded-full bg-maref-surface-alt p-4">
              <Globe className="h-8 w-8 text-maref-accent" />
            </div>
            <h3 className="text-sm font-medium text-maref-text">浏览器后端未连接</h3>
            <div className="text-xs text-center space-y-1 max-w-md">
              <p className="text-maref-text-muted">
                需要 Playwright 后端才能进行远程浏览器渲染。
              </p>
              <div className="mt-3 rounded-lg border border-maref-border bg-maref-surface-alt p-4 text-left font-mono text-[11px]">
                <p className="text-maref-success"># 安装 Playwright 后端</p>
                <p className="text-maref-text-muted">pip install playwright</p>
                <p className="text-maref-text-muted">playwright install chromium</p>
                <p className="text-maref-text-muted mt-1">maref browser --port 9222</p>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && connected && (
          <iframe
            ref={iframeRef}
            src={url}
            className="h-full w-full border-0"
            title="Browser View"
            sandbox="allow-scripts allow-same-origin"
          />
        )}
      </div>
    </div>
  );
}
