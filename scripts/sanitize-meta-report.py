#!/usr/bin/env python3
"""Sanitize meta-monitor report before public artifact upload.

meta-audit-gate.yml 把 meta-monitor-report.json 作为 GitHub Actions artifact
上传。公开仓库的 artifact 可被任何人下载，而报告内含内部目录结构
(.governance/.openclaw 绝对路径、registry write_path、com.maref.* 服务名、
PID、内部 URL 等)。本脚本在上传前递归裁剪敏感字段并把残余路径字符串脱敏。

用法:
  python3 scripts/sanitize-meta-report.py <in.json> <out.json>
  省略输出参数时打印到 stdout。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# 直接丢弃的键：内部路径 / 结构 / 进程标识 / 详情描述
SENSITIVE_KEYS: frozenset[str] = frozenset({
    "path", "write_path", "newest_log", "issues", "url", "body", "error",
    "pid", "registry", "configured", "running", "dead", "unknown",
    "stale_agents", "detail", "source", "message", "title", "check_id",
    "subsystem", "last_report_timestamp", "mtime",
})

# 残余绝对路径 / 内部标识：即使出现在保留字段里也替换
SENSITIVE_RE = re.compile(
    r"/(Volumes|Users|private|Library|etc)/|com\.maref\.|127\.0\.0\.1"
    r"|\.openclaw|\.governance|\.maref_backups"
)


def redact(value: Any) -> Any:
    """递归清洗：删敏感键、替换敏感字符串；保留布尔/数值/汇总结构。"""
    if isinstance(value, str):
        return "[redacted]" if SENSITIVE_RE.search(value) else value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else ".openclaw/meta-monitor-report.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        with open(src, encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[sanitize] 读取报告失败: {e}", file=sys.stderr)
        return 2

    clean = redact(report)
    if dst is None:
        json.dump(clean, sys.stdout, indent=2, default=str)
    else:
        Path(dst).write_text(
            json.dumps(clean, indent=2, default=str), encoding="utf-8"
        )
        print(f"[sanitize] 已生成脱敏报告: {dst}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
