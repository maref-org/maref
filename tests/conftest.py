import os
from pathlib import Path

os.environb[b"MAREF_HMAC_SECRET_KEY"] = b"test-key-insecure-not-for-production"
os.environ["MAREF_HMAC_SECRET_KEY"] = "test-key-insecure-not-for-production"
os.environb[b"MAREF_BFT_SECRET_KEY"] = b"test-bft-key-insecure-not-for-production"
os.environ["MAREF_BFT_SECRET_KEY"] = "test-bft-key-insecure-not-for-production"
os.environb[b"MAREF_MCP_SECRET_KEY"] = b"test-mcp-key-insecure-not-for-production"
os.environ["MAREF_MCP_SECRET_KEY"] = "test-mcp-key-insecure-not-for-production"
os.environ["MAREF_BROWSER_AUTH_KEY"] = "test-browser-auth-key-insecure-not-for-production"

# G6 测试隔离：审计写入强制落到临时目录，禁止污染生产 .governance/
# 目录必须先创建，否则 _default_audit_log_path 会回退到 cwd 造成逃逸
_AUDIT_DIR = Path("/tmp/maref-test-audit")
_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
os.environb[b"MAREF_AUDIT_PATH"] = b"/tmp/maref-test-audit"
os.environ["MAREF_AUDIT_PATH"] = "/tmp/maref-test-audit"
os.environb[b"MAREF_GAAS_AUDIT_DIR"] = b"/tmp/maref-test-audit"
os.environ["MAREF_GAAS_AUDIT_DIR"] = "/tmp/maref-test-audit"


import pytest


@pytest.fixture(autouse=True)
def _restore_test_env_keys():
    """每个测试后恢复 conftest 设定的密钥 env，防测试 pop 污染后续。

    部分测试（如 test_cost_guard_opensource fixture teardown）会
    pop MAREF_HMAC_SECRET_KEY 而未恢复，导致后续创建 AuditLogger
    的测试顺序相关失败。此 autouse fixture 保证 key 恒存在。
    """
    yield
    os.environ["MAREF_HMAC_SECRET_KEY"] = "test-key-insecure-not-for-production"
