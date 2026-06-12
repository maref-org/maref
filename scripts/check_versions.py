"""验证所有版本标签一致。"""
from __future__ import annotations

import re
import sys

expected = "0.30.0"

files_checks = {
    "pyproject.toml": r'version\s*=\s*"([^"]+)"',
    "Dockerfile": r'org\.opencontainers\.image\.version="([^"]+)"',
    "k8s/production/deployment.yaml": r"version:\s*(.+)",
    "gui/src-tauri/Cargo.toml": r'version\s*=\s*"([^"]+)"',
}

errors = []
for path, pattern in files_checks.items():
    content = open(path).read()
    match = re.search(pattern, content)
    if match and expected not in match.group(1):
        errors.append(f"{path}: {match.group(1)} (expected {expected})")

if errors:
    print("Version inconsistencies found:")
    for e in errors:
        print(f"  ❌ {e}")
    sys.exit(1)
else:
    print("✅ All versions consistent")
