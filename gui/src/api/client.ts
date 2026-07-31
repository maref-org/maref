import type { GuardrailStats, Session, Message, ModelProvider, Skill, Task, FileNode, HITLEvent, HITLStats } from "@/types";

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

function _dispatchGovernanceEvent(mode: "real" | "mock") {
  if (mode === "mock") {
    window.dispatchEvent(new CustomEvent("governance:offline", { detail: { mode } }));
  } else {
    window.dispatchEvent(new CustomEvent("governance:online", { detail: { mode } }));
  }
  window.dispatchEvent(new CustomEvent("governance:backend-mode", { detail: { mode } }));
}

export async function detectBackend(): Promise<"real" | "mock"> {
  const healthy = await checkBackendHealth();
  _backendMode = healthy ? "real" : "mock";
  _dispatchGovernanceEvent(_backendMode);
  return _backendMode;
}

export function setBackendMode(mode: "real" | "mock") {
  _backendMode = mode;
  _dispatchGovernanceEvent(mode);
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

  getTasks: () => request<{ tasks: Task[] }>("/v1/tasks"),

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
      ? `${REAL_BACKEND}/api/v1/sessions/${sessionId}/stream`
      : `${BASE_URL}/v1/sessions/${sessionId}/stream`,

  getTerminalUrl: (sessionId: string) =>
    _backendMode === "real"
      ? `ws://localhost:8000/api/v1/sessions/${sessionId}/terminal`
      : `ws://localhost:8000/api/v1/sessions/${sessionId}/terminal`,

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
    return request<{ events: HITLEvent[]; count: number }>(
      `/v1/hitl/pending${params}`);
  },

  hitlStats: () =>
    request<HITLStats>("/v1/hitl/stats"),

  hitlApprove: (eventId: string) =>
    request<{ event_id: string; status: string; approved: boolean }>(
      `/v1/hitl/${eventId}/approve`, { method: "POST" }),

  hitlDeny: (eventId: string) =>
    request<{ event_id: string; status: string; cancelled: boolean; reason: string }>(
      `/v1/hitl/${eventId}/deny`, { method: "POST" }),

  hitlHistory: (limit = 50, offset = 0) =>
    request<{ events: HITLEvent[]; count: number }>(
      `/v1/hitl/history?limit=${limit}&offset=${offset}`),

  // ── Immunity API ────────────────────────────────────

  getImmunityCooldown: () =>
    request<{ entries: Array<{ id: string; agent_id: string; agent_name: string; status: string; submitted_at: string; evaluated_at: string | null; merged_at: string | null; age_seconds: number; contamination_score: number; blocked_reason: string | null; merged_branch: string | null }> }>(
      "/api/immunity/cooldown"),

  getImmunityCooldownSummary: () =>
    request<{ status: string; total_agents: number; cooling: number; blocked: number; merged: number; force_merged: number }>(
      "/api/immunity/cooldown/summary"),

  getImmunityGenes: () =>
    request<{ genes: Array<{ id: string; source: string; cwe: string; risk_level: string; severity: number; occurrences: number; first_seen: string; last_seen: string; description: string }> }>(
      "/api/immunity/genes"),

  // ── Governance API ───────────────────────────────────

  getGovernanceState: () =>
    request<{ state: string; entropy: number; entropy_max: number; transition_count: number; circuit_breaker: string }>(
      "/v1/governance/state"),

  getGovernanceTransitions: () =>
    request<{ transitions: Array<{ from: string; to: string; reason: string; time: string; valid: boolean }> }>(
      "/v1/governance/transitions"),

  getCircuitBreakerEvents: () =>
    request<{ events: Array<{ from: string; to: string; reason: string; time: string }> }>(
      "/v1/governance/circuit-breaker"),

  getOscillationEvents: () =>
    request<{ events: Array<{ stage: string; desc: string; time: string }> }>(
      "/v1/governance/oscillation"),

  // ── Audit API ────────────────────────────────────────

  // ── Guardrails API ───────────────────────────────────

  getGuardrailsStats: () =>
    request<GuardrailStats>("/v1/guardrails/stats"),

  getGuardrailsEvents: (limit = 50) =>
    request<{ events: Array<{ verdict: string; gate: string; duration: number; timestamp: number }> }>(
      `/v1/guardrails/events?limit=${limit}`),

  // ── Observability API ──────────────────────────────

  getErrorBudget: () =>
    request<{
      slo_target: number;
      budget: { total: number; consumed: number; remaining: number; remaining_pct: number };
      burn_rate: number;
      alerts: Array<{ level: string; burn_rate: number; threshold: number; window_seconds: number; triggered: boolean; slo_name: string }>;
      budget_exhausted: boolean;
      time_to_exhaustion_seconds: number;
      total_errors?: number;
      recent_errors?: Array<{ id: string; severity: string; source: string; message: string; timestamp: string }>;
    }>("/v1/observability/error-budget"),

  getCostReport: (agentId?: string, since?: string) => {
    const params = new URLSearchParams();
    if (agentId) params.set("agent_id", agentId);
    if (since) params.set("since", since);
    const qs = params.toString();
    return request<{ agent_id: string; total_cost: number; record_count: number; records?: Array<Record<string, unknown>> }>(
      `/v1/observability/cost-report${qs ? `?${qs}` : ""}`);
  },

  getCostByTeam: () =>
    request<Record<string, number>>("/v1/observability/cost-by-team"),

  // ── RSI (Pareto) API ─────────────────────────────────

  getParetoFront: () =>
    request<{ dimensions: string[]; current_scores: Record<string, number>; recommended_weights: Record<string, number>; rationale: string }>(
      "/v1/rsi/pareto-front"),

  getCrossEffects: () =>
    request<{ source_dim: string; target_dim: string; effect_size: number; direction: string; confidence: number }[]>(
      "/v1/rsi/cross-effects"),

  getAdaptiveAllocation: () =>
    request<{ target: string; rounds_allocated: number; success_rate: number; current_weight: number }[]>(
      "/v1/rsi/adaptive-allocation"),

  // ── Evolution Timeline API ──────────────────────────

  getEvolutionTimeline: () =>
    request<{
      day: number;
      date: string;
      avgScore: number;
      adoptionRate: number;
      dimensions: Record<string, number>;
      events: Array<{
        type: "version" | "gate" | "conflict" | "heal" | "alert";
        label: string;
        detail: string;
        timestamp: string;
      }>;
      selfHealCount: number;
      selfHealSuccesses: number;
      version?: string;
    }[]>("/v1/rsi/evolution-timeline"),

  // ── Audit API ────────────────────────────────────────

  getAuditLogs: (params?: { type?: string; search?: string; limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.type) searchParams.set("type", params.type);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    return request<{ entries: Array<{ id: number; type: string; actor: string; action: string; reason: string; severity: string; time: string }>; total: number; counts: Record<string, number> }>(
      `/v1/audit/logs${qs ? `?${qs}` : ""}`);
  },
};
