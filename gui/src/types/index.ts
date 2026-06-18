export type TabView = "chat" | "browser" | "terminal" | "git" | "governance";

export type ProviderId = "ollama" | "bailian" | "siliconflow" | "openai" | "anthropic";

export type ExecutionMode = "chat" | "agent" | "full-access";

export type CapabilityType = "read-code" | "edit-code" | "run-command" | "debug-error";

export interface ModelProvider {
  id: ProviderId;
  label: string;
  models: string[];
  defaultModel: string;
}

export interface Session {
  id: string;
  title: string;
  mode: ExecutionMode;
  provider: ProviderId;
  model: string;
  contextPercent: number;
  status: "active" | "thinking" | "idle" | "error";
  createdAt: string;
  updatedAt: string;
}

export type Role = "user" | "assistant" | "system" | "tool";

export type StreamEventType =
  | "thinking"
  | "response"
  | "tool_call"
  | "tool_result"
  | "error"
  | "done";

export interface StreamEvent {
  type: StreamEventType;
  content?: string;
  toolCall?: ToolCall;
  error?: string;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface Artifact {
  id: string;
  name: string;
  type: "markdown" | "code" | "excel" | "ppt" | "pdf" | "image" | "csv";
  size?: number;
  status: "generating" | "ready" | "error";
  preview?: string;
  downloadUrl?: string;
}

export interface Message {
  id: string;
  sessionId: string;
  role: Role;
  content: string;
  timestamp: string;
  capabilities?: CapabilityType[];
  toolCalls?: ToolCall[];
  artifacts?: Artifact[];
  modelUsed?: string;
  status?: "complete" | "streaming";
}

export type SceneId = "web_reader" | "research" | "data_mining" | "file_management";

export interface Task {
  id: string;
  name: string;
  description: string;
  priority: 0 | 1 | 2 | 3;
  status: "pending" | "queued" | "running" | "completed" | "failed" | "cancelled" | "timeout";
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  timeout_seconds: number | null;
  max_retries: number;
  retry_count: number;
  error_message: string | null;
  session_id: string | null;
  tags: string[];
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  version: string;
  installed: boolean;
  author: string;
}

export interface Agent {
  id: string;
  sessionId: string;
  title: string;
  mode: ExecutionMode;
  status: "active" | "idle" | "error";
}

export interface FileNode {
  path: string;
  name: string;
  type: "file" | "directory";
  extension?: string;
  children?: FileNode[];
}

export interface ToolCallResult {
  output?: string;
  error?: string;
  status: "success" | "error" | "pending";
  duration?: number;
}

export interface PermissionRequest {
  operation: string;
  description: string;
  risk: "low" | "medium" | "high" | "critical";
}

export interface TokenUsageData {
  used: number;
  total: number;
  cost?: number;
}

export interface HITLEvent {
  event_id: string;
  tier: string;
  severity: string;
  description: string;
  action: string;
  timestamp: number;
  auto_approve_seconds: number;
  status: "pending" | "approved" | "rejected" | "auto_approved" | "expired";
}

export interface HITLStats {
  total_events: number;
  pending_count: number;
  by_tier: Record<string, number>;
  by_status: Record<string, number>;
  tier_map: Record<string, string>;
}

export interface GuardrailStats {
  total_checks: number;
  allow_rate: number;
  deny_rate: number;
  audit_rate: number;
  risk_scores: Array<{ agent_id: string; score: number }>;
  open_circuit_breakers: number;
  active_denials: number;
}

export interface GuardrailEvent {
  verdict: string;
  gate: string;
  duration: number;
  timestamp: number;
}

export interface CooldownEntry {
  id: string;
  agent_id: string;
  agent_name: string;
  status: "cooling" | "blocked" | "merged" | "force_merged";
  submitted_at: string;
  evaluated_at: string | null;
  merged_at: string | null;
  age_seconds: number;
  contamination_score: number;
  blocked_reason: string | null;
  merged_branch: string | null;
}

export interface CooldownSummary {
  status: string;
  total_agents: number;
  cooling: number;
  blocked: number;
  merged: number;
  force_merged: number;
}

export interface GeneEntry {
  id: string;
  source: string;
  cwe: string;
  risk_level: "low" | "medium" | "high" | "critical";
  severity: number;
  occurrences: number;
  first_seen: string;
  last_seen: string;
  description: string;
}
