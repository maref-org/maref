#!/usr/bin/env python3
"""审计日志健康检查 (Phase Alpha A1) — 全域盘点模式 (P0 修复 RC-1/RC-5)

根因报告: docs/audit-reports/audit-stale-rootcause-verification-20260923.md

与旧版差异:
- 不再只盯 maref_config fallback 后的两个 repo 根文件（测试残留）
- 按 role 盘点全部已知链: production / sidecar / legacy_test_residue / registry
- blocking(生产链) 超龄或缺失 → issues（驱动 healthy=false）
- non-blocking(残留/声明路径) → warnings（不单独判死）
- 无生产 recursive 路径 → 结构性 issue NO_PRODUCTION_PATH，而非只报测试文件 STALE
- 顶层保留 governance_audit / recursive_governance_audit / probe_db 供晨报与循环日志兼容
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from maref_config import (
    AUDIT_LOG,
    REPO_DIR,
    audit_base,
    report_path,
)
from maref_config import (
    PROBE_DB as DB_PATH,
)
from maref_config import (
    RECURSIVE_AUDIT_LOG as RECURSIVE_LOG,
)

STALE_HOURS = 24.0


def _runtime_dir() -> Path:
    env = os.environ.get("MAREF_RUNTIME_DIR")
    return Path(env) if env else REPO_DIR


def _audit_base() -> Path:
    """audit_paths 注册表基目录（P2: 与 maref_config.audit_base 统一）。"""
    return audit_base()


def _hooks_chain() -> Path:
    return Path.home() / ".claude" / "hooks" / "state" / "governance_audit.jsonl"


def build_inventory() -> list[dict]:
    """全域审计链清单。blocking=True 的链参与 healthy 判定。

    P2: registry 与 production 路径去重（双路径收敛后常指向同一文件）。
    """
    runtime = _runtime_dir()
    base = _audit_base()
    config_gov = Path(AUDIT_LOG)
    config_rec = Path(RECURSIVE_LOG)
    # config 指到 repo 根且不在 runtime 下 → 历史测试/演示残留（RC-1）
    config_gov_residue = (
        config_gov == REPO_DIR / "governance_audit.jsonl"
        and runtime.resolve() != REPO_DIR.resolve()
    )
    config_rec_residue = (
        config_rec == REPO_DIR / "recursive_governance_audit.jsonl"
        and runtime.resolve() != REPO_DIR.resolve()
    )

    openclaw_sm = runtime / ".governance" / "governance_audit.jsonl"
    registry_gov = base / "governance_audit.jsonl"
    # 收敛后 registry 与 openclaw 主链同路径 → 不再单列 STALE 告警
    registry_is_alias = False
    try:
        registry_is_alias = registry_gov.resolve() == openclaw_sm.resolve()
    except OSError:
        registry_is_alias = registry_gov == openclaw_sm

    chains = [
        {
            "name": "hooks_agent",
            "role": "production",
            "blocking": True,
            "path": _hooks_chain(),
            "desc": "Claude/OpenCode PreToolUse 治理 hook 审计（真实活跃链）",
        },
        {
            "name": "openclaw_state_machine",
            "role": "production",
            "blocking": True,
            "path": openclaw_sm,
            "desc": "openclaw 状态机审计主链 (state_machine)",
        },
        {
            "name": "recursive_production",
            "role": "production",
            "blocking": True,
            "path": runtime / "recursive_governance_audit.jsonl",
            "alt_paths": (
                base / "recursive_governance_audit.jsonl",
                REPO_DIR / ".governance" / "recursive_governance_audit.jsonl",
            ),
            "desc": "递归治理生产链（RecursiveGovernanceOverlay 应写入）",
            "missing_issue": "NO_PRODUCTION_PATH (无生产写入方/路径未落地)",
        },
        {
            "name": "sidecar_claimed",
            "role": "sidecar",
            "blocking": False,
            "path": runtime / "governance_audit.jsonl",
            "desc": "governance-sidecar 启动时声称的审计路径（历史只打印未落盘）",
        },
        {
            "name": "config_monitored_governance",
            "role": "legacy_test_residue" if config_gov_residue else "config",
            "blocking": False,
            "path": config_gov,
            "desc": "maref_config.AUDIT_LOG（旧版健康检查唯一对象）",
        },
        {
            "name": "config_monitored_recursive",
            "role": "legacy_test_residue" if config_rec_residue else "config",
            "blocking": False,
            "path": config_rec,
            "desc": "maref_config.RECURSIVE_AUDIT_LOG（旧版健康检查唯一对象）",
        },
        {
            "name": "registry_audit_logger",
            "role": "registry_alias" if registry_is_alias else "registry",
            "blocking": False,
            "path": registry_gov,
            "desc": "audit_paths 注册表 audit_logger 写入路径 (MAREF_AUDIT_PATH)"
            + (" — 与 openclaw_state_machine 同路径（P2 收敛）" if registry_is_alias else ""),
            "skip_duplicate": registry_is_alias,
        },
        {
            "name": "registry_recursive",
            "role": "registry",
            "blocking": False,
            "path": base / "recursive_governance_audit.jsonl",
            "alt_paths": (
                runtime / "recursive_governance_audit.jsonl",
                REPO_DIR / ".governance" / "recursive_governance_audit.jsonl",
            ),
            "desc": "audit_paths 对应 recursive 路径（P2: 备路径=生产 recursive，去重 MISSING）",
        },
    ]
    return chains


def _probe_chain(path: Path) -> dict | None:
    """读取单链状态；文件不存在返回 None。"""
    if not path.exists() or not path.is_file():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None

    last = None
    line_count = 0
    try:
        with open(path, "rb") as f:
            if size <= 5_000_000:
                data = f.read().decode("utf-8", errors="replace").splitlines()
                line_count = len(data)
                for line in reversed(data):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        last = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            else:
                line_count = sum(1 for _ in f)
                f.seek(max(0, size - 300_000))
                tail = f.read().decode("utf-8", errors="replace").splitlines()
                for line in reversed(tail):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        last = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return {"size_mb": round(size / (1024 * 1024), 2), "hours_stale": 999.0}

    ts = last.get("timestamp") if last else None
    hours_stale = 999.0
    if ts is not None:
        try:
            last_dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            hours_stale = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
        except (OSError, ValueError, OverflowError, TypeError):
            hours_stale = 999.0

    actor = None
    if isinstance(last, dict):
        actor = last.get("actor") or last.get("agent_id")
    traffic = _classify_traffic(path, hours_stale)
    return {
        "size_mb": round(os.path.getsize(path) / (1024 * 1024), 2),
        "line_count": line_count,
        "last_entry_ts": float(ts) if ts is not None else None,
        "hours_stale": round(hours_stale, 1),
        "last_actor": actor,
        "traffic": traffic,
        "status": "STALE" if hours_stale > STALE_HOURS else "FRESH",
    }


def _classify_traffic(path: Path, hours_stale: float) -> str:
    """区分 heartbeat_only 与 real_traffic（P0/P1 语义）。

    在 STALE 窗口内采样尾部条目：若全部 metadata.source=heartbeat（或 action 含 heartbeat），
    返回 heartbeat_only；否则 real_traffic。读取失败返回 unknown。
    """
    if hours_stale > STALE_HOURS:
        # 已 STALE：不依赖窗口内条目，按最后条目粗分
        pass
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - 200_000))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return "unknown"

    now = datetime.now(timezone.utc).timestamp()
    window_start = now - STALE_HOURS * 3600
    sampled = 0
    heartbeat = 0
    for line in reversed(tail[-200:]):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = e.get("timestamp")
        try:
            if ts is not None and float(ts) < window_start:
                break
        except (TypeError, ValueError):
            pass
        sampled += 1
        meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        action = str(e.get("action", ""))
        if meta.get("source") == "heartbeat" or "heartbeat" in action.lower() or "HEARTBEAT" in action:
            heartbeat += 1
        if sampled >= 50:
            break
    if sampled == 0:
        return "unknown"
    return "heartbeat_only" if heartbeat == sampled else "real_traffic"


def _resolve_chain(entry: dict) -> tuple[Path | None, list[Path]]:
    """返回 (主路径, 备选路径)。recursive/registry 链任一路径存在即视为落地。"""
    primary = Path(entry["path"])
    alts = [Path(p) for p in entry.get("alt_paths", ())]
    if entry["name"] in ("recursive_production", "registry_recursive"):
        for candidate in [primary, *alts]:
            if candidate.exists():
                return candidate, alts
        return None, alts
    return primary, alts


def check_audit_health():
    now = datetime.now(timezone.utc)
    status: dict = {
        "checked_at": now.isoformat(),
        "mode": "inventory",
        "healthy": True,
        "issues": [],
        "warnings": [],
        "chains": [],
    }

    for entry in build_inventory():
        if entry.get("skip_duplicate"):
            # P2: registry 与 production 同文件时跳过重复告警
            resolved = Path(entry["path"])
            status["chains"].append(
                {
                    "name": entry["name"],
                    "role": entry["role"],
                    "blocking": entry["blocking"],
                    "desc": entry["desc"],
                    "path": str(resolved),
                    "alt_paths": [],
                    "status": "ALIAS_OF_PRODUCTION",
                }
            )
            continue
        resolved, alts = _resolve_chain(entry)
        record = {
            "name": entry["name"],
            "role": entry["role"],
            "blocking": entry["blocking"],
            "desc": entry["desc"],
            "path": str(resolved) if resolved else str(entry["path"]),
            "alt_paths": [str(p) for p in alts],
        }

        if resolved is None:
            # recursive 专项: 主/备路径全缺
            if entry["name"] == "recursive_production":
                record["status"] = "NO_PRODUCTION_PATH"
                issue = f"recursive_production: {entry.get('missing_issue', 'FILE_MISSING')}"
                if entry["blocking"]:
                    status["healthy"] = False
                    status["issues"].append(issue)
                else:
                    status["warnings"].append(issue)
            else:
                record["status"] = "MISSING"
                issue = f"{entry['name']}: FILE_MISSING"
                if entry["blocking"]:
                    status["healthy"] = False
                    status["issues"].append(issue)
                else:
                    status["warnings"].append(f"{issue} ({entry['role']})")
            status["chains"].append(record)
            continue

        probed = _probe_chain(resolved)
        if probed is None:
            record["status"] = "MISSING"
            issue = f"{entry['name']}: FILE_MISSING ({entry['role']})"
            if entry["blocking"]:
                status["healthy"] = False
                status["issues"].append(issue)
            else:
                status["warnings"].append(issue)
            status["chains"].append(record)
            continue

        record.update(probed)
        status["chains"].append(record)

        if probed["status"] == "STALE":
            tag = f"{entry['name']}: STALE_{probed['hours_stale']:.0f}h"
            if entry["blocking"]:
                status["healthy"] = False
                status["issues"].append(f"{tag} (production stalled >{STALE_HOURS:.0f}h)")
            else:
                status["warnings"].append(f"{tag} ({entry['role']}, non-blocking)")
        elif (
            probed["status"] == "FRESH"
            and probed.get("traffic") == "heartbeat_only"
            and entry["blocking"]
        ):
            # P0/P1: 心跳证明管道通，不判死；但标注无真实决策流量
            status["warnings"].append(
                f"{entry['name']}: FRESH but heartbeat_only (no real traffic in {STALE_HOURS:.0f}h window)"
            )

    # ── 兼容层: 顶层 governance_audit / recursive_governance_audit ──
    chains_by_name = {c["name"]: c for c in status["chains"]}

    gov_block = [chains_by_name.get("hooks_agent"), chains_by_name.get("openclaw_state_machine")]
    gov_present = [c for c in gov_block if c and c.get("hours_stale") is not None]
    gov = {
        "role": "production_summary",
        "monitored_paths": [c["path"] for c in gov_present],
        "chains_fresh": sum(1 for c in gov_present if c.get("status") == "FRESH"),
        "chains_total": len(gov_present),
    }
    if gov_present:
        worst = max(gov_present, key=lambda c: c.get("hours_stale") or 0)
        gov.update(
            {
                "size_mb": worst.get("size_mb"),
                "line_count": worst.get("line_count"),
                "last_entry_ts": worst.get("last_entry_ts"),
                "hours_stale": worst.get("hours_stale"),
                "status": worst.get("status"),
                "worst_chain": worst.get("name"),
            }
        )
    status["governance_audit"] = gov

    rec_prod = chains_by_name.get("recursive_production") or {}
    rec_legacy = chains_by_name.get("config_monitored_recursive") or {}
    recursive = {
        "role": "production_summary",
        "production_status": rec_prod.get("status", "UNKNOWN"),
        "production_path": rec_prod.get("path"),
        "legacy_path": rec_legacy.get("path"),
        "legacy_role": rec_legacy.get("role"),
        "legacy_hours_stale": rec_legacy.get("hours_stale"),
    }
    if rec_prod.get("hours_stale") is not None:
        recursive.update(
            {
                "size_mb": rec_prod.get("size_mb"),
                "line_count": rec_prod.get("line_count"),
                "last_entry_ts": rec_prod.get("last_entry_ts"),
                "hours_stale": rec_prod.get("hours_stale"),
                "status": rec_prod.get("status"),
            }
        )
    elif rec_legacy.get("hours_stale") is not None:
        recursive.update(
            {
                "hours_stale": rec_legacy.get("hours_stale"),
                "status": rec_legacy.get("status"),
                "note": "仅 legacy_test_residue 可读，非生产链",
            }
        )
    status["recursive_governance_audit"] = recursive

    status["resolution"] = {
        "runtime_dir": str(_runtime_dir()),
        "repo_dir": str(REPO_DIR),
        "audit_base": str(_audit_base()),
        "config_audit_log": str(AUDIT_LOG),
        "config_recursive_log": str(RECURSIVE_LOG),
    }

    # ── probe_db 对照组（进水口，独立于 JSONL 写链） ──
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT MAX(timestamp) FROM probe_readings")
        max_ts = c.fetchone()[0]
        conn.close()
        if max_ts:
            hours_stale = (now.timestamp() - max_ts) / 3600
            status["probe_db"] = {"last_reading_ts": max_ts, "hours_stale": round(hours_stale, 1)}
            if hours_stale > STALE_HOURS:
                status["healthy"] = False
                status["issues"].append(f"probe_db: STALE_{hours_stale:.0f}h")

    return status


def main():
    print("=" * 60)
    print("审计日志健康检查 (全域盘点模式 / P0)")
    print("=" * 60)

    status = check_audit_health()
    print(f"\n整体健康: {'✅ 正常' if status['healthy'] else '❌ 异常'}")

    print("\n审计链盘点:")
    for c in status["chains"]:
        age = c.get("hours_stale")
        age_s = f"{age}h" if age is not None else "-"
        blocking = "P" if c.get("blocking") else " "
        print(
            f"  [{blocking}] {c['status']:22} age={age_s:>8}  "
            f"{c['name']} ({c['role']}"
            f"{', ' + c['traffic'] if c.get('traffic') else ''})"
        )

    gov = status.get("governance_audit") or {}
    if gov.get("hours_stale") is not None:
        print(
            f"\ngovernance_audit (production summary): "
            f"{gov.get('status')} worst={gov.get('worst_chain')} "
            f"age={gov.get('hours_stale')}h fresh={gov.get('chains_fresh')}/{gov.get('chains_total')}"
        )
    rec = status.get("recursive_governance_audit") or {}
    print(
        f"\nrecursive_governance_audit: production={rec.get('production_status')} "
        f"legacy_age={rec.get('legacy_hours_stale')}h"
    )

    if status.get("probe_db"):
        print(f"\nprobe_db: {status['probe_db']['hours_stale']}h 前")

    if status["issues"]:
        print(f"\n⚠️ 阻断问题 {len(status['issues'])} 个:")
        for issue in status["issues"]:
            print(f"  - {issue}")
    if status.get("warnings"):
        print(f"\nℹ️ 非阻断警告 {len(status['warnings'])} 个:")
        for w in status["warnings"]:
            print(f"  - {w}")

    output = str(report_path("audit_health_check.json"))
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output}")


if __name__ == "__main__":
    main()
