#!/usr/bin/env python3
"""
Runtime Audit Log — Agent 运行时行为审计日志模块

记录 agent 的每次 LLM 调用、文件操作、状态转换。
写入 /tmp/opc-agent-bus/audit.log，audit agent 可读取验证。

用法:
    from runtime_audit_log import AuditLogger

    logger = AuditLogger("audit-agent")
    logger.log_llm_call("dashscope", "qwen-max", 200, 0.85)
    logger.log_file_op("read", "/path/to/file", "success")
    logger.log_state_transition("idle", "auditing")

    reader = AuditLogReader()
    entries = reader.get_recent(10)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────────────

AUDIT_LOG_DIR = Path("/tmp/opc-agent-bus")
AUDIT_LOG_FILE = AUDIT_LOG_DIR / "audit.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB rotation
MAX_LOG_ENTRIES = 10000

# ── 操作类型 ──────────────────────────────────────────────────

class OpType:
    LLM_CALL = "llm_call"
    FILE_OP = "file_op"
    STATE_TRANSITION = "state_transition"
    AGENT_BUS_EVENT = "agent_bus_event"
    HEARTBEAT = "heartbeat"
    AUDIT_RESULT = "audit_result"
    PROPOSAL = "proposal"
    DISTRIBUTION = "distribution"
    ERROR = "error"

# ── 状态码 ───────────────────────────────────────────────────

class Status:
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    BLOCKED = "blocked"

# ── 审计日志写入器 ──────────────────────────────────────────

class AuditLogger:
    """Agent 运行时行为审计日志写入器（线程安全）"""

    def __init__(self, agent_name: str, log_file: Path = AUDIT_LOG_FILE):
        self.agent_name = agent_name
        self.log_file = log_file
        self._lock = threading.Lock()
        self._entries_written = 0
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.write_text("", encoding="utf-8")

    def _rotate_if_needed(self) -> None:
        """日志文件超过 10MB 时轮转"""
        if self.log_file.stat().st_size > MAX_LOG_SIZE:
            backup = self.log_file.with_suffix(f".log.{int(time.time())}")
            self.log_file.rename(backup)
            self.log_file.write_text("", encoding="utf-8")
            logger.info("🔄 审计日志轮转: %s", backup.name)

    def _write_entry(self, entry: dict) -> None:
        with self._lock:
            self._rotate_if_needed()
            entry["timestamp"] = datetime.now(timezone.utc).isoformat()
            entry["agent"] = self.agent_name
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line)
                self._entries_written += 1
            except OSError as e:
                logger.error("❌ 审计日志写入失败: %s", e)

    def log_llm_call(
        self,
        provider: str,
        model: str,
        status_code: int = 200,
        score: Optional[float] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """记录 LLM 调用"""
        self._write_entry({
            "op_type": OpType.LLM_CALL,
            "provider": provider,
            "model": model,
            "status_code": status_code,
            "score": score,
            "duration_ms": duration_ms,
            "error": error,
        })

    def log_file_op(self, operation: str, path: str, status: str, details: Optional[str] = None) -> None:
        """记录文件操作"""
        self._write_entry({
            "op_type": OpType.FILE_OP,
            "operation": operation,
            "path": str(path),
            "status": status,
            "details": details,
        })

    def log_state_transition(self, from_state: str, to_state: str, reason: Optional[str] = None) -> None:
        """记录状态转换"""
        self._write_entry({
            "op_type": OpType.STATE_TRANSITION,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
        })

    def log_agent_bus_event(self, event_type: str, payload_summary: str) -> None:
        """记录 Agent Bus 事件"""
        self._write_entry({
            "op_type": OpType.AGENT_BUS_EVENT,
            "event_type": event_type,
            "payload": payload_summary[:200],
        })

    def log_heartbeat(self, status: str = "alive") -> None:
        """记录心跳"""
        self._write_entry({
            "op_type": OpType.HEARTBEAT,
            "status": status,
        })

    def log_audit_result(self, task_id: str, median_score: float, verdict: str, disagreement: float) -> None:
        """记录审计结果"""
        self._write_entry({
            "op_type": OpType.AUDIT_RESULT,
            "task_id": task_id,
            "median_score": median_score,
            "verdict": verdict,
            "disagreement": disagreement,
        })

    def log_proposal(self, proposal_id: str, topic: str, status: str) -> None:
        """记录内容提案"""
        self._write_entry({
            "op_type": OpType.PROPOSAL,
            "proposal_id": proposal_id,
            "topic": topic[:100],
            "status": status,
        })

    def log_distribution(self, content_id: str, channel: str, status: str, url: Optional[str] = None) -> None:
        """记录内容分发"""
        self._write_entry({
            "op_type": OpType.DISTRIBUTION,
            "content_id": content_id,
            "channel": channel,
            "status": status,
            "url": url,
        })

    def log_error(self, error_type: str, message: str, context: Optional[dict] = None) -> None:
        """记录错误"""
        self._write_entry({
            "op_type": OpType.ERROR,
            "error_type": error_type,
            "message": message[:500],
            "context": context or {},
        })

    @property
    def entries_count(self) -> int:
        return self._entries_written

    def summary(self) -> dict:
        """返回当前会话摘要"""
        return {
            "agent": self.agent_name,
            "entries_written": self._entries_written,
            "log_file": str(self.log_file),
        }


# ── 审计日志读取器 ──────────────────────────────────────────

class AuditLogReader:
    """审计日志读取器 — 供 audit agent 验证完整性"""

    def __init__(self, log_file: Path = AUDIT_LOG_FILE):
        self.log_file = log_file

    def read_all(self) -> list[dict]:
        """读取所有日志条目"""
        if not self.log_file.exists():
            return []
        entries = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError as e:
            logger.error("❌ 审计日志读取失败: %s", e)
        return entries

    def get_recent(self, n: int = 20) -> list[dict]:
        """获取最近 n 条日志条目"""
        all_entries = self.read_all()
        return all_entries[-n:]

    def filter_by_agent(self, agent_name: str, entries: Optional[list[dict]] = None) -> list[dict]:
        """按 agent 名称筛选"""
        source = entries if entries is not None else self.read_all()
        return [e for e in source if e.get("agent") == agent_name]

    def filter_by_op_type(self, op_type: str, entries: Optional[list[dict]] = None) -> list[dict]:
        """按操作类型筛选"""
        source = entries if entries is not None else self.read_all()
        return [e for e in source if e.get("op_type") == op_type]

    def filter_by_time_range(self, start: str, end: str, entries: Optional[list[dict]] = None) -> list[dict]:
        """按时间范围筛选"""
        source = entries if entries is not None else self.read_all()
        return [e for e in source if start <= e.get("timestamp", "") <= end]

    def get_statistics(self, entries: Optional[list[dict]] = None) -> dict:
        """获取统计摘要"""
        source = entries if entries is not None else self.read_all()
        if not source:
            return {"total": 0, "by_op_type": {}, "by_agent": {},
                    "error_count": 0, "llm_calls": 0, "distributions": 0}

        op_counts: dict[str, int] = {}
        agent_counts: dict[str, int] = {}
        error_count = 0
        llm_calls = 0
        distributions = 0

        for entry in source:
            op_type = entry.get("op_type", "unknown")
            op_counts[op_type] = op_counts.get(op_type, 0) + 1

            agent = entry.get("agent", "unknown")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

            if op_type == OpType.ERROR:
                error_count += 1
            elif op_type == OpType.LLM_CALL:
                llm_calls += 1
            elif op_type == OpType.DISTRIBUTION:
                distributions += 1

        return {
            "total": len(source),
            "by_op_type": op_counts,
            "by_agent": agent_counts,
            "error_count": error_count,
            "llm_calls": llm_calls,
            "distributions": distributions,
        }

    def verify_integrity(self) -> dict:
        """验证日志完整性 — 供 audit agent 审计"""
        entries = self.read_all()
        issues = []

        # 检查必要字段
        required_fields = {"timestamp", "agent", "op_type"}
        for i, entry in enumerate(entries):
            missing = required_fields - set(entry.keys())
            if missing:
                issues.append({
                    "line": i + 1,
                    "issue": f"缺少字段: {missing}",
                    "entry": entry,
                })

        # 检查时间戳倒序（最近的在前）
        if len(entries) >= 2:
            timestamps = [e.get("timestamp", "") for e in entries[-10:]]
            for i in range(1, len(timestamps)):
                if timestamps[i] and timestamps[i - 1] and timestamps[i] < timestamps[i - 1]:
                    issues.append({
                        "line": len(entries) - 10 + i,
                        "issue": "时间戳乱序",
                    })

        return {
            "total_entries": len(entries),
            "issues": issues,
            "healthy": len(issues) == 0,
            "format": "jsonl",
            "log_file": str(self.log_file),
        }


# ── 命令行入口 ──────────────────────────────────────────────

def main():
    import sys as _sys

    if len(_sys.argv) < 2:
        print("用法: runtime_audit_log.py [read|stats|verify|watch] [n]")
        return

    reader = AuditLogReader()
    cmd = _sys.argv[1]

    if cmd == "read":
        n = int(_sys.argv[2]) if len(_sys.argv) > 2 else 20
        entries = reader.get_recent(n)
        print(f"最近 {n} 条审计日志:")
        print("─" * 80)
        for e in entries:
            ts = e.get("timestamp", "?")[11:19]
            agent = e.get("agent", "?")
            op = e.get("op_type", "?")
            print(f"  [{ts}] {agent:15s} {op:20s} {json.dumps(e, ensure_ascii=False)[:80]}")

    elif cmd == "stats":
        stats = reader.get_statistics()
        print("审计日志统计:")
        print(f"  总条目:     {stats['total']}")
        print(f"  按类型:     {stats.get('by_op_type', {})}")
        print(f"  按 Agent:   {stats.get('by_agent', {})}")
        print(f"  错误数:     {stats['error_count']}")
        print(f"  LLM 调用:   {stats['llm_calls']}")
        print(f"  分发次数:   {stats['distributions']}")

    elif cmd == "verify":
        result = reader.verify_integrity()
        print("审计日志完整性验证:")
        print(f"  总条目:   {result['total_entries']}")
        print(f"  健康:     {'✅' if result['healthy'] else '❌'}")
        if result['issues']:
            print(f"  问题:     {len(result['issues'])} 个")
            for issue in result['issues'][:5]:
                print(f"    - 行 {issue.get('line')}: {issue.get('issue')}")

    elif cmd == "watch":
        # 持续尾随日志
        import time as _time
        print("持续尾随审计日志 (Ctrl+C 停止)...")
        last_size = 0
        try:
            while True:
                if reader.log_file.exists():
                    current_size = reader.log_file.stat().st_size
                    if current_size > last_size:
                        with open(reader.log_file, "r") as f:
                            f.seek(last_size)
                            for line in f:
                                if line.strip():
                                    entry = json.loads(line)
                                    ts = entry.get("timestamp", "?")[11:19]
                                    agent = entry.get("agent", "?")
                                    op = entry.get("op_type", "?")
                                    print(f"  [{ts}] {agent:15s} {op:20s}")
                        last_size = current_size
                _time.sleep(1)
        except KeyboardInterrupt:
            pass

    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
