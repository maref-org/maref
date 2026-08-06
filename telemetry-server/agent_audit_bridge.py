"""
MAREF Agent Audit Bridge — 为 MAREF agent 提供运行时审计日志能力

用法:
    from telemetry_server.agent_audit_bridge import AgentAuditor

    auditor = AgentAuditor("my-agent")
    auditor.log_llm_call("deepseek", "deepseek-chat", 200)
    auditor.log_state_transition("idle", "processing")
"""

from __future__ import annotations

import os
from pathlib import Path
from runtime_audit_log import AuditLogger, AuditLogReader

# MAREF 审计日志路径
MAREF_AUDIT_LOG = Path("/var/log/maref/audit.log")


class AgentAuditor:
    """MAREF Agent 运行时审计包装器"""

    def __init__(self, agent_name: str, log_file: str | Path = MAREF_AUDIT_LOG):
        self.agent_name = agent_name
        self.logger = AuditLogger(agent_name, log_file=Path(log_file))
        self.reader = AuditLogReader(log_file=Path(log_file))

    # ── LLM 调用审计 ──
    def log_llm_call(self, provider: str, model: str, status_code: int,
                     score: float = 0.0, duration_ms: float = 0.0, error: str | None = None):
        self.logger.log_llm_call(provider, model, status_code, score, duration_ms, error)

    # ── 状态转换 ──
    def log_state_transition(self, from_state: str, to_state: str, reason: str = ""):
        self.logger.log_state_transition(from_state, to_state, reason)

    # ── 文件操作 ──
    def log_file_op(self, operation: str, path: str, status: str):
        self.logger.log_file_op(operation, path, status)

    # ── 审计结果 ──
    def log_audit_result(self, task_id: str, score: float, verdict: str, disagreement: float = 0.0):
        self.logger.log_audit_result(task_id, score, verdict, disagreement)

    # ── 心跳 ──
    def log_heartbeat(self, status: str = "alive"):
        self.logger.log_heartbeat(status)

    # ── 错误 ──
    def log_error(self, error_type: str, message: str, context: dict | None = None):
        self.logger.log_error(error_type, message, context)

    # ── 查询 ──
    def get_recent_entries(self, n: int = 20) -> list[dict]:
        return self.reader.get_recent(n)

    def get_statistics(self) -> dict:
        return self.reader.get_statistics()

    def verify_log_integrity(self) -> dict:
        return self.reader.verify_integrity()
