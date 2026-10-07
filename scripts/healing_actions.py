#!/usr/bin/env python3
"""自愈动作库 + 四路策略路由（Phase 2.2）。

单一事实源: maref_capability_completion_strategy.md §5.3 自愈策略路由 + §6 指标（自愈率≥40%）。

四路策略：
  retry-corrected  - 同一任务修正参数/提示词重试
  replan          - 重新规划步骤/换路径
  tool-fallback   - 切换备用工具/API
  escalate        - 升级人工/上层 Governor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# 导入失败事件总线（记录自愈结果）
sys.path.insert(0, str(SCRIPTS))
from failure_event_bus import record, mark, OUTCOMES

# Phase 2.3 Reflexion 条件化桥接
try:
    from reflexion_bridge import build_reflection_context, record_reflection, check_recurrence
except ImportError:
    build_reflection_context = None
    record_reflection = None
    check_recurrence = None


class HealingStrategy(str, Enum):
    RETRY_CORRECTED = "retry-corrected"
    REPLAN = "replan"
    TOOL_FALLBACK = "tool-fallback"
    ESCALATE = "escalate"


# 失败分类 → 策略路由表（战略 §5.3 决策表）
STRATEGY_ROUTING_TABLE: dict[str, HealingStrategy] = {
    # E1 幻觉/状态错判 → 重新规划
    "E1": HealingStrategy.REPLAN,
    # E2 执行错误/工具失败 → 工具降级
    "E2": HealingStrategy.TOOL_FALLBACK,
    # E3 环境阻力 → 修正重试（含登录恢复、风控冷却、弹窗关闭）
    "E3": HealingStrategy.RETRY_CORRECTED,
    # E4 规划错误 → 重新规划
    "E4": HealingStrategy.REPLAN,
    # E5 规格缺口 → 升级
    "E5": HealingStrategy.ESCALATE,
}

# E3 子类 → 策略微调（覆盖默认）
E3_STRATEGY_OVERRIDE = {
    "captcha": HealingStrategy.ESCALATE,
    "cloudflare": HealingStrategy.ESCALATE,
    "popup": HealingStrategy.TOOL_FALLBACK,
}


@dataclass
class VerificationResult:
    success: bool
    method: str
    detail: str = ""
    latency_ms: int = 0


class Verifier(ABC):
    """机器可验证的验证器基类（战略：恢复成功=机器可验证）。"""

    @abstractmethod
    def verify(self, context: dict[str, Any]) -> VerificationResult:
        ...


class URLReachableVerifier(Verifier):
    """URL 可达性验证（HTTP 200/3xx）。"""

    def verify(self, context: dict[str, Any]) -> VerificationResult:
        import urllib.request
        url = context.get("url") or context.get("target_url")
        if not url:
            return VerificationResult(False, "url_reachable", "missing url")
        start = time.time()
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                ok = 200 <= resp.status < 400
                return VerificationResult(
                    ok, "url_reachable",
                    f"HTTP {resp.status}",
                    int((time.time() - start) * 1000)
                )
        except Exception as e:
            return VerificationResult(False, "url_reachable", str(e), int((time.time() - start) * 1000))


class OCRTextVerifier(Verifier):
    """OCR 出现成功提示文案验证。"""

    def verify(self, context: dict[str, Any]) -> VerificationResult:
        expected = context.get("expected_text", [])
        screenshot = context.get("screenshot")
        if not screenshot or not Path(screenshot).exists():
            return VerificationResult(False, "ocr_text", "screenshot missing")
        try:
            # 复用 easyocr（本地）
            import easyocr
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            result = reader.readtext(screenshot, detail=0)
            text = " ".join(result)
            for exp in expected:
                if exp in text:
                    return VerificationResult(True, "ocr_text", f"matched: {exp}")
            return VerificationResult(False, "ocr_text", f"none of {expected} found in OCR")
        except Exception as e:
            return VerificationResult(False, "ocr_text", f"ocr error: {e}")


class APIStatusVerifier(Verifier):
    """API 返回 200 验证。"""

    def verify(self, context: dict[str, Any]) -> VerificationResult:
        # 期望 context 有 verify_cmd 或 verify_api 字段
        cmd = context.get("verify_cmd")
        if not cmd:
            return VerificationResult(False, "api_status", "missing verify_cmd")
        start = time.time()
        try:
            r = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=30)
            ok = r.returncode == 0
            return VerificationResult(ok, "api_status", f"exit={r.returncode}", int((time.time() - start) * 1000))
        except subprocess.TimeoutExpired:
            return VerificationResult(False, "api_status", "timeout", int((time.time() - start) * 1000))
        except Exception as e:
            return VerificationResult(False, "api_status", str(e), int((time.time() - start) * 1000))


class HumanQueueVerifier(Verifier):
    """人工队列入列确认（escalate 分支的验证）。"""

    def verify(self, context: dict[str, Any]) -> VerificationResult:
        # 检查 .openclaw/inbox/ 是否有对应 escalation 记录
        inbox = Path(os.environ.get("FAILURE_INBOX") or (ROOT / ".openclaw" / "inbox"))
        fp = context.get("fingerprint", "")
        if not fp:
            return VerificationResult(False, "human_queue", "missing fingerprint")
        for p in inbox.glob(f"*{fp}*"):
            return VerificationResult(True, "human_queue", f"escalation recorded: {p.name}")
        return VerificationResult(False, "human_queue", "no escalation record in inbox")


# 验证器注册表
VERIFIERS: dict[HealingStrategy, Verifier] = {
    HealingStrategy.RETRY_CORRECTED: OCRTextVerifier(),
    HealingStrategy.REPLAN: URLReachableVerifier(),
    HealingStrategy.TOOL_FALLBACK: APIStatusVerifier(),
    HealingStrategy.ESCALATE: HumanQueueVerifier(),
}


def route_strategy(failure_class: str, sub_class: str = "") -> HealingStrategy:
    """按失败分类路由策略（E3 子类可覆盖）。"""
    if failure_class == "E3" and sub_class in E3_STRATEGY_OVERRIDE:
        return E3_STRATEGY_OVERRIDE[sub_class]
    return STRATEGY_ROUTING_TABLE.get(failure_class, HealingStrategy.ESCALATE)


async def execute_healing(
    fp: str,
    failure_class: str,
    sub_class: str,
    strategy: HealingStrategy,
    context: dict[str, Any],
) -> dict[str, Any]:
    """执行自愈动作 + 验证器确认 + Reflexion 条件化（Phase 2.3）。"""
    start = time.time()
    result = {"fp": fp, "strategy": strategy.value, "success": False, "detail": "", "verification": None}

    # Phase 2.3: 自愈前注入历史反思上下文
    reflection_ctx = ""
    if build_reflection_context:
        reflection_ctx = build_reflection_context(fp, failure_class, sub_class, context.get("root_cause", ""))
        if reflection_ctx:
            context["reflection_context"] = reflection_ctx

    # Phase 2.3: 检查复发
    is_recurrent = False
    if check_recurrence:
        rec = check_recurrence(fp)
        is_recurrent = rec.get("is_recurrent", False)
        if is_recurrent:
            context["is_recurrent"] = True
            result["recurrence"] = rec

    try:
        if strategy == HealingStrategy.RETRY_CORRECTED:
            # 修正重试：重新登录、冷却等待、关闭弹窗
            detail = await _retry_corrected_action(fp, sub_class, context)
        elif strategy == HealingStrategy.REPLAN:
            # 重新规划：触发任务重规划（写入 agent_bus 等待 planner）
            detail = await _replan_action(fp, context)
        elif strategy == HealingStrategy.TOOL_FALLBACK:
            # 工具降级：切换备用 API/路径
            detail = await _tool_fallback_action(fp, sub_class, context)
        elif strategy == HealingStrategy.ESCALATE:
            # 升级：写入 inbox、通知 Governor
            detail = await _escalate_action(fp, sub_class, context)
        else:
            detail = f"unknown strategy {strategy}"

        # 执行后验证
        context["fingerprint"] = fp  # 供 HumanQueueVerifier 等验证器使用
        verifier = VERIFIERS.get(strategy)
        if verifier:
            vr = verifier.verify(context)
            result["verification"] = asdict(vr)
            if vr.success:
                result["success"] = True
                result["detail"] = f"{detail} | verified: {vr.method}"
            else:
                result["detail"] = f"{detail} | verification failed: {vr.detail}"
        else:
            result["success"] = True
            result["detail"] = detail

    except Exception as e:
        result["detail"] = f"execute error: {e}"

    result["latency_ms"] = int((time.time() - start) * 1000)

    # Phase 2.3: 记录反思（自愈完成后）
    if record_reflection:
        vr = result.get("verification")
        record_reflection(
            fp=fp,
            failure_class=failure_class,
            sub_class=sub_class,
            root_cause=context.get("root_cause", ""),
            strategy=strategy.value,
            success=result["success"],
            action_log=result["detail"],
            verification=vr,
        )

    # 记录结果到失败事件总线
    if result["success"]:
        mark(fp, "recovered", actor="healing_actions", note=result["detail"])
    else:
        mark(fp, "escalated", actor="healing_actions", note=result["detail"])

    return result


async def _retry_corrected_action(fp: str, sub_class: str, context: dict) -> str:
    """E3 环境阻力的修正重试动作。"""
    actions = []
    if sub_class == "login_expired":
        # 触发重新登录流程（调用现有登录脚本）
        actions.append("trigger_re_login")
    elif sub_class == "risk_control":
        actions.append("wait_cooldown_300s")
    elif sub_class == "button_disabled":
        actions.append("wait_element_enabled")
    elif sub_class == "popup":
        actions.append("dismiss_popup")
    else:
        actions.append("generic_retry")

    # 实际执行：这里只记录意图，真实执行由 self_healing_engine 对接
    return f"retry_corrected: {', '.join(actions)}"


async def _replan_action(fp: str, context: dict) -> str:
    """E1/E4 重新规划：发布 replan 任务到 agent_bus。"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_bus", SCRIPTS / "agent_bus.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bus = mod.AgentBus()
        bus.publish("task_replan", "healing_actions", {
            "fingerprint": fp,
            "reason": "failure_class in (E1, E4) -> replan",
            "original_task": context.get("task_id", ""),
            "ts": datetime.now(UTC).isoformat(),
        })
        return "replan_task_published"
    except Exception as e:
        return f"replan publish failed: {e}"


