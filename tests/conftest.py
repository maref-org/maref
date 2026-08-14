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
