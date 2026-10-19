"""MAREF 路径解析公共模块（单一真相源 / SSOT）。

统一项目根目录、治理审计目录与元监控目录的解析，消除路径分裂。

解析优先级统一为「显式环境变量 > 运行时目录 > 项目根默认值」，
所有函数返回绝对路径，避免依赖当前工作目录（CWD）。

历史说明：本模块曾在 OSS 裁剪中被误删（0ab36e19），导致 meta-monitor
等模块导入即崩溃。本文件是运行时依赖，不得加入 OSS 排除清单。
"""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """返回项目根目录。

    解析优先级:
    1. MAREF_PROJECT_ROOT 环境变量
    2. 从本文件位置向上回溯到含 pyproject.toml 的目录
    3. Path.cwd() fallback
    """
    env_root = os.environ.get("MAREF_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    here = Path(__file__).resolve().parent
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent

    return Path.cwd().resolve()


def get_local_root() -> Path:
    """返回用户家目录（用于路径脱敏的 $LOCAL_ROOT 占位）。"""
    return Path.home()


def get_governance_base() -> Path:
    """返回治理审计基目录（绝对路径）。

    解析优先级:
    1. MAREF_AUDIT_PATH 环境变量（兼容目录或文件语义；指向文件时取父目录）
    2. <MAREF_RUNTIME_DIR>/.governance
    3. <project_root>/.governance
    """
    env_path = os.environ.get("MAREF_AUDIT_PATH")
    if env_path:
        p = Path(env_path)
        if p.suffix:
            p = p.parent
        return p.resolve()

    runtime = os.environ.get("MAREF_RUNTIME_DIR")
    if runtime:
        return (Path(runtime) / ".governance").resolve()

    return (get_project_root() / ".governance").resolve()


def get_meta_base() -> Path:
    """返回 meta-monitor 数据基目录（报告 / 通知 / 反馈状态）。

    解析优先级:
    1. MAREF_META_PATH 环境变量
    2. <project_root>/.governance/meta

    历史路径 <project_root>/.openclaw 仅通过 get_legacy_meta_base() 读取，
    写入端不得再使用该路径。
    """
    env_path = os.environ.get("MAREF_META_PATH")
    if env_path:
        return Path(env_path).resolve()
    return (get_project_root() / ".governance" / "meta").resolve()


def get_legacy_meta_base() -> Path:
    """返回历史 meta 目录（仅用于迁移期读取，禁止写入）。"""
    return (get_project_root() / ".openclaw").resolve()


def get_audit_dir() -> Path:
    """返回审计目录。

    解析优先级:
    1. MAREF_AUDIT_PATH 环境变量（统一为目录语义）
    2. <project_root>/.governance/audit/
    """
    env_path = os.environ.get("MAREF_AUDIT_PATH")
    if env_path:
        p = Path(env_path)
        if p.suffix:
            p = p.parent
        return p.resolve()

    return (get_project_root() / ".governance" / "audit").resolve()


def get_audit_log_path(filename: str = "governance_audit.jsonl") -> Path:
    """返回审计日志文件完整路径。自动创建父目录。"""
    path = get_audit_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_legacy_audit_paths() -> list[Path]:
    """返回历史分裂路径列表，供读取方迁移期 fallback 兼容。

    写入端必须只使用 get_governance_base()，不得写入以下路径。
    """
    root = get_project_root()
    return [
        get_governance_base() / "governance_audit.jsonl",
        get_audit_dir() / "governance_audit.jsonl",
        root / "governance_audit.jsonl",
        Path.cwd() / "governance_audit.jsonl",
        Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl",
    ]
