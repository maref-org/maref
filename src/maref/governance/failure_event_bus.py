#!/usr/bin/env python3
"""失败事件统一入口（双仓补全方案 Phase 1.1 / 1.3 / 1.7）。

单一事实源: 战略 maref_capability_completion_strategy.md §5.1 信号 schema、
§6 指标定义（自愈率/复发率/升级率/MTTR）。

  record   写一行结构化失败/摩擦信号 + fingerprint + 截图归档 + agent_bus 广播
  resolve  标记自愈成功（供 MTTR / 自愈率）
  escalate 标记升级人工
  judge    <fp> --needed/--not-needed [--minutes N] 升级决策人工评审（升级精度/人工分钟）
  list     按 fp / signal / 时间窗列出事件
  replay   <fp> 回放: 事件 + 截图 + 轨迹步
  stats    四指标 + 三扩展指标（升级精度/人工分钟[proxy]/归因准确率）

退出码: 0 成功 / 1 参数或数据错误 / 2 目标不存在
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

try:  # py<3.11 无 datetime.UTC（默认 /usr/bin/python3=3.9 兼容）
    from datetime import UTC
except ImportError:  # pragma: no cover
    from datetime import timezone

    UTC = timezone.utc

ROOT = Path(__file__).resolve().parent.parent
# 环境变量可覆盖（测试沙箱/隔离演练用；不设则落仓库默认目录）
EVENTS_DIR = Path(os.environ.get("FAILURE_EVENT_DIR") or (ROOT / ".openclaw" / "failure_events"))
EVENTS = EVENTS_DIR / "events.jsonl"
ARTIFACTS = Path(
    os.environ.get("FAILURE_ARTIFACTS_DIR") or (ROOT / ".openclaw" / "failure_artifacts")
)
TRAJ_DIR = ROOT / ".openclaw" / "trajectories"
STATE = EVENTS_DIR / "state.json"

SCHEMA_VERSION = "1.0"
SIGNALS = ("friction", "failure", "waste", "stagnation", "silence", "surprise")
OUTCOMES = ("open", "recovered", "escalated", "unresolved")
BUS_TYPE = (
    "governance_failure"  # 语义 topic = governance.failure（总线事件类型只允许 [A-Za-z0-9_]）
)
FP_LEN = 12

_RE_TS = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?",
    re.IGNORECASE,
)
_RE_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_RE_HEX = re.compile(r"\b[0-9a-f]{8,}\b")
_RE_PATH = re.compile(r"(/[\w.\-]+){2,}")
_RE_NUM = re.compile(r"\d{4,}")


def normalize_signature(text: str) -> str:
    """把易变细节（时间戳/哈希/路径/大数字）抹平，使同一类失败得到同一 fingerprint。"""
    s = str(text or "").strip().lower()
    s = _RE_UUID.sub("<uuid>", s)
    s = _RE_TS.sub("<ts>", s)
    s = _RE_PATH.sub("<path>", s)
    s = _RE_HEX.sub("<hex>", s)
    s = _RE_NUM.sub("<n>", s)
    return re.sub(r"\s+", " ", s).strip()[:400]


def make_fingerprint(signal: str, signature: str) -> str:
    material = f"{signal}|{normalize_signature(signature)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:FP_LEN]


def _judge_file() -> Path:
    """升级决策评审账本（动态基于 EVENTS_DIR，self-check 沙箱自动跟随）。"""
    return EVENTS_DIR / "judge_reviews.jsonl"


def _attr_file() -> Path:
    """归因人工复核账本（failure_attribution.verify 同文件写入）。"""
    return EVENTS_DIR / "attribution_reviews.jsonl"


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_jsonl(path: Path, since: datetime | None = None) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if since is not None:
            try:
                if datetime.fromisoformat(str(rec.get("ts", "")).replace("Z", "+00:00")) < since:
                    continue
            except ValueError:
                continue
        out.append(rec)
    return out


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_events(
    fp: str | None = None, since: datetime | None = None, collapse: bool = False
) -> list[dict]:
    if not EVENTS.exists():
        return []
    out: list[dict] = []
    for ln in EVENTS.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if fp and rec.get("fingerprint") != fp:
            continue
        if since is not None:
            try:
                if datetime.fromisoformat(str(rec.get("ts", "")).replace("Z", "+00:00")) < since:
                    continue
            except ValueError:
                continue
        out.append(rec)
    if collapse:
        out = _collapse(out)
    return out


def _collapse(rows: list[dict]) -> list[dict]:
    """append-only 账本按 event_id 折叠，末条状态覆盖旧状态（计数不被状态更新虚增）。"""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        key = str(r.get("event_id") or id(r))
        if key not in merged:
            order.append(key)
        merged[key] = r
    return [merged[k] for k in order]


def _append(rec: dict) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _artifact_dir(fp: str) -> Path:
    d = ARTIFACTS / fp
    d.mkdir(parents=True, exist_ok=True)
    return d


def _publish_bus(rec: dict) -> dict:
    """尽力广播到 agent_bus；总线不可用不阻断落库（落库是事实源）。"""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "agent_bus", Path(__file__).resolve().parent / "agent_bus.py"
        )
        if spec is None or spec.loader is None:
            return {"published": False, "reason": "agent_bus_unavailable"}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bus = mod.AgentBus() if hasattr(mod, "AgentBus") else mod.Bus()
        bus.publish(
            BUS_TYPE,
            rec.get("agent_id") or "failure_event_bus",
            payload={
                "fingerprint": rec.get("fingerprint"),
                "signal": rec.get("signal"),
                "task_id": rec.get("task_id"),
                "class": rec.get("class"),
                "detail": str(rec.get("detail", ""))[:200],
                "ts": rec.get("ts"),
            },
        )
        return {"published": True, "topic": BUS_TYPE}
    except Exception as exc:  # noqa: BLE001 — 广播失败不污染落库
        return {"published": False, "reason": type(exc).__name__}


def latest_screenshot(max_age_seconds: int = 21600) -> str:
    """取最近一次视觉反馈截图（/tmp/adb_vf_*.png），失败分支可零改动补图。"""
    try:
        cands = sorted(Path("/tmp").glob("adb_vf_*.png"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return ""
    cutoff = time.time() - max_age_seconds
    for p in reversed(cands):
        try:
            if p.stat().st_size > 0 and p.stat().st_mtime >= cutoff:
                return str(p)
        except OSError:
            continue
    return ""


def record(
    signal: str,
    agent_id: str,
    *,
    task_id: str = "",
    step: int | None = None,
    context_hash: str = "",
    detail: str = "",
    signature: str = "",
    fingerprint: str = "",
    source: str = "",
    failure_class: str = "",
    screenshot: str | Path = "",
    auto_screenshot: bool = False,
    bus: bool = True,
    outcome: str = "open",
    dedupe: bool = True,
) -> dict:
    if auto_screenshot and not screenshot:
        screenshot = latest_screenshot()
    if signal not in SIGNALS:
        raise ValueError(f"signal 必须 ∈ {SIGNALS}")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome 必须 ∈ {OUTCOMES}")
    fp = fingerprint or make_fingerprint(signal, signature or detail or task_id)
    if not fp:
        raise ValueError("fingerprint 为空：请提供 signature/detail/task_id 之一")

    if dedupe:
        for ev in load_events(fp=fp, collapse=True):
            if ev.get("task_id") == task_id and ev.get("signal") == signal:
                return {"skipped": True, "reason": "duplicate", "event": ev}

    ts = _now_iso()
    screenshot_ref = ""
    if screenshot:
        src = Path(screenshot)
        if src.exists():
            dst = _artifact_dir(fp) / f"{int(time.time() * 1000)}_{src.name}"
            try:
                shutil.copy2(src, dst)
                try:
                    screenshot_ref = str(dst.relative_to(ROOT))
                except ValueError:  # 沙箱/临时目录下的产物保留绝对路径
                    screenshot_ref = str(dst)
            except OSError as exc:
                screenshot_ref = f"copy_failed:{type(exc).__name__}"

    rec = {
        "schema_version": SCHEMA_VERSION,
        "event_id": uuid.uuid4().hex[:16],
        "signal": signal,
        "fingerprint": fp,
        "agent_id": agent_id,
        "task_id": task_id,
        "step": step,
        "context_hash": context_hash,
        "screenshot_ref": screenshot_ref,
        "class": failure_class,
        "source": source,
        "detail": str(detail)[:2000],
        "outcome": outcome,
        "recovered_at": None,
        "escalated_to": "",
        "actor": "",
        "ts": ts,
    }
    _append(rec)
    if bus:
        rec["bus"] = _publish_bus(rec)
    return {"skipped": False, "event": rec}


def judge(fp: str, verdict: str, minutes: float = 0.0, reviewer: str = "human") -> dict:
    """升级决策人工评审（战略 §6 escalation_precision / human_minutes 数据源）。

    needed = 该次升级人工判断正确；not_needed = 升级为误报/过度升级。
    minutes = 本次评审/处置花费的人工分钟（估算值，stats 标注 proxy）。
    """
    if verdict not in ("needed", "not_needed"):
        raise ValueError("verdict 必须 needed / not_needed")
    if minutes < 0:
        raise ValueError("minutes 不能为负")
    rows = load_events(fp=fp, collapse=True)
    if not rows:
        return {"error": "not_found", "fingerprint": fp}
    row = {
        "fp": fp,
        "verdict": verdict,
        "minutes": round(float(minutes), 2),
        "reviewer": reviewer,
        "ts": _now_iso(),
    }
    _append_jsonl(_judge_file(), row)
    return row


def mark(fp: str, outcome: str, actor: str = "", note: str = "") -> dict:
    if outcome not in ("recovered", "escalated", "unresolved"):
        raise ValueError("outcome 只支持 recovered / escalated / unresolved")
    rows = load_events(fp=fp, collapse=True)
    if not rows:
        return {"error": "not_found", "fingerprint": fp}
    target = None
    for r in reversed(rows):
        if r.get("outcome") == "open":
            target = r
            break
    if target is None:
        target = rows[-1]
    target["outcome"] = outcome
    target["actor"] = actor
    target["recovered_at"] = _now_iso() if outcome == "recovered" else None
    if note:
        target["detail"] = f"{target.get('detail', '')} | {note}"[:2000]
    _append(target)  # append-only: 事件账本不改写历史，末条状态以最后一次为准
    return {"updated": True, "event": target}


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def replay(fp: str) -> dict:
    events = load_events(fp=fp, collapse=True)
    if not events:
        return {"error": "not_found", "fingerprint": fp}
    art_dir = ARTIFACTS / fp
    shots: list[str] = []
    if art_dir.exists():
        for p in sorted(art_dir.glob("*")):
            try:
                shots.append(str(p.relative_to(ROOT)))
            except ValueError:
                shots.append(str(p))
    steps: list[dict] = []
    sessions = {e.get("task_id") for e in events if e.get("task_id")}
    for sid in sessions:
        direct = TRAJ_DIR / "opencode" / f"{sid}.jsonl"
        shards = [direct] if direct.exists() else sorted(TRAJ_DIR.glob("????-??-??.jsonl"))
        for shard in shards:
            if not shard.exists():
                continue
            for ln in shard.read_text(errors="replace").splitlines():
                ln = ln.strip()
                if not ln or f'"{sid}"' not in ln:
                    continue
                try:
                    d = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if d.get("session_id") == sid:
                    steps.append(d)
    steps.sort(key=lambda r: r.get("seq", 0))
    return {
        "fingerprint": fp,
        "events": events,
        "screenshots": shots,
        "trajectory_steps": len(steps),
        "steps": steps[:200],
        "replayable": bool(events) and bool(shots) and bool(steps),
        "note": "replayable 要求 事件+截图+轨迹步 三者齐备（战略§4 验收口径）",
    }


def stats(days: int = 0) -> dict:
    since = datetime.now(UTC) - timedelta(days=days) if days else None
    rows = load_events(since=since, collapse=True)
    failures = [r for r in rows if r.get("signal") == "failure"]
    outcome = {}
    for r in failures:
        outcome[r.get("outcome", "open")] = outcome.get(r.get("outcome", "open"), 0) + 1
    resolved = outcome.get("recovered", 0) + outcome.get("escalated", 0)
    recovered = outcome.get("recovered", 0)
    escalated = outcome.get("escalated", 0)
    total_fail = len(failures)

    counts: dict[str, int] = {}
    for r in failures:
        counts[r.get("fingerprint", "")] = counts.get(r.get("fingerprint", ""), 0) + 1
    recurrence = sum(1 for r in failures if counts.get(r.get("fingerprint", ""), 0) >= 2)

    with_shot = sum(1 for r in failures if r.get("screenshot_ref"))
    screenshot_coverage = round(with_shot / total_fail, 4) if total_fail else None

    mttr_min: float | None = None
    deltas = []
    for r in failures:
        if r.get("outcome") != "recovered":
            continue
        t0, t1 = _parse_ts(r.get("ts", "")), _parse_ts(r.get("recovered_at") or "")
        if t0 and t1:
            deltas.append((t1 - t0).total_seconds() / 60.0)
    if deltas:
        mttr_min = round(statistics.median(deltas), 2)

    # ── 批次 A3 扩展指标（战略 §6）─────────────────────────────
    jrows = _load_jsonl(_judge_file(), since=since)
    n_needed = sum(1 for j in jrows if j.get("verdict") == "needed")
    n_not = sum(1 for j in jrows if j.get("verdict") == "not_needed")
    n_judge = n_needed + n_not
    escalation_precision = round(n_needed / n_judge, 4) if n_judge else None

    minutes_total = round(sum(float(j.get("minutes") or 0) for j in jrows), 2)
    win_days = days or None
    # 无评审数据 = 未采集（null），有数据才按窗口出值（区别"真 0 分钟"与"没跑度量"）
    human_minutes_per_day = (
        round(minutes_total / win_days, 2) if (win_days and win_days > 0 and n_judge) else None
    )

    arows = _load_jsonl(_attr_file(), since=since)
    n_correct = sum(1 for a in arows if a.get("verdict") == "correct")
    n_wrong = sum(1 for a in arows if a.get("verdict") == "wrong")
    n_attr = n_correct + n_wrong
    attribution_accuracy = round(n_correct / n_attr, 4) if n_attr else None

    return {
        "window_days": days or "all",
        "total_events": len(rows),
        "failure_events": total_fail,
        "outcome": outcome,
        "self_heal_rate": round(recovered / resolved, 4) if resolved else None,
        "recurrence_rate": round(recurrence / total_fail, 4) if total_fail else None,
        "escalation_rate": round(escalated / total_fail, 4) if total_fail else None,
        "mttr_minutes": mttr_min,
        "screenshot_coverage": screenshot_coverage,
        "escalation_precision": escalation_precision,
        "human_minutes_per_day": human_minutes_per_day,
        "human_minutes_is_proxy": True,
        "attribution_accuracy": attribution_accuracy,
        "denominators": {
            "self_heal": resolved,
            "recurrence": total_fail,
            "escalation": total_fail,
            "mttr": len(deltas),
            "screenshot": total_fail,
            "judge_precision": n_judge,
            "human_minutes_days": win_days,
            "attribution": n_attr,
        },
        "note": "分母为 0 时指标诚实返回 null（战略§6：不假 0）；human_minutes 为人工估算 proxy",
    }


def write_report(res: dict, date_s: str = "") -> Path:
    """A5: 每日指标报告落 .openclaw/reports/failure_bus/YYYY-MM-DD.md（同日覆盖，幂等）。"""
    date_s = date_s or datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = ROOT / ".openclaw" / "reports" / "failure_bus"
    out_dir.mkdir(parents=True, exist_ok=True)
    d = res["denominators"]
    lines = [
        f"# 失败总线日报 {date_s}",
        "",
        f"窗口: {res['window_days']} 天  事件: {res['total_events']} (failure {res['failure_events']})",
        "",
        "| 指标 | 值 | 分母 |",
        "|---|---|---|",
        f"| 自愈率 | {res['self_heal_rate']} | {d['self_heal']} |",
        f"| 复发率 | {res['recurrence_rate']} | {d['recurrence']} |",
        f"| 升级率 | {res['escalation_rate']} | {d['escalation']} |",
        f"| MTTR (min) | {res['mttr_minutes']} | {d['mttr']} |",
        f"| 截图覆盖率 | {res['screenshot_coverage']} | {d['screenshot']} |",
        f"| 升级精度 | {res['escalation_precision']} | {d['judge_precision']} |",
        f"| 人工分钟/日 (proxy) | {res['human_minutes_per_day']} | {d['human_minutes_days']} |",
        f"| 归因准确率 | {res['attribution_accuracy']} | {d['attribution']} |",
        "",
        f"outcome: {res['outcome']}",
        "",
        f"> {res['note']}",
        "",
    ]
    fp = out_dir / f"{date_s}.md"
    fp.write_text("\n".join(lines), encoding="utf-8")
    return fp


def record_from_rewards(rows: list[dict]) -> dict:
    """trajectory_reward_mix FAILURE 回写（Phase 1.1 接线点）。"""
    written, skipped, errors = 0, 0, 0
    for r in rows:
        if r.get("label") != "FAILURE":
            continue
        ev = (r.get("evidence") or {}).get("programmatic") or {}
        sig = ev.get("verify_cmd") or ev.get("verify_name") or r.get("title") or ""
        try:
            res = record(
                "failure",
                "trajectory_reward_mix",
                task_id=str(r.get("session_id", "")),
                signature=f"{ev.get('verify_name', '')}:{ev.get('exit', '')}|{sig}",
                detail=str(r.get("title") or ""),
                source="trajectory_reward_mix",
                bus=False,
            )
            skipped += 1 if res.get("skipped") else 0
            written += 0 if res.get("skipped") else 1
        except Exception:  # noqa: BLE001
            errors += 1
    return {"written": written, "skipped_duplicate": skipped, "errors": errors}


def self_check() -> int:
    import tempfile

    global EVENTS_DIR, EVENTS, ARTIFACTS, STATE
    backup = (EVENTS_DIR, EVENTS, ARTIFACTS, STATE)
    tmp = Path(tempfile.mkdtemp(prefix="feb_selfcheck_"))
    try:
        EVENTS_DIR = tmp / "failure_events"
        EVENTS = EVENTS_DIR / "events.jsonl"
        ARTIFACTS = tmp / "failure_artifacts"
        STATE = EVENTS_DIR / "state.json"

        assert make_fingerprint(
            "failure", "pytest exit=1 at 2026-10-04T10:00:00Z"
        ) == make_fingerprint("failure", "pytest exit=1 at 2026-10-05T22:31:07Z"), (
            "fingerprint 未吸收时间戳"
        )
        assert make_fingerprint("failure", "x") != make_fingerprint("friction", "x"), (
            "signal 未入指纹"
        )

        r1 = record("failure", "unit", task_id="t1", signature="pytest:1", bus=False)
        assert not r1["skipped"] and r1["event"]["fingerprint"], "record 失败"
        r2 = record("failure", "unit", task_id="t1", signature="pytest:1", bus=False)
        assert r2["skipped"], "同 fp+task 去重失效"
        r3 = record("failure", "unit", task_id="t2", signature="pytest:1", bus=False)
        assert not r3["skipped"], "跨任务复发被误去重"

        fp = r1["event"]["fingerprint"]
        m = mark(fp, "recovered", actor="unit")
        assert m["event"]["outcome"] == "recovered" and m["event"]["recovered_at"], "resolve 失败"
        s = stats(days=0)
        assert s["self_heal_rate"] == 1.0 and s["mttr_minutes"] is not None, f"stats 异常 {s}"
        assert s["recurrence_rate"] == 1.0, f"复发率应为 1.0 {s}"
        rp = replay(fp)
        assert rp["events"], "replay 无事件"
        print("failure_event_bus.self_check: OK")
        return 0
    finally:
        EVENTS_DIR, EVENTS, ARTIFACTS, STATE = backup
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="失败事件统一入口（Phase 1.1/1.3/1.7）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record", help="写入一条信号事件")
    p.add_argument("--signal", required=True, choices=SIGNALS)
    p.add_argument("--agent", required=True, help="agent_id")
    p.add_argument("--task", default="", help="task_id / session_id")
    p.add_argument("--step", type=int, default=None)
    p.add_argument("--context-hash", default="")
    p.add_argument("--detail", default="")
    p.add_argument("--signature", default="", help="指纹签名源（同类失败应同签名）")
    p.add_argument("--fp", default="", help="显式 fingerprint（跳过推导）")
    p.add_argument("--source", default="")
    p.add_argument("--class", dest="failure_class", default="", help="E1-E5（Phase 2 归因回写）")
    p.add_argument("--screenshot", default="", help="截图路径（复制入 failure_artifacts/<fp>/）")
    p.add_argument("--outcome", default="open", choices=OUTCOMES)
    p.add_argument("--auto-screenshot", action="store_true", help="自动附最近一次视觉反馈截图")
    p.add_argument("--no-bus", action="store_true", help="不广播 agent_bus")
    p.add_argument("--no-dedupe", action="store_true")

    p = sub.add_parser("resolve", help="标记自愈成功")
    p.add_argument("fp")
    p.add_argument("--by", default="human")
    p.add_argument("--note", default="")

    p = sub.add_parser("escalate", help="标记升级人工")
    p.add_argument("fp")
    p.add_argument("--to", default="human")
    p.add_argument("--note", default="")

    p = sub.add_parser("judge", help="升级决策人工评审（升级精度/人工分钟数据源）")
    p.add_argument("fp")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--needed", action="store_true", help="升级判断正确")
    g.add_argument("--not-needed", action="store_true", help="升级为误报/过度升级")
    p.add_argument("--minutes", type=float, default=0.0, help="本次处置人工分钟（估算）")
    p.add_argument("--by", default="human", help="评审人")

    p = sub.add_parser("list", help="列出事件")
    p.add_argument("--fp", default="")
    p.add_argument("--signal", default="", choices=SIGNALS)
    p.add_argument("--days", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("replay", help="按 fingerprint 回放")
    p.add_argument("fp")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("stats", help="四指标 + 三扩展指标")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--write-report",
        action="store_true",
        help="落 .openclaw/reports/failure_bus/YYYY-MM-DD.md（A5 日报）",
    )

    sub.add_parser("self-check", help="自检（隔离临时目录）")

    args = ap.parse_args()

    if args.cmd == "self-check":
        return self_check()

    if args.cmd == "record":
        res = record(
            args.signal,
            args.agent,
            task_id=args.task,
            step=args.step,
            context_hash=args.context_hash,
            detail=args.detail,
            signature=args.signature,
            fingerprint=args.fp,
            source=args.source,
            failure_class=args.failure_class,
            screenshot=args.screenshot,
            auto_screenshot=args.auto_screenshot,
            bus=not args.no_bus,
            outcome=args.outcome,
            dedupe=not args.no_dedupe,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 2 if res.get("error") else 0

    if args.cmd in ("resolve", "escalate"):
        res = mark(
            args.fp,
            "recovered" if args.cmd == "resolve" else "escalated",
            actor=getattr(args, "by", "") or getattr(args, "to", ""),
            note=args.note,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0 if res.get("updated") else 2

    if args.cmd == "judge":
        res = judge(
            args.fp,
            "needed" if args.needed else "not_needed",
            minutes=args.minutes,
            reviewer=args.by,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 2 if res.get("error") else 0

    if args.cmd == "list":
        since = datetime.now(UTC) - timedelta(days=args.days) if args.days else None
        rows = list(load_events(fp=args.fp or None, since=since, collapse=True))
        if args.signal:
            rows = [r for r in rows if r.get("signal") == args.signal]
        rows = rows[-args.limit :]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for r in rows:
                print(
                    f"{r.get('ts', '')[:19]}  {r.get('signal', ''):10s} "
                    f"{r.get('fingerprint', '')}  {r.get('outcome', ''):10s} "
                    f"{r.get('agent_id', '')}/{r.get('task_id', '')}  "
                    f"{str(r.get('detail', ''))[:60]}"
                )
            print(f"（{len(rows)} 条）")
        return 0

    if args.cmd == "replay":
        res = replay(args.fp)
        if res.get("error"):
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 2
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"fingerprint: {res['fingerprint']}")
            print(
                f"事件: {len(res['events'])}  截图: {len(res['screenshots'])}  轨迹步: {res['trajectory_steps']}"
            )
            for e in res["events"]:
                print(
                    f"  [{e.get('ts', '')[:19]}] {e.get('signal')} {e.get('outcome')} {e.get('detail', '')[:80]}"
                )
            for s in res["screenshots"]:
                print(f"  截图: {s}")
            print(f"  可回放: {res['replayable']}")
        return 0 if res["events"] else 2

    if args.cmd == "stats":
        res = stats(days=args.days)
        if args.write_report:
            res["report_path"] = str(write_report(res))
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(
                f"窗口: {res['window_days']}  事件: {res['total_events']} (failure {res['failure_events']})"
            )
            print(f"  自愈率: {res['self_heal_rate']} (n={res['denominators']['self_heal']})")
            print(f"  复发率: {res['recurrence_rate']} (n={res['denominators']['recurrence']})")
            print(f"  升级率: {res['escalation_rate']} (n={res['denominators']['escalation']})")
            print(f"  MTTR:   {res['mttr_minutes']} min (n={res['denominators']['mttr']})")
            print(
                f"  升级精度: {res['escalation_precision']} (n={res['denominators']['judge_precision']})"
            )
            print(
                f"  人工分钟/日: {res['human_minutes_per_day']} proxy (days={res['denominators']['human_minutes_days']})"
            )
            print(
                f"  归因准确率: {res['attribution_accuracy']} (n={res['denominators']['attribution']})"
            )
            print(f"  outcome: {res['outcome']}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
