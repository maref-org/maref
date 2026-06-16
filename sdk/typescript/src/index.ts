export interface GovernanceStatus {
  state: string;
  circuit_breaker: "CLOSED" | "OPEN" | "HALF_OPEN";
  agent_count: number;
  trust_score_avg: number;
  drift_level: "LOW" | "MEDIUM" | "HIGH";
  timestamp: number;
}

export interface AgentTrustScore {
  agent_id: string;
  score: number;
  factors: {
    behavior_consistency: number;
    cb_trigger_frequency: number;
    halt_escape_rate: number;
    task_completion: number;
    vc_validity: number;
  };
}

export class MAREFClient {
  private baseUrl: string;

  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async getGovernanceStatus(): Promise<GovernanceStatus> {
    const res = await fetch(`${this.baseUrl}/api/status`);
    return res.json();
  }

  async getAgentTrustScore(agentId: string): Promise<AgentTrustScore> {
    const res = await fetch(`${this.baseUrl}/api/agents/${agentId}/trust`);
    return res.json();
  }

  async listAgents(): Promise<string[]> {
    const res = await fetch(`${this.baseUrl}/api/agents`);
    const data = await res.json();
    return data.agents;
  }

  subscribeAuditLog(callback: (entry: Record<string, unknown>) => void): EventSource {
    const source = new EventSource(`${this.baseUrl}/api/audit/stream`);
    source.onmessage = (event) => {
      callback(JSON.parse(event.data));
    };
    return source;
  }
}
