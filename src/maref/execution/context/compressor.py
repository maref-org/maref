from __future__ import annotations

from typing import Any

_TOKEN_RATIO = 4.0  # 平均每 token 约 4 字符


class ContextCompressor:
    """上下文压缩器。优先保留保护段（工具定义等），从中部截断历史对话。"""

    def estimate_tokens(self, text: str) -> int:
        return max(1, int(len(text) / _TOKEN_RATIO))

    def compress(self, context: str, budget: int, protected_sections: list[str] | None = None) -> str:
        if self.estimate_tokens(context) <= budget:
            return context

        protected = protected_sections or []
        placeholder = "\n[...truncated...]"

        # 计算保护段的空间
        protected_total = 0
        for section in protected:
            protected_total += self.estimate_tokens(section)

        remaining_budget = budget - protected_total - self.estimate_tokens(placeholder)
        if remaining_budget <= 0:
            return placeholder.join(protected) if protected else placeholder

        # 找到保护段在 context 中的位置
        if protected:
            for section in protected:
                context = context.replace(section, "", 1)

        # 从中部截断：保留头部和尾部
        context_tokens = self.estimate_tokens(context)
        keep_head_ratio = 0.6
        keep_chars = int((remaining_budget / context_tokens) * len(context))

        head_chars = int(keep_chars * keep_head_ratio)
        tail_chars = keep_chars - head_chars

        if head_chars + tail_chars >= len(context):
            result = context
        else:
            result = context[:head_chars] + placeholder + context[-tail_chars:]

        # 重新插入保护段到最前面
        if protected:
            result = "\n\n".join(protected) + "\n\n" + result

        return result

    def stats(self) -> dict[str, Any]:
        return {
            "token_ratio": _TOKEN_RATIO,
        }
