"""MAREF 治理工具链统一配置层 (P0-A)

消除硬编码路径/端口。优先级: 环境变量 > 自动探测 > 默认值。

设计:
- RUNTIME_DIR: 真实运行时目录(含审计日志/proposals/db/进化状态)
- REPO_DIR:    代码仓库目录(脚本/报告/配置生成物, 便于版本控制)
- 读资源(日志/db/proposals/进化状态) → RUNTIME_DIR 优先, fallback REPO_DIR
- 写产物(reports/configs/vaccine) → 始终 REPO_DIR

环境变量覆盖:
  MAREF_RUNTIME_DIR / MAREF_SIDECAR_URL / MAREF_AUDIT_LOG
  MAREF_RECURSIVE_AUDIT_LOG / MAREF_PROBE_DB / MAREF_PROPOSALS_DIR
  MAREF_EVOLUTION_STATE / MAREF_EVOLUTION_VAULT
  MAREF_REPORTS_DIR / MAREF_CONFIGS_DIR
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[-1]


def _detect_runtime_dir() -> Path:
    env = os.environ.get("MAREF_RUNTIME_DIR")
    if env:
        return Path(env)
    candidates = [Path("/Volumes/1TB-M2/openclaw"), REPO_DIR]
    for cand in candidates:
        if (cand / "governance_audit.jsonl").exists():
            return cand
    return REPO_DIR


RUNTIME_DIR = _detect_runtime_dir()

# ── 读资源(运行时优先) ──────────────────────────────
AUDIT_LOG = _env_path(
    "MAREF_AUDIT_LOG",
    _first_existing(RUNTIME_DIR / "governance_audit.jsonl", REPO_DIR / "governance_audit.jsonl"),
)
RECURSIVE_AUDIT_LOG = _env_path(
    "MAREF_RECURSIVE_AUDIT_LOG",
    _first_existing(
        RUNTIME_DIR / "recursive_governance_audit.jsonl",
        REPO_DIR / "recursive_governance_audit.jsonl",
    ),
)
PROBE_DB = _env_path(
    "MAREF_PROBE_DB",
    _first_existing(
        RUNTIME_DIR / "governance_observations.db", REPO_DIR / "governance_observations.db"
    ),
)
EVOLUTION_STATE = _env_path(
    "MAREF_EVOLUTION_STATE",
    _first_existing(
        RUNTIME_DIR / ".evolution_daemon_state.json", REPO_DIR / ".evolution_daemon_state.json"
    ),
)
EVOLUTION_VAULT = _env_path(
    "MAREF_EVOLUTION_VAULT",
    _first_existing(RUNTIME_DIR / ".evolution_vault", REPO_DIR / ".evolution_vault"),
)

# ── 生成物(始终 REPO_DIR) ────────────────────────────
AUDIT_LOG_V2 = REPO_DIR / "governance_audit_v2.jsonl"
RECURSIVE_AUDIT_LOG_V2 = REPO_DIR / "recursive_governance_audit_v2.jsonl"

REPORTS_DIR = _env_path("MAREF_REPORTS_DIR", REPO_DIR / "reports")
CONFIGS_DIR = _env_path("MAREF_CONFIGS_DIR", REPO_DIR / "configs")
VACCINE_DIR = REPO_DIR / "scripts" / "vaccine_pipeline"


def proposals_dir(create: bool = False) -> Path:
    env = os.environ.get("MAREF_PROPOSALS_DIR")
    if env:
        path = Path(env)
    else:
        path = _first_existing(
            RUNTIME_DIR / ".openclaw" / "evolution" / "proposals",
            REPO_DIR / ".openclaw" / "evolution" / "proposals",
        )
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def report_path(name: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR / name


def config_path(name: str) -> Path:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIGS_DIR / name


def vaccine_path(name: str) -> Path:
    return VACCINE_DIR / name


def _is_maref_sidecar(url: str, timeout: float = 0.5) -> bool:
    """按身份探测: MAREF sidecar 的 /api/version 返回 version 字段。"""
    import json
    import urllib.request

    try:
        resp = urllib.request.urlopen(f"{url}/api/version", timeout=timeout)
        data = json.loads(resp.read())
        return isinstance(data, dict) and "version" in data
    except Exception:
        return False


def sidecar_url() -> str:
    """探测可用的 MAREF sidecar 地址。环境变量 > 身份探测 > 默认。"""
    env = os.environ.get("MAREF_SIDECAR_URL")
    if env:
        return env.rstrip("/")
    for url in ("http://127.0.0.1:8931", "http://127.0.0.1:8000"):
        if _is_maref_sidecar(url):
            return url
    return "http://127.0.0.1:8000"


def summary() -> dict:
    return {
        "runtime_dir": str(RUNTIME_DIR),
        "repo_dir": str(REPO_DIR),
        "audit_log": str(AUDIT_LOG),
        "recursive_audit_log": str(RECURSIVE_AUDIT_LOG),
        "probe_db": str(PROBE_DB),
        "proposals_dir": str(proposals_dir()),
        "evolution_state": str(EVOLUTION_STATE),
        "sidecar_url": sidecar_url(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(summary(), indent=2, ensure_ascii=False))
