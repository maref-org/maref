import { useGovernanceStore } from "@/stores/governanceStore";
import { useHITLStore } from "@/stores/hitlStore";
import { useGuardrailsStore } from "@/stores/guardrailsStore";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EventCallback = (data: any) => void;

class WSClient {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private wsUrl: string;

  constructor(url = "ws://localhost:8000/ws/events") {
    this.wsUrl = url;
  }

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.onopen = () => {
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event: MessageEvent) => {
        this.handleMessage(event);
      };

      this.ws.onclose = () => {
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  on(event: string, callback: EventCallback): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  off(event: string, callback: EventCallback): void {
    this.listeners.get(event)?.delete(callback);
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data);
      const eventType = data.type as string;

      const cbs = this.listeners.get(eventType);
      if (cbs) {
        for (const cb of cbs) {
          try {
            cb(data);
          } catch {
            // ignore per-callback errors
          }
        }
      }

      const genericCbs = this.listeners.get("*");
      if (genericCbs) {
        for (const cb of genericCbs) {
          try {
            cb(data);
          } catch {
            // ignore per-callback errors
          }
        }
      }

      this.handleStoreRefresh(eventType);
    } catch {
      // ignore malformed messages
    }
  }

  private handleStoreRefresh(eventType: string): void {
    switch (eventType) {
      case "governance:transition":
        useGovernanceStore.getState().refreshAll();
        break;
      case "hitl:pending":
      case "hitl:resolved":
        useHITLStore.getState().fetchPending();
        useHITLStore.getState().fetchStats();
        break;
      case "guardrails:check":
        useGuardrailsStore.getState().fetchStats();
        break;
      case "audit:entry":
        console.log("[ws] audit:entry event received", eventType);
        break;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 3000);
  }
}

export const wsClient = new WSClient();
