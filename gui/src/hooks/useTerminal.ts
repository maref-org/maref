import { useEffect, useRef, useState, useCallback } from "react";
import { getBackendMode, connectWebSocket } from "@/api/client";

interface RealTerminalState {
  output: string[];
  isConnected: boolean;
}

export function useRealTerminal(sessionId: string | null) {
  const [state, setState] = useState<RealTerminalState>({
    output: [],
    isConnected: false,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const retries = useRef(0);

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  useEffect(() => {
    if (!sessionId || getBackendMode() !== "real") return;

    let disposed = false;

    function connect() {
      if (disposed) return;
      wsRef.current?.close();

      const ws = connectWebSocket(`/sessions/${sessionId}/terminal`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (disposed) return;
        setState((s) => ({ ...s, isConnected: true }));
        retries.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (disposed) return;
        let text: string;
        if (event.data instanceof ArrayBuffer) {
          text = new TextDecoder().decode(event.data);
        } else if (event.data instanceof Blob) {
          const reader = new FileReader();
          reader.onload = () => {
            if (!disposed) {
              setState((s) => ({
                ...s,
                output: [...s.output, reader.result as string],
              }));
            }
          };
          reader.readAsText(event.data);
          return;
        } else {
          text = String(event.data);
        }
        setState((s) => ({
          ...s,
          output: [...s.output, text],
        }));
      };

      ws.onclose = () => {
        if (disposed) return;
        setState((s) => ({ ...s, isConnected: false }));
        const backoff = Math.min(1000 * 2 ** retries.current, 30000);
        retries.current += 1;
        reconnectTimer.current = setTimeout(connect, backoff);
      };

      ws.onerror = () => {
        if (disposed) return;
        setState((s) => ({ ...s, isConnected: false }));
      };
    }

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [sessionId]);

  const clearOutput = useCallback(() => {
    setState((s) => ({ ...s, output: [] }));
  }, []);

  return {
    output: state.output,
    isConnected: state.isConnected,
    send,
    clearOutput,
  };
}