async def _tool_fallback_action(fp: str, sub_class: str, context: dict) -> str:
    """E2 工具失败的降级动作。"""
    actions = []
    if sub_class == "timeout":
        actions.append("switch_to_async_polling")
    elif sub_class == "element_missing":
        actions.append("try_alternative_selector")
    elif sub_class == "adb_error":
        actions.append("reconnect_adb_wireless")
    elif sub_class == "api_error":
        actions.append("fallback_to_mock_or_cache")
    else:
        actions.append("generic_fallback")
    return f"tool_fallback: {', '.join(actions)}"


async def _escalate_action(fp: str, sub_class: str, context: dict) -> str:
    """E5/E3部分 升级人工。"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_bus", SCRIPTS / "agent_bus.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bus = mod.AgentBus()
        bus.publish("human_escalation", "healing_actions", {
            "fingerprint": fp,
            "failure_class": context.get("failure_class"),
            "sub_class": sub_class,
            "reason": context.get("root_cause", ""),
            "ts": datetime.now(UTC).isoformat(),
        })
        # 同时写 inbox（HumanQueueVerifier 会查）
        inbox = ROOT / ".openclaw" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / f"escalation_{fp}_{int(time.time())}.json").write_text(
            json.dumps({"fp": fp, "sub_class": sub_class, "context": context}, ensure_ascii=False)
        )
        return "escalation_published_and_recorded"
    except Exception as e:
        return f"escalate failed: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="自愈动作库 + 四路策略路由（Phase 2.2）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("route", help="按失败分类路由策略")
    p.add_argument("failure_class", choices=["E1", "E2", "E3", "E4", "E5"])
    p.add_argument("--sub", default="")

    p = sub.add_parser("execute", help="执行自愈动作（异步）")
    p.add_argument("fp")
    p.add_argument("--class", dest="failure_class", required=True, choices=["E1", "E2", "E3", "E4", "E5"])
    p.add_argument("--sub", default="")
    p.add_argument("--context", default="{}", help="JSON context for verifier")

    p = sub.add_parser("verify", help="单独跑验证器")
    p.add_argument("strategy", choices=[s.value for s in HealingStrategy])
    p.add_argument("--context", default="{}")

    p = sub.add_parser("self-check", help="自检")

    args = ap.parse_args()

    if args.cmd == "self-check":
        # 路由表自检
        assert route_strategy("E1") == HealingStrategy.REPLAN
        assert route_strategy("E2") == HealingStrategy.TOOL_FALLBACK
        assert route_strategy("E3") == HealingStrategy.RETRY_CORRECTED
        assert route_strategy("E4") == HealingStrategy.REPLAN
        assert route_strategy("E5") == HealingStrategy.ESCALATE
        # E3 子类覆盖
        assert route_strategy("E3", "captcha") == HealingStrategy.ESCALATE
        assert route_strategy("E3", "popup") == HealingStrategy.TOOL_FALLBACK
        # 验证器可实例化
        for v in VERIFIERS.values():
            assert hasattr(v, "verify")
        print("healing_actions.self_check: OK")
        return 0

    if args.cmd == "route":
        strat = route_strategy(args.failure_class, args.sub)
        print(json.dumps({"strategy": strat.value}, ensure_ascii=False))
        return 0

    if args.cmd == "execute":
        import asyncio
        ctx = json.loads(args.context)
        strat = route_strategy(args.failure_class, args.sub)
        res = asyncio.run(execute_healing(args.fp, args.failure_class, args.sub, strat, ctx))
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0 if res["success"] else 1

    if args.cmd == "verify":
        import asyncio
        ctx = json.loads(args.context)
        vr = VERIFIERS[HealingStrategy(args.strategy)].verify(ctx)
        print(json.dumps(asdict(vr), ensure_ascii=False, indent=2, default=str))
        return 0 if vr.success else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())