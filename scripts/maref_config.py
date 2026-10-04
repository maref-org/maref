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
    """运行时目录探测。

    优先级: MAREF_RUNTIME_DIR 环境变量 > ~/.maref/runtime_dir.json > repo 自身。
    **不硬编码任何机器绝对路径**（Leak Detection CI 禁止 /Volumes 等内部卷路径）。
    真实运行时目录经 MAREF_RUNTIME_DIR 注入（launchd/cron），交互式会话
    回落持久化配置（T0-2: 消除交互跑/cycle 跑双口径）。
    """
    import json as _json

    env = os.environ.get("MAREF_RUNTIME_DIR")
    if env:
        return Path(env)
    cfg_path = Path.home() / ".maref" / "runtime_dir.json"
    try:
        cfg = _json.loads(cfg_path.read_text())
        candidate = cfg.get("runtime_dir")
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    except (OSError, ValueError, TypeError):
        pass
    return REPO_DIR


RUNTIME_DIR = _detect_runtime_dir()


def audit_base() -> Path:
    """P2 双路径收敛: 审计基目录唯一解析（与 maref._paths / audit_paths 对齐）。

    优先级: MAREF_AUDIT_PATH > RUNTIME_DIR/.governance > REPO_DIR/.governance
    """
    env = os.environ.get("MAREF_AUDIT_PATH")
    if env:
        p = Path(env)
        if p.suffix:
            p = p.parent
        return p if p.is_absolute() else (REPO_DIR / p)
    return RUNTIME_DIR / ".governance"

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
        audit_base() / "recursive_governance_audit.jsonl",
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
EXPERIENCE_DB = _env_path(
    "MAREF_EXPERIENCE_DB",
    RUNTIME_DIR / ".evolution_vault" / "experience.db",
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


def _load_env_file_keys(path: Path) -> dict[str, str]:
    """从 ~/.maref.env 读取 KEY=VALUE（不覆盖已有环境变量语义由调用方决定）。"""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def load_sidecar_api_key() -> str:
    """解析 sidecar Bearer token：env > ~/.maref.env > 空串。"""
    env_key = os.environ.get("MAREF_API_KEY", "").strip()
    if env_key:
        return env_key
    return _load_env_file_keys(Path.home() / ".maref.env").get("MAREF_API_KEY", "").strip()


def sidecar_auth_headers(content_type: str = "application/json") -> dict[str, str]:
    """构造 sidecar API 请求头（含 Bearer）。无 key 时仍返回 Content-Type（由调用方决定是否中止）。"""
    headers = {"Content-Type": content_type}
    key = load_sidecar_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def ensure_sidecar_api_key() -> str:
    """确保 ~/.maref.env 存在 MAREF_API_KEY；缺失则生成并追加（mode 0600）。返回 key。"""
    existing = load_sidecar_api_key()
    if existing:
        return existing
    import secrets

    new_key = secrets.token_urlsafe(32)
    env_path = Path.home() / ".maref.env"
    if env_path.exists():
        text = env_path.read_text()
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"MAREF_API_KEY={new_key}\n"
        env_path.write_text(text)
    else:
        env_path.write_text(f"MAREF_API_KEY={new_key}\n")
        env_path.chmod(0o600)
    os.environ["MAREF_API_KEY"] = new_key
    return new_key


def summary() -> dict:
    return {
        "runtime_dir": str(RUNTIME_DIR),
        "repo_dir": str(REPO_DIR),
        "audit_base": str(audit_base()),
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
