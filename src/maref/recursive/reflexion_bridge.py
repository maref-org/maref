#!/usr/bin/env python3
"""Reflexion 条件化桥接（Phase 2.3）。

按 fingerprint 自动检索三温记忆/lessons → 注入自愈上下文
自愈成功后 → 生成反思写 lessons → lesson_to_asset 入库

单一事实源: maref_capability_completion_strategy.md §5.4 Reflexion 经验层 + §6 指标（复发率周环比降）
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OBS_FILE = ROOT / ".openclaw" / "mem_assets" / "observations.jsonl"
LESSONS_FILE = ROOT / ".openclaw" / "lessons" / "lessons.jsonl"
TEMP_FILE = ROOT / ".openclaw" / "memory_temperature" / "state.json"

_DEFAULT_LIMIT = 10


def _lvl(trust: str | None) -> int:
    """trust_level -> 数值 L4=4 L3=3 L2=2 L1=1 L0=0"""
    if not trust:
        return 0
    m = re.match(r"L(\d+)", str(trust))
    return int(m.group(1)) if m else 0


def _load_assets() -> list[dict]:
    if not OBS_FILE.exists():
        return []
    assets = []
    for ln in OBS_FILE.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            assets.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return assets


def _load_lessons() -> list[dict]:
    if not LESSONS_FILE.exists():
        return []
    lessons = []
    for ln in LESSONS_FILE.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            lessons.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return lessons


def _score_asset(asset: dict, tokens: list[str]) -> float:
    """简易关键词评分：title/content/tags/commands/evidence 含 token 加分。"""
    ev = asset.get("evidence", [])
    ev_text = ""
    if isinstance(ev, list):
        for e in ev:
            if isinstance(e, dict):
                ev_text += " " + " ".join(str(v) for v in e.values())
            else:
                ev_text += " " + str(e)
    elif isinstance(ev, dict):
        ev_text = " ".join(str(v) for v in ev.values())
    else:
        ev_text = str(ev)

    text = " ".join([
        str(asset.get("title", "")),
        str(asset.get("content", "")),
        " ".join(asset.get("tags", [])),
        " ".join(asset.get("commands", [])),
        ev_text,
    ]).lower()
    score = 0.0
    for t in tokens:
        if t in text:
            score += 1.0
    # trust_level 加权
    score *= (1 + _lvl(asset.get("trust_level")) * 0.2)
    return score


def search_reflections(query: str, *, fp: str | None = None, limit: int = 5, min_trust: str = "") -> list[dict]:
    """检索相关 lessons + assets（合并两源）。

    返回: list of {source: "lesson"|"asset", asset_id, title, content, confidence, trust_level, matched_tokens}
    """
    tokens = [t for t in re.split(r"[\s,，、/]+", (query or "").lower()) if t]
    if fp:
        tokens.append(fp[:8])  # fingerprint 前缀也加入

    assets = _load_assets()
    lessons = _load_lessons()

    results = []

    # 搜 assets
    for a in assets:
        if min_trust and _lvl(a.get("trust_level")) < _lvl(min_trust):
            continue
        s = _score_asset(a, tokens)
        if s > 0:
            matched = [t for t in tokens if t in " ".join([
                str(a.get("title", "")), str(a.get("content", "")), " ".join(a.get("tags", [])), " ".join(a.get("commands", []))
            ]).lower()]
            results.append({
                "source": "asset",
                "asset_id": a.get("asset_id"),
                "title": a.get("title"),
                "content": str(a.get("content", ""))[:500],
                "confidence": a.get("confidence"),
                "trust_level": a.get("trust_level"),
                "obs_type": a.get("obs_type"),
                "score": s,
                "matched_tokens": matched,
            })

    # 搜 lessons
    for l in lessons:
        text = " ".join([
            str(l.get("title", "")),
            str(l.get("lesson", "")),
            " ".join(l.get("tags", [])),
            l.get("session_id", ""),
        ]).lower()
        s = sum(1 for t in tokens if t in text)
        if s > 0:
            results.append({
                "source": "lesson",
                "lesson_id": l.get("lesson_id") or l.get("id"),
                "title": l.get("title"),
                "content": str(l.get("lesson", ""))[:500],
                "confidence": None,
                "trust_level": "L2",  # lessons 默认 L2
                "obs_type": "experience",
                "score": float(s),
                "matched_tokens": [t for t in tokens if t in text],
            })

    # 排序：score 降序 + trust_level 降序
    results.sort(key=lambda x: (-x["score"], -_lvl(x.get("trust_level"))))
    return results[:limit]


def build_reflection_context(fp: str, failure_class: str, sub_class: str, root_cause: str) -> str:
    """构造注入自愈的反思上下文（供 prompt 使用）。"""
    query = f"{fp} {failure_class} {sub_class} {root_cause}"
    hits = search_reflections(query, fp=fp, limit=3, min_trust="L2")
    if not hits:
        return ""

    lines = ["【历史反思注入】"]
    for i, h in enumerate(hits, 1):
        src = h.get("source", "")
        title = h.get("title") or h.get("lesson_id") or "未知"
        content = h.get("content", "")[:200]
        trust = h.get("trust_level", "")
        lines.append(f"{i}. [{src}:{trust}] {title}: {content}")
    lines.append("—— 基于以上历史经验，避免重复错误，优先尝试已验证有效的策略。")
    return "\n".join(lines)


def record_reflection(
    fp: str,
    failure_class: str,
    sub_class: str,
    root_cause: str,
    strategy: str,
    success: bool,
    action_log: str,
    verification: dict | None = None,
) -> dict:
    """自愈完成后记录反思（写 lessons.jsonl）。"""
    lesson = {
        "lesson_id": f"reflex_{fp}_{int(time.time())}",
        "title": f"自愈反思: {failure_class}/{sub_class} -> {strategy} ({'成功' if success else '失败'})",
        "lesson": (
            f"指纹: {fp}\n"
            f"分类: {failure_class}({sub_class})\n"
            f"根因: {root_cause}\n"
            f"策略: {strategy}\n"
            f"结果: {'自愈成功' if success else '自愈失败/升级'}\n"
            f"动作: {action_log}\n"
            f"验证: {verification.get('method') if verification else 'N/A'}"
        ),
        "tags": ["reflexion", "self_healing", failure_class.lower(), sub_class],
        "session_id": fp,
        "timestamp": datetime.now(UTC).isoformat(),
        "outcome": "success" if success else "failure",
    }
    LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LESSONS_FILE.open("a") as fh:
        fh.write(json.dumps(lesson, ensure_ascii=False) + "\n")

    # 同步触发 lesson_to_asset 入库（异步非阻塞）
    try:
        import subprocess
        subprocess.Popen([
            sys.executable, str(ROOT / "scripts" / "lesson_to_asset.py"),
            "--dry-run", "--limit", "1"
        ], cwd=str(ROOT))
    except Exception:
        pass

    return {"recorded": True, "lesson_id": lesson["lesson_id"]}


def check_recurrence(fp: str, window_days: int = 7) -> dict:
    """检查同一 fingerprint 在窗口内是否复发。"""
    from maref.governance.failure_event_bus import load_events
    since = datetime.now(UTC) - timedelta(days=window_days)
    events = load_events(fp=fp, since=since, collapse=True)
    failures = [e for e in events if e.get("signal") == "failure"]
    return {
        "fingerprint": fp,
        "recurrence_count": len(failures) - 1,  # 减去首次
        "is_recurrent": len(failures) >= 2,
        "first_ts": failures[0].get("ts") if failures else None,
        "latest_ts": failures[-1].get("ts") if failures else None,
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Reflexion 条件化桥接（Phase 2.3）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search", help="检索历史反思")
    p.add_argument("query")
    p.add_argument("--fp", default="")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--min-trust", default="")

    p = sub.add_parser("context", help="构造自愈注入上下文")
    p.add_argument("fp")
    p.add_argument("--class", dest="failure_class", required=True)
    p.add_argument("--sub", required=True)
    p.add_argument("--cause", required=True)

    p = sub.add_parser("record", help="记录自愈反思")
    p.add_argument("fp")
    p.add_argument("--class", dest="failure_class", required=True)
    p.add_argument("--sub", required=True)
    p.add_argument("--cause", required=True)
    p.add_argument("--strategy", required=True)
    p.add_argument("--success", action="store_true")
    p.add_argument("--action", default="")
    p.add_argument("--verification", default="{}")

    p = sub.add_parser("recurrence", help="检查复发")
    p.add_argument("fp")
    p.add_argument("--days", type=int, default=7)

    p = sub.add_parser("self-check", help="自检")

    args = ap.parse_args()

    if args.cmd == "self-check":
        # 基础自检
        hits = search_reflections("test", limit=1)
        assert isinstance(hits, list)
        ctx = build_reflection_context("abc123", "E3", "login_expired", "登录过期")
        assert isinstance(ctx, str)
        rec = check_recurrence("abc123")
        assert "is_recurrent" in rec
        print("reflexion_bridge.self_check: OK")
        return 0

    if args.cmd == "search":
        hits = search_reflections(args.query, fp=args.fp or None, limit=args.limit, min_trust=args.min_trust)
        print(json.dumps(hits, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "context":
        ctx = build_reflection_context(args.fp, args.failure_class, args.sub, args.cause)
        print(ctx)
        return 0

    if args.cmd == "record":
        import asyncio
        vr = json.loads(args.verification) if args.verification else None
        res = record_reflection(args.fp, args.failure_class, args.sub, args.cause,
                                args.strategy, args.success, args.action, vr)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "recurrence":
        res = check_recurrence(args.fp, args.days)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())