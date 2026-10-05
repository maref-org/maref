#!/usr/bin/env python3
"""失败事件统一入口（双仓补全方案 Phase 1.1 / 1.3 / 1.7）。

单一事实源: 战略 maref_capability_completion_strategy.md §5.1 信号 schema、
§6 指标定义（自愈率/复发率/升级率/MTTR）。

  record   写一行结构化失败/摩擦信号 + fingerprint + 截图归档 + agent_bus 广播
  resolve  标记自愈成功（供 MTTR / 自愈率）
  escalate 标记升级人工
  list     按 fp / signal / 时间窗列出事件
  replay   <fp> 回放: 事件 + 截图 + 轨迹步
  stats    四指标日查（自愈率/复发率/升级率/MTTR）

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# py<3.11 无 datetime.UTC（py3.10 target 兼容）：统一走 timezone.utc
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

    rec: dict[str, Any] = {
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
        "denominators": {
            "self_heal": resolved,
            "recurrence": total_fail,
            "escalation": total_fail,
            "mttr": len(deltas),
            "screenshot": total_fail,
        },
        "note": "分母为 0 时指标诚实返回 null（战略§6：不假 0）",
    }


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

    p = sub.add_parser("list", help="列出事件")
    p.add_argument("--fp", default="")
    p.add_argument("--signal", default="", choices=SIGNALS)
    p.add_argument("--days", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("replay", help="按 fingerprint 回放")
    p.add_argument("fp")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("stats", help="四指标")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true")

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
            print(f"  outcome: {res['outcome']}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
