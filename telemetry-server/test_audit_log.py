"""Tests for runtime_audit_log module."""
import os, sys, tempfile, json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from runtime_audit_log import AuditLogger, AuditLogReader, OpType, Status

tmp = tempfile.NamedTemporaryFile(suffix=".log", delete=False, mode="w")
tmp.close()
log_path = Path(tmp.name)

logger = AuditLogger("test-agent", log_file=log_path)
reader = AuditLogReader(log_file=log_path)

# Test all operation types
logger.log_llm_call("deepseek", "deepseek-chat", 200, 0.95, duration_ms=1500)
logger.log_file_op("write", "/tmp/test.txt", "success")
logger.log_state_transition("idle", "running", reason="startup")
logger.log_agent_bus_event("scan.complete", '{"count": 5}')
logger.log_heartbeat("alive (uptime=100s)")
logger.log_audit_result("content_quality", 82.5, "conditional", 2.1)
logger.log_proposal("prop-001", "ghost-ai-governance", "approved")
logger.log_distribution("content-1", "zhihu", "published", "https://zhihu.com/test")
logger.log_error("TestError", "something broke")

# Read stats
stats = reader.get_statistics()
print(f"Total: {stats['total']}")
print(f"By type: {stats['by_op_type']}")
print(f"By agent: {stats['by_agent']}")
assert stats["total"] == 9, f"total={stats['total']}"
assert stats["by_op_type"]["llm_call"] == 1
assert stats["by_agent"]["test-agent"] == 9

# Verify integrity
entries = reader.read_all()
assert len(entries) == 9

os.unlink(tmp.name)
print("✅ All 9 operation types passed!")
