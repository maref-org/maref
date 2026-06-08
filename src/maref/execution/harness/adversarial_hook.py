"""对抗验证钩子 — 同级 Agent 互审。

在 UnifiedHarness 的 VALIDATING 阶段触发，
Reviewer Agent 检查 Executor Agent 的输出，标记问题。

两种模式:
- light: 同级模型快速审查 (默认)
- full: 调用更强模型深度审查 (通过 review_handler 注入)

集成方式:
    hook_registry = HarnessHookRegistry()
    adv_hook = AdversarialValidatorHook(hook_registry, review_handler=my_reviewer)
    # 或在 UnifiedHarness 初始化时传入 hook_registry
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from maref.execution.harness.hooks import HarnessHookRegistry
from maref.recursive.hook_registry import HookResult, HookVerdict

# 默认审查 prompt (light 模式)
_LIGHT_REVIEW_PROMPT = """Review the following output for issues.
Check for: correctness, completeness, security concerns, logical errors.

Output to review:
{output}

Respond with a JSON object:
{{"passed": true/false, "issues": [{{"severity": "low|medium|high", "description": "..."}}], "summary": "..."}}
"""

# 完整审查 prompt (full 模式)
_FULL_REVIEW_PROMPT = """You are a senior reviewer conducting a thorough adversarial review.

Task context: {task_context}
Agent role: {agent_role}

Output to review:
{output}

Check for:
1. Correctness — are there factual errors or logical flaws?
2. Completeness — does the output fully address the task?
3. Security — are there injection vectors, credential leaks, or unsafe operations?
4. Governance compliance — does this violate any constraints?
5. Edge cases — are error paths and boundary conditions handled?

Respond with a JSON object:
{{"passed": true/false, "issues": [{{"severity": "low|medium|high|critical", "category": "correctness|completeness|security|governance|edge_case", "description": "..."}}], "summary": "...", "recommendation": "approve|revise|reject"}}
"""


class AdversarialValidatorHook:
    """对抗验证钩子。

    在 harness.validate 话题触发时，调用 review_handler 审查执行结果。
    发现问题时标记 FLAG，严重问题返回 BLOCK。
    """

    def __init__(
        self,
        hook_registry: HarnessHookRegistry,
        review_handler: Callable[[dict[str, Any]], str] | None = None,
        mode: str = "light",
        fail_on: str = "critical",  # critical|high|any
        handler_id: str = "adversarial-validator",
    ) -> None:
        self._review_handler = review_handler
        self._mode = mode
        self._fail_on = fail_on
        self._handler_id = handler_id
        self._review_count = 0
        self._flag_count = 0
        self._block_count = 0

        hook_registry.register(
            "harness.validate",
            self._validate,
            priority=50,  # 中等优先级, 在审计日志之前
            handler_id=handler_id,
        )

    # ── Stats ─────────────────────────────────────────────────────

    @property
    def review_count(self) -> int:
        return self._review_count

    @property
    def flag_count(self) -> int:
        return self._flag_count

    @property
    def block_count(self) -> int:
        return self._block_count

    def get_stats(self) -> dict[str, int]:
        return {
            "reviews": self._review_count,
            "flags": self._flag_count,
            "blocks": self._block_count,
        }

    # ── Hook handler ──────────────────────────────────────────────

    def _validate(self, event_data: dict[str, Any]) -> HookResult:
        self._review_count += 1
        start = time.time()

        output = event_data.get("result", "")
        task_context = event_data.get("task_name", event_data.get("description", "unknown"))
        agent_role = event_data.get("agent_role", "unknown")

        if not output:
            return HookResult(
                verdict=HookVerdict.PASS,
                handler_id=self._handler_id,
                message="No output to review",
                duration_ms=(time.time() - start) * 1000,
            )

        # 构建审查 prompt
        if self._mode == "full":
            prompt = _FULL_REVIEW_PROMPT.format(
                output=_truncate(str(output), 4000),
                task_context=task_context,
                agent_role=agent_role,
            )
        else:
            prompt = _LIGHT_REVIEW_PROMPT.format(
                output=_truncate(str(output), 2000),
            )

        # 调用审查 handler
        if self._review_handler:
            try:
                review_result = self._review_handler(prompt)
            except BaseException as e:
                return HookResult(
                    verdict=HookVerdict.AUDIT,
                    handler_id=self._handler_id,
                    message=f"Review handler error: {e}",
                    duration_ms=(time.time() - start) * 1000,
                )
        else:
            # 无审查 handler — 返回 NOTIFY 表示"需要人工审查"
            return HookResult(
                verdict=HookVerdict.NOTIFY,
                handler_id=self._handler_id,
                message="No review handler configured — manual review recommended",
                duration_ms=(time.time() - start) * 1000,
            )

        # 解析审查结果
        verdict, message = self._parse_review(review_result)

        duration = (time.time() - start) * 1000
        return HookResult(
            verdict=verdict,
            handler_id=self._handler_id,
            message=message,
            duration_ms=duration,
        )

    # ── 结果解析 ─────────────────────────────────────────────────

    def _parse_review(self, review: str) -> tuple[HookVerdict, str]:
        """解析审查返回, 判定 verdict。"""
        review_lower = review.lower()

        # 检查是否有 critical 级问题
        has_critical = "critical" in review_lower
        has_high = "high" in review_lower and "severity" in review_lower
        has_passed = '"passed": true' in review_lower or "'passed': true" in review_lower
        has_failed = '"passed": false' in review_lower or "'passed': false" in review_lower

        # 决策矩阵
        if has_passed and not has_failed:
            return HookVerdict.PASS, "Adversarial review passed"

        if has_failed and has_critical:
            self._block_count += 1
            return HookVerdict.BLOCK, f"Adversarial review BLOCKED (critical): {_truncate(review, 300)}"

        if self._fail_on == "any" and has_failed:
            self._block_count += 1
            return HookVerdict.BLOCK, f"Adversarial review BLOCKED: {_truncate(review, 300)}"

        if has_failed and has_high and self._fail_on in ("high", "critical"):
            self._block_count += 1
            return HookVerdict.BLOCK, f"Adversarial review BLOCKED (high severity): {_truncate(review, 300)}"

        # 一般问题 — 标记 FLAG 但不阻断
        if has_failed:
            self._flag_count += 1
            return HookVerdict.NOTIFY, f"Adversarial review flagged issues: {_truncate(review, 300)}"

        # 默认: 不确定审查结果时, 标记为审计
        return HookVerdict.AUDIT, f"Adversarial review (unclear verdict): {_truncate(review, 200)}"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated {len(text) - max_len} chars]"
