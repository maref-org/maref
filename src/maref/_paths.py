"""
MAREF 路径解析公共模块

提供统一的项目路径和审计日志路径解析，消除 22 个文件的路径分裂。
修复 A5 审计日志路径分裂（OPC全流程缺口审计-20260726 P0 阻断性 bug）。

历史：3 个文件引用 maref._paths 但模块不存在，导致导入即崩溃。
  - src/maref/flywheel/improvement_detector.py
  - src/maref/flywheel/sanitizer.py
  - src/maref/opc/sanitizer.py

统一路径：<project_root>/.governance/audit/governance_audit.jsonl
"""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """返回项目根目录。

    解析优先级:
    1. MAREF_PROJECT_ROOT 环境变量
    2. 从本文件位置向上回溯到 openclaw 根目录（含 pyproject.toml）
    3. Path.cwd() fallback
    """
    env_root = os.environ.get("MAREF_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    here = Path(__file__).resolve().parent
    candidate = here.parent.parent  # maref/ -> src/ -> openclaw/
    if (candidate / "pyproject.toml").exists():
        return candidate

    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent

    return Path.cwd()


def get_local_root() -> Path:
    """返回用户家目录（用于 sanitizer.py 路径脱敏的 $LOCAL_ROOT 占位）。"""
    return Path.home()


def get_governance_base() -> Path:
    """返回治理审计基目录（绝对路径）。

    统一 .governance 相对默认值（消除 CWD 依赖，修复 A5 路径分裂根因）。

    解析优先级 (P2 双路径收敛):
    1. MAREF_AUDIT_PATH 环境变量（兼容目录或文件语义；指向文件时取父目录）
    2. <MAREF_RUNTIME_DIR>/.governance（生产运行时，与 maref_config 对齐）
    3. <project_root>/.governance
    """
    env_path = os.environ.get("MAREF_AUDIT_PATH")
    if env_path:
        p = Path(env_path)
        if p.suffix:  # 指向文件时取父目录
            p = p.parent
        return p

    runtime = os.environ.get("MAREF_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / ".governance"

    return get_project_root() / ".governance"


def get_meta_base() -> Path:
    """返回 meta-monitor/health/pulse 基目录（绝对路径）。

    统一 .openclaw 相对默认值（消除 CWD 依赖）。

    解析优先级:
    1. MAREF_META_PATH 环境变量
    2. <project_root>/.openclaw
    """
    env_path = os.environ.get("MAREF_META_PATH")
    if env_path:
        return Path(env_path)
    return get_project_root() / ".openclaw"


def get_audit_dir() -> Path:
    """返回审计目录。

    解析优先级:
    1. MAREF_AUDIT_PATH 环境变量（统一为目录语义）
    2. <project_root>/.governance/audit/
    """
    env_path = os.environ.get("MAREF_AUDIT_PATH")
    if env_path:
        p = Path(env_path)
        if p.suffix:  # 兼容 config.py 旧语义：指向文件时取父目录
            p = p.parent
        return p

    return get_project_root() / ".governance" / "audit"


def get_audit_log_path(filename: str = "governance_audit.jsonl") -> Path:
    """返回审计日志文件完整路径。自动创建父目录。"""
    path = get_audit_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_legacy_audit_paths() -> list[Path]:
    """返回历史分裂路径列表，供读取方 fallback 兼容。"""
    root = get_project_root()
    return [
        get_audit_log_path(),
        root / ".governance" / "governance_audit.jsonl",
        root / "governance_audit.jsonl",
        Path.cwd() / "governance_audit.jsonl",
        Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl",
    ]


def get_photo_dir() -> Path:
    """返回推广照片目录（兼容 backends.py 调用）。"""
    path = get_project_root() / "ip-kingdom" / "visual-assets" / "portraits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_photo_path(filename: str = "") -> Path:
    """返回推广照片文件路径（兼容 backends.py 调用）。"""
    return get_photo_dir() / filename if filename else get_photo_dir()
