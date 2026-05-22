import type { Session, Message, ModelProvider, Skill, Task, FileNode, HITLEvent } from "@/types";

const REAL_BACKEND = "http://localhost:8000";
const BASE_URL = "/api";

let _backendMode: "checking" | "real" | "mock" = "checking";

export function getBackendMode() {
  return _backendMode;
}

export function setBackendMode(mode: "real" | "mock") {
  _backendMode = mode;
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${REAL_BACKEND}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function detectBackend(): Promise<"real" | "mock"> {
  const healthy = await checkBackendHealth();
  _backendMode = healthy ? "real" : "mock";
  return _backendMode;
}

export function connectWebSocket(path: string): WebSocket {
  const wsPath = path.startsWith("/") ? path : `/${path}`;
  return new WebSocket(`ws://localhost:8000${wsPath}`);
}

export function connectSSE(url: string): EventSource {
  if (url.startsWith("http")) return new EventSource(url);
  return new EventSource(`${REAL_BACKEND}${url}`);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message ?? "API request failed");
  }
  return res.json();
}

export const api = {
  getProviders: () => request<{ providers: ModelProvider[] }>("/providers"),

  getSkills: () => request<{ skills: Skill[] }>("/skills"),

  createSession: (body: { title: string; mode: string; provider: string; model: string }) =>
    request<Session>("/sessions", { method: "POST", body: JSON.stringify(body) }),

  getSessions: () => request<{ sessions: Session[] }>("/sessions"),

  getSession: (id: string) => request<Session>(`/sessions/${id}`),

  sendMessage: (sessionId: string, content: string) =>
    request<Message>(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  getMessages: (sessionId: string) =>
    request<{ messages: Message[] }>(`/sessions/${sessionId}/messages`),

  interrupt: (sessionId: string) =>
    request<void>(`/sessions/${sessionId}/interrupt`, { method: "POST" }),

  approve: (sessionId: string, actionId: string) =>
    request<void>(`/sessions/${sessionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ actionId }),
    }),

  getTasks: () => request<{ tasks: Task[] }>("/tasks"),

  submitTask: (body: {
    name: string;
    description?: string;
    priority?: number;
    payload?: Record<string, unknown>;
    timeout_seconds?: number;
    max_retries?: number;
    tags?: string[];
    session_id?: string;
  }) => request<Task>("/v1/tasks", { method: "POST", body: JSON.stringify(body) }),

  getTask: (id: string) => request<Task>(`/v1/tasks/${id}`),

  cancelTask: (id: string) =>
    request<Task>(`/v1/tasks/${id}/cancel`, { method: "POST" }),

  listTasks: (params?: {
    status?: string;
    priority?: number;
    session_id?: string;
    tag?: string;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.priority !== undefined) searchParams.set("priority", String(params.priority));
    if (params?.session_id) searchParams.set("session_id", params.session_id);
    if (params?.tag) searchParams.set("tag", params.tag);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    return request<{ tasks: Task[]; total: number }>(`/v1/tasks${qs ? `?${qs}` : ""}`);
  },

  getFileTree: () => request<{ tree: FileNode[] }>("/filetree"),

  getStreamUrl: (sessionId: string) =>
    _backendMode === "real"
      ? `${REAL_BACKEND}/sessions/${sessionId}/stream`
      : `${BASE_URL}/sessions/${sessionId}/stream`,

  getTerminalUrl: (sessionId: string) =>
    _backendMode === "real"
      ? `ws://localhost:8000/sessions/${sessionId}/terminal`
      : `ws://localhost:8000/api/sessions/${sessionId}/terminal`,

  // ── Desktop Controller API ──────────────────────────────

  desktopStatus: () => request("/v1/desktop/status"),

  desktopPermissions: () => request("/v1/desktop/permissions", { method: "POST" }),

  desktopCalibrate: () => request("/v1/desktop/calibrate", { method: "POST" }),

  desktopCapture: () => request("/v1/desktop/capture", { method: "POST" }),

  desktopParse: (screenshotPath = "") =>
    request("/v1/desktop/parse", { method: "POST", body: JSON.stringify({ screenshot_path: screenshotPath }) }),

  desktopUiElements: () => request("/v1/desktop/ui-elements"),

  desktopExecute: (opType: string, params: Record<string, unknown> = {}, description = "") =>
    request("/v1/desktop/execute", {
      method: "POST",
      body: JSON.stringify({ op_type: opType, params, description }),
    }),

  desktopExecutePlan: (steps: Array<{ op_type: string; params: Record<string, unknown>; description?: string }>, dryRun = true, description = "") =>
    request("/v1/desktop/execute-plan", {
      method: "POST",
      body: JSON.stringify({ steps, dry_run: dryRun, description }),
    }),

  desktopExecuteTemplate: (templateName: string, dryRun = true) =>
    request("/v1/desktop/execute-template", {
      method: "POST",
      body: JSON.stringify({ template_name: templateName, dry_run: dryRun }),
    }),

  desktopHistory: (limit = 50) => request(`/v1/desktop/history?limit=${limit}`),

  desktopExecutionDetails: (executionId: number) => request(`/v1/desktop/history/${executionId}`),

  desktopPolicyStatus: () => request("/v1/desktop/policy-status"),

  desktopSetMode: (mode: string) => request("/v1/desktop/set-mode", { method: "POST", body: JSON.stringify({ mode }) }),

  desktopApproveHitl: () => request("/v1/desktop/hitl/approve", { method: "POST" }),

  desktopRejectHitl: () => request("/v1/desktop/hitl/reject", { method: "POST" }),

  desktopDecisionLog: () => request("/v1/desktop/decision-log"),

  desktopGovernanceStatus: () => request("/v1/desktop/governance-status"),

  desktopSetGovernanceMode: (mode: string) => request(`/v1/desktop/governance/mode?mode=${mode}`, { method: "POST" }),

  desktopGovernanceEvents: (limit = 50) => request(`/v1/desktop/governance-events?limit=${limit}`),

  // ── HITL API ─────────────────────────────────────────

  hitlRequestApproval: (body: { session_id: string; action: string; description: string; parameters?: Record<string, unknown>; tier?: string }) =>
    request<{ event_id: string; status: string; action: string; description: string; tier: string; requires_human: boolean; auto_approve_seconds: number }>(
      "/v1/hitl/request", { method: "POST", body: JSON.stringify(body) }),

  hitlConfirm: (eventId: string) =>
    request<{ event_id: string; status: string; approved: boolean }>(
      "/v1/hitl/confirm", { method: "POST", body: JSON.stringify({ event_id: eventId }) }),

  hitlCancel: (eventId: string) =>
    request<{ event_id: string; status: string; cancelled: boolean; reason: string }>(
      "/v1/hitl/cancel", { method: "POST", body: JSON.stringify({ event_id: eventId }) }),

  hitlPause: (sessionId: string) =>
    request<{ session_id: string; paused: boolean; message: string }>(
      `/v1/hitl/pause?session_id=${sessionId}`, { method: "POST" }),

  hitlResume: (sessionId: string) =>
    request<{ session_id: string; resumed: boolean; message: string }>(
      `/v1/hitl/resume?session_id=${sessionId}`, { method: "POST" }),

  hitlPending: (tier?: string) => {
    const params = tier ? `?tier=${tier}` : "";
    return request<{ events: Array<{ event_id: string; tier: string; severity: string; description: string; action: string; timestamp: number; auto_approve_seconds: number; status: string }>; count: number }>(
      `/v1/hitl/pending${params}`);
  },

  hitlStats: () =>
    request<{ stats: Record<string, unknown> }>("/v1/hitl/stats"),

  hitlApprove: (eventId: string) =>
    request<{ event_id: string; status: string; approved: boolean }>(
      `/v1/hitl/${eventId}/approve`, { method: "POST" }),

  hitlDeny: (eventId: string) =>
    request<{ event_id: string; status: string; cancelled: boolean; reason: string }>(
      `/v1/hitl/${eventId}/deny`, { method: "POST" }),

  hitlHistory: (limit = 50, offset = 0) =>
    request<{ events: HITLEvent[]; count: number }>(
      `/v1/hitl/history?limit=${limit}&offset=${offset}`),
};
