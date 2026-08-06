#!/usr/bin/env python3
"""
启动修复版 sidecar
"""

import subprocess
import sys
import os

# 启动修复版 sidecar
port = 8000
cmd = [
    sys.executable, "-m", "uvicorn",
    "fixed_sidecar:create_fixed_app",
    "--host", "0.0.0.0",
    "--port", str(port),
    "--reload"
]

print(f"启动修复版 sidecar (端口: {port})...")
print(f"命令: {' '.join(cmd)}")
print(f"健康检查: http://127.0.0.1:{port}/api/health")
print(f"GaaS 治理: http://127.0.0.1:{port}/api/v1/gaas/govern")

subprocess.run(cmd)
