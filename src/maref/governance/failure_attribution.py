#!/usr/bin/env python3
"""视觉归因器（Phase 2.1 闭环补全）。

读 failure_event_bus 事件 → VLM/OCR 读屏 → 输出 E1-E5 + root_cause + suggested_strategy 回写事件。

单一事实源: maref_capability_completion_strategy.md §5.2 归因分类器 + §6 指标（归因准确率≥85%抽样）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EVENTS_DIR = Path(os.environ.get("FAILURE_EVENT_DIR") or (ROOT / ".openclaw" / "failure_events"))
EVENTS = EVENTS_DIR / "events.jsonl"
ARTIFACTS = Path(os.environ.get("FAILURE_ARTIFACTS_DIR") or (ROOT / ".openclaw" / "failure_artifacts"))

# E1-E5 失败分类学（战略 §5.2）
FAILURE_CLASSES = {
    "E1": "hallucination",      # 幻觉/错误理解状态（把"草稿已保存"当成"已发布"）
    "E2": "execution_error",    # 执行错误/工具失败（API 超时、元素未找到）
    "E3": "environment",        # 环境阻力（登录失效、验证码、风控弹窗、Cloudflare）
    "E4": "planning",           # 推理/规划错误（步骤顺序错、前提未满足）
    "E5": "spec_gap",           # 规格缺口（任务歧义、验收标准不清）
}

# E3 子类（优先覆盖，含恢复策略映射 self_healing_engine failure_code）
E3_SUBCLASSES = {
    "login_expired":   {"pattern": ["登录", "login", "session 失效", "token 过期", "重新登录"], "strategy": "retry-corrected"},
    "captcha":         {"pattern": ["验证码", "captcha", "滑块", "人机验证"], "strategy": "escalate"},
    "risk_control":    {"pattern": ["风控", "risk", "限流", "rate limit", "频繁操作", "账号异常"], "strategy": "retry-corrected"},
    "cloudflare":      {"pattern": ["cloudflare", "检测", "挑战", "challenge", "cf-ray"], "strategy": "escalate"},
    "popup":           {"pattern": ["弹窗", "popup", "弹出", "dialog", "提示框", "确认"], "strategy": "tool-fallback"},
    "button_disabled": {"pattern": ["按钮不可用", "disabled", "灰色", "不可点击", "置灰"], "strategy": "retry-corrected"},
}

# E2 常见工具失败模式
E2_PATTERNS = {
    "timeout":       ["timeout", "超时", "timed out", "read timed out", "connect timeout"],
    "element_missing": ["no such element", "元素未找到", "not found", "unable to locate", "找不到"],
    "api_error":     ["api error", "http 5", "http 4", "status 5", "status 4", "服务器错误"],
    "adb_error":     ["adb", "device offline", "无设备", "connection refused", "adb shell"],
    "ocr_fail":      ["ocr", "easyocr", "识别失败", "读不到文字", "no text"],
}

# E1 幻觉模式（基于输出与真实状态不符）
E1_PATTERNS = {
    "false_success": ["已发布", "发布成功", "成功", "completed", "success"] + ["但实际", "然而", "不过", "事实上", "actually"],
    "state_mismatch": ["草稿", "draft", "保存", "saved"] + ["当成", "误判", "以为", "当作", "mistook"],
}

# E4 规划错误模式
E4_PATTERNS = {
    "order_wrong": ["顺序", "先后", "步骤", "前置", "prerequisite", "依赖"],
    "precondition_fail": ["前提", "条件", "precondition", "假设", "未满足", "not ready"],
}

# E5 规格缺口模式
E5_PATTERNS = {
    "ambiguous": ["歧义", "不明确", "ambiguous", "不清楚", "模糊"],
    "no_acceptance": ["验收", "acceptance", "标准", "criteria", "定义"],
}


@dataclass
class AttributionResult:
    failure_class: str          # E1-E5
    sub_class: str              # 细分类（如 login_expired）
    root_cause: str             # 根因描述（中文，≤200字）
    suggested_strategy: str     # retry-corrected / replan / tool-fallback / escalate
    confidence: float           # 0.0-1.0
    evidence: list[str]         # 证据片段（截图关键词/日志片段）


def log(*a):
    print(*a, flush=True)


def _read_vlm_screenshot(shot_path: str, task: str) -> str | None:
    """调用 huawei_see.py 读屏（本地 minicpm 优先，失败兜底云端）。"""
    try:
        # 优先本地 minicpm（免费、~22s、不外发截图）
        cmd = ["python3", str(SCRIPTS / "huawei_see.py"), "--adb", "--task", task]
        if shot_path:
            # huawei_see 支持通过环境变量或修改截图路径；这里用默认截图逻辑
            pass
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=str(SCRIPTS))
        out = (r.stdout or "").strip()
        if out and not out.startswith("Ollama 本地 VLM 失败") and "失败" not in out[:20]:
            return out
        # 兜底云端
        cmd2 = ["python3", str(SCRIPTS / "huawei_see.py"), "--adb", "--cloud", "--task", task]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=120, cwd=str(SCRIPTS))
        out2 = (r2.stdout or "").strip()
        if out2:
            return out2
    except subprocess.TimeoutExpired:
        return "VLM_TIMEOUT"
    except Exception as e:
        return f"VLM_ERROR:{type(e).__name__}"
    return None


def _read_grounding(shot_path: str, task: str) -> dict | None:
    """调用 vlm_grounding.py 获取像素坐标定位（用于按钮 disabled/元素未找到等空间判断）。"""
    try:
        cmd = ["python3", str(SCRIPTS / "vlm_grounding.py"), "--adb", "--task", task, "--json"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(SCRIPTS))
        if r.returncode == 0:
            import json as _json
            return _json.loads(r.stdout)
    except Exception:
        pass
    return None


def _load_event(fp: str) -> dict | None:
    if not EVENTS.exists():
        return None
    for ln in EVENTS.read_text(errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if rec.get("fingerprint") == fp:
            return rec
    return None


def _save_attribution(fp: str, attr: AttributionResult) -> dict:
    """append-only 回写：在事件账本追加 attribution 记录（不改历史）。"""
    ts = datetime.now(UTC).isoformat()
    rec = {
        "schema_version": "1.0",
        "event_id": hashlib.sha256(f"{fp}{ts}".encode()).hexdigest()[:16],
        "fingerprint": fp,
        "type": "attribution",
        "failure_class": attr.failure_class,
        "sub_class": attr.sub_class,
        "root_cause": attr.root_cause,
        "suggested_strategy": attr.suggested_strategy,
        "confidence": attr.confidence,
        "evidence": attr.evidence,
        "ts": ts,
    }
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"updated": True, "attribution": asdict(attr)}


def _classify_by_visual(text: str, detail: str, grounding: dict | None) -> AttributionResult:
    """基于视觉描述 + 日志详情 + grounding 结果做分类。"""
    full = f"{text} {detail}".lower()
    evidence = []

    # 1) E3 环境阻力（优先，含恢复策略）
    for sub, cfg in E3_SUBCLASSES.items():
        for kw in cfg["pattern"]:
            if kw.lower() in full:
                evidence.append(f"E3:{sub}:{kw}")
                return AttributionResult(
                    failure_class="E3",
                    sub_class=sub,
                    root_cause=f"环境阻力-{sub}: 视觉/日志检测到 '{kw}'",
                    suggested_strategy=cfg["strategy"],
                    confidence=0.85,
                    evidence=evidence,
                )

    # 2) E2 执行错误/工具失败
    for sub, pats in E2_PATTERNS.items():
        for kw in pats:
            if kw.lower() in full:
                evidence.append(f"E2:{sub}:{kw}")
                return AttributionResult(
                    failure_class="E2",
                    sub_class=sub,
                    root_cause=f"工具失败-{sub}: 检测到 '{kw}'",
                    suggested_strategy="tool-fallback" if sub in ("timeout", "adb_error") else "retry-corrected",
                    confidence=0.8,
                    evidence=evidence,
                )

    # 3) E1 幻觉/状态错判（需结合视觉与预期对比）
    for sub, pats in E1_PATTERNS.items():
        hit = 0
        for kw in pats:
            if kw.lower() in full:
                hit += 1
        if hit >= 2:  # 需同时命中正向词+反向词
            evidence.append(f"E1:{sub}")
            return AttributionResult(
                failure_class="E1",
                sub_class=sub,
                root_cause=f"幻觉/状态错判: 输出声称成功但视觉/日志显示仍在中间态",
                suggested_strategy="replan",
                confidence=0.7,
                evidence=evidence,
            )

    # 4) E4 规划错误
    for sub, pats in E4_PATTERNS.items():
        for kw in pats:
            if kw.lower() in full:
                evidence.append(f"E4:{sub}:{kw}")
                return AttributionResult(
                    failure_class="E4",
                    sub_class=sub,
                    root_cause=f"规划错误-{sub}: 检测到 '{kw}'",
                    suggested_strategy="replan",
                    confidence=0.75,
                    evidence=evidence,
                )

    # 5) E5 规格缺口
    for sub, pats in E5_PATTERNS.items():
        for kw in pats:
            if kw.lower() in full:
                evidence.append(f"E5:{sub}:{kw}")
                return AttributionResult(
                    failure_class="E5",
                    sub_class=sub,
                    root_cause=f"规格缺口-{sub}: 任务/验收标准未明确",
                    suggested_strategy="escalate",
                    confidence=0.7,
                    evidence=evidence,
                )

    # 6) Grounding 空间信号（按钮 disabled、元素越界等）
    if grounding:
        elements = grounding.get("elements", [])
        for el in elements:
            label = (el.get("label") or "").lower()
            if "disabled" in label or "不可用" in label or "灰色" in label:
                evidence.append(f"GROUNDING:button_disabled:{label}")
                return AttributionResult(
                    failure_class="E3",
                    sub_class="button_disabled",
                    root_cause=f"按钮不可用: grounding 检测到 '{label}' 为 disabled 态",
                    suggested_strategy="retry-corrected",
                    confidence=0.9,
                    evidence=evidence,
                )

    # 默认：未识别
    return AttributionResult(
        failure_class="E5",
        sub_class="unknown",
        root_cause="未匹配已知模式，需人工分析",
        suggested_strategy="escalate",
        confidence=0.3,
        evidence=["NO_MATCH"],
    )


def attribute(fp: str, use_grounding: bool = False) -> dict:
    """对单个 fingerprint 做归因。"""
    ev = _load_event(fp)
    if not ev:
        return {"error": "not_found", "fingerprint": fp}

    shot = ev.get("screenshot_ref", "")
    if shot and not Path(shot).exists():
        # 尝试在 ARTIFACTS 下找
        candidates = list(ARTIFACTS.glob(f"{fp}/*"))
        if candidates:
            shot = str(candidates[-1])

    task = f"分析失败画面：{ev.get('detail','')[:200]}。signal={ev.get('signal')} class={ev.get('class')}"
    vlm_text = _read_vlm_screenshot(shot, task) if shot else None
    grounding = _read_grounding(shot, "定位异常元素位置与状态") if (shot and use_grounding) else None

    attr = _classify_by_visual(vlm_text or "", ev.get("detail", ""), grounding)
    attr.evidence.append(f"vlm:{vlm_text[:80] if vlm_text else 'NONE'}")

    # 回写
    res = _save_attribution(fp, attr)

    # 同时更新原事件的 class 字段（供 stats/列表用）
    ev["class"] = attr.failure_class
    with EVENTS.open("a") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    return res


def batch_attribute(fp_list: list[str] | None = None, since_days: int = 0, use_grounding: bool = False) -> dict:
    """批量归因：对未归因的 failure 事件自动跑。"""
    if not EVENTS.exists():
        return {"done": 0, "error": "no_events"}
    since = datetime.now(UTC) - timedelta(days=since_days) if since_days else None

    seen_fps = set()
    if fp_list:
        seen_fps = set(fp_list)
    else:
        for ln in EVENTS.read_text(errors="replace").splitlines():
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if rec.get("signal") == "failure" and rec.get("fingerprint"):
                if since and datetime.fromisoformat(rec["ts"].replace("Z", "+00:00")) < since:
                    continue
                # 已有 attribution 记录则跳过
                has_attr = any(
                    ln2.strip() and json.loads(ln2).get("type") == "attribution" and json.loads(ln2).get("fingerprint") == rec["fingerprint"]
                    for ln2 in EVENTS.read_text(errors="replace").splitlines()
                )
                if not has_attr:
                    seen_fps.add(rec["fingerprint"])

    results = []
    for fp in seen_fps:
        res = attribute(fp, use_grounding)
        results.append(res)

    return {"done": len(results), "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description="视觉归因器（Phase 2.1）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("attribute", help="对单个 fingerprint 归因")
    p.add_argument("fp")
    p.add_argument("--grounding", action="store_true")

    p = sub.add_parser("batch", help="批量归因未处理事件")
    p.add_argument("--fps", nargs="*", default=None)
    p.add_argument("--since-days", type=int, default=7)
    p.add_argument("--grounding", action="store_true")

    p = sub.add_parser("self-check", help="自检")

    args = ap.parse_args()

    if args.cmd == "self-check":
        import tempfile
        global EVENTS_DIR, EVENTS, ARTIFACTS
        backup = (EVENTS_DIR, EVENTS, ARTIFACTS)
        tmp = Path(tempfile.mkdtemp(prefix="attr_selfcheck_"))
        try:
            EVENTS_DIR = tmp / "failure_events"
            EVENTS = EVENTS_DIR / "events.jsonl"
            ARTIFACTS = tmp / "failure_artifacts"

            # 模拟一条 E3 事件
            from failure_event_bus import record, make_fingerprint
            r = record("failure", "test", task_id="t1", signature="login expired",
                       detail="视觉检测到登录页面：请输入手机号", auto_screenshot=False, bus=False)
            assert not r["skipped"]
            fp = r["event"]["fingerprint"]

            # 屏蔽 VLM 调用，直接测试分类逻辑
            attr = _classify_by_visual("登录页面 请输入手机号", "session 失效需重新登录", None)
            assert attr.failure_class == "E3" and attr.sub_class == "login_expired"
            assert attr.suggested_strategy == "retry-corrected"

            # E2
            attr2 = _classify_by_visual("timeout", "api read timed out", None)
            assert attr2.failure_class == "E2" and attr2.sub_class == "timeout"

            # E1
            attr3 = _classify_by_visual("发布成功 但实际 未发布", "声称成功", None)
            assert attr3.failure_class == "E1"

            print("failure_attribution.self_check: OK")
            return 0
        finally:
            EVENTS_DIR, EVENTS, ARTIFACTS = backup
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    if args.cmd == "attribute":
        res = attribute(args.fp, args.grounding)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0 if "error" not in res else 2

    if args.cmd == "batch":
        res = batch_attribute(args.fps, args.since_days, args.grounding)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())