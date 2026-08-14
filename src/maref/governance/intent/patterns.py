"""ChainPatternLibrary — 恶意动作链模式库 (v0.52.1 G2-C2)。

定义可扩展的恶意链模式, 对位 AISI 四大发现。每个模式是一组有序的
动作匹配器 (基于 ActionRecord.category / action / metadata)。

模式序列中的相邻匹配器之间允许少量无关动作 (gap) — 因为代理可能插入
伪装步骤掩盖真实攻击链。

内置 8 个模式 (对位 AISI):
    supply_chain_lie     发现 ① 提交→自背书→感谢  (软件供应链欺骗)
    se_human_lure        发现 ② 通信→附件→诱跑代码 (社交工程)
    credential_harvest   发现 ② 索要凭证→收到→离开
    identity_rotation    发现 ① 建身份→建身份→弃旧  (换身份续作)
    record_tamper        发现 ① 改历史→切换身份     (掩盖痕迹)
    anonymous_evasion    发现 ① 网络→切换出口        (Tor 逃避)
    cross_agent_share    发现 ④ 留言分享→外部复用     (跨代理遗产)
    code_inject_hide     发现 ③ 注入→清理痕迹       (提示注入+掩盖)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from maref.governance.intent.chain_tracker import ActionCategory, ActionRecord


class ActionMatcher:
    """动作匹配器 — 判定一条 ActionRecord 是否匹配模式中的一步。

    通过 category 和/或 action 子串、metadata 谓词组合匹配。
    """

    def __init__(
        self,
        category: ActionCategory | None = None,
        action_contains: str | None = None,
        metadata_pred: Callable[[dict[str, Any]], bool] | None = None,
        label: str = "",
    ) -> None:
        self.category = category
        self.action_contains = action_contains
        self.metadata_pred = metadata_pred
        self.label = label or f"{category.value if category else '?'}/{action_contains or '*'}"

    def matches(self, record: ActionRecord) -> bool:
        if self.category is not None and record.category != self.category:
            return False
        if self.action_contains and self.action_contains not in record.action.lower():
            return False
        return not (
            self.metadata_pred is not None
            and not self.metadata_pred(record.metadata)
        )

    def __repr__(self) -> str:
        return f"Matcher({self.label})"


@dataclass
class ChainPattern:
    """一个恶意动作链模式。

    Attributes:
        pattern_id: 模式唯一标识。
        name: 模式名称。
        sequence: 有序匹配器列表。
        severity: 链级风险分级 (命中即至少此级)。
        weight: 聚合评分权重。
        description: 模式描述。
    """

    pattern_id: str
    name: str
    sequence: list[ActionMatcher]
    severity: str = "HIGH"  # LOW/MEDIUM/HIGH/CRITICAL
    weight: float = 1.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "severity": self.severity,
            "weight": self.weight,
            "description": self.description,
            "sequence_labels": [m.label for m in self.sequence],
        }


@dataclass
class PatternMatch:
    """一次模式匹配结果。

    Attributes:
        pattern: 命中的模式。
        start_index: 在链中的起始索引。
        end_index: 在链中的结束索引。
        matched_records: 命中的动作记录。
        gap_count: 匹配段内插入的无关动作数 (gap 越大置信度越低)。
    """

    pattern: ChainPattern
    start_index: int
    end_index: int
    matched_records: list[ActionRecord]
    gap_count: int = 0

    @property
    def span(self) -> int:
        return self.end_index - self.start_index + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern.pattern_id,
            "name": self.pattern.name,
            "severity": self.pattern.severity,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "matched_actions": [r.action for r in self.matched_records],
            "gap_count": self.gap_count,
        }


# 允许的最大 gap (连续无关动作数)
_DEFAULT_MAX_GAP = 2


class ChainPatternLibrary:
    """恶意链模式库 — 注册 + 子序列匹配。

    Usage::

        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        matches = lib.match(chain)
    """

    def __init__(self, max_gap: int = _DEFAULT_MAX_GAP) -> None:
        self.max_gap = max_gap
        self._patterns: dict[str, ChainPattern] = {}

    def register(self, pattern: ChainPattern) -> None:
        self._patterns[pattern.pattern_id] = pattern

    def register_builtin_patterns(self) -> None:
        """注册 8 个内置 AISI 对位模式。"""
        for pattern in _BUILTIN_PATTERNS:
            self.register(pattern)

    def list_patterns(self) -> list[ChainPattern]:
        return list(self._patterns.values())

    def get(self, pattern_id: str) -> ChainPattern | None:
        return self._patterns.get(pattern_id)

    def match(self, chain: list[ActionRecord]) -> list[PatternMatch]:
        """在动作链上匹配全部模式 (允许 gap)。

        Args:
            chain: 时间升序的动作链。

        Returns:
            命中的 PatternMatch 列表。
        """
        matches: list[PatternMatch] = []
        for pattern in self._patterns.values():
            found = self._match_one(chain, pattern)
            matches.extend(found)
        return matches

    def _match_one(
        self, chain: list[ActionRecord], pattern: ChainPattern
    ) -> list[PatternMatch]:
        """对单个模式在链上做子序列匹配 (多起点推进式, gap 容忍)。

        修复:
        - G2-I1: ``gap_count`` 准确计数匹配段内的无关动作 (span - 命中数),
           gap 惩罚在置信度计算中真实生效。
        - G2-I2: 对每个满足 seq[0] 的位置作为独立起点推进匹配, 重置不再
           "消费"当前记录 → 穿插伪装步骤无法使真实攻击链整体漏检。

        匹配段为最短完整匹配 (一旦完整命中立即记录)。
        """
        n = len(chain)
        seq = pattern.sequence
        if n == 0 or not seq:
            return []

        results: list[PatternMatch] = []
        m = len(seq)

        # 每个满足 seq[0] 的位置作为起点
        for start in range(n):
            if not seq[0].matches(chain[start]):
                continue
            matched: list[ActionRecord] = [chain[start]]
            cursor = 1
            gap = 0
            end = start
            i = start + 1
            while i < n and cursor < m:
                if seq[cursor].matches(chain[i]):
                    matched.append(chain[i])
                    cursor += 1
                    gap = 0
                    end = i
                else:
                    gap += 1
                    if gap > self.max_gap:
                        break
                i += 1
            if cursor == m:
                # gap_count = 匹配段内无关动作数 = span - 命中数
                span = end - start + 1
                gap_count = max(0, span - m)
                results.append(
                    PatternMatch(
                        pattern=pattern,
                        start_index=start,
                        end_index=end,
                        matched_records=matched,
                        gap_count=gap_count,
                    )
                )
        return results


# ---- 内置 8 模式 ----

_BUILTIN_PATTERNS: list[ChainPattern] = [
    ChainPattern(
        pattern_id="supply_chain_lie",
        name="软件供应链欺骗",
        sequence=[
            ActionMatcher(category=ActionCategory.EXTERNAL, action_contains="submit"),
            # G2-I3 误报缓解: review 步骤要求来自未声明/伪造身份 (via_undeclared_identity),
            # 正常开源协作中"可信身份的代码审查"不命中 → 不误报正常流程。
            # 该标记由 G1 身份指纹 (未声明账号检出) 联动标注 (预留接口)。
            ActionMatcher(
                category=ActionCategory.IDENTITY,
                action_contains="review",
                metadata_pred=lambda m: bool(m.get("via_undeclared_identity")),
                label="review/endorse",
            ),
            ActionMatcher(category=ActionCategory.COMMUNICATE, action_contains="thank"),
        ],
        severity="CRITICAL",
        weight=1.5,
        description="提交恶意代码 → 假身份审查背书 → 假感谢闭环 (AISI 发现①, 需未声明身份标记)",
    ),
    ChainPattern(
        pattern_id="se_human_lure",
        name="社交工程诱骗",
        sequence=[
            ActionMatcher(category=ActionCategory.COMMUNICATE, action_contains="send"),
            ActionMatcher(category=ActionCategory.CREATE, action_contains="attach"),
            ActionMatcher(category=ActionCategory.EXECUTE),
        ],
        severity="CRITICAL",
        weight=1.4,
        description="向真人发送消息 → 附件 → 诱导运行代码 (AISI 发现②)",
    ),
    ChainPattern(
        pattern_id="credential_harvest",
        name="凭证收割",
        sequence=[
            ActionMatcher(
                category=ActionCategory.COMMUNICATE,
                action_contains="credential",
                label="solicit_credential",
            ),
            ActionMatcher(category=ActionCategory.CREDENTIAL, action_contains="receive"),
        ],
        severity="HIGH",
        weight=1.3,
        description="索要凭证 → 接收 (AISI 发现②社交工程)",
    ),
    ChainPattern(
        pattern_id="identity_rotation",
        name="身份轮换",
        sequence=[
            ActionMatcher(category=ActionCategory.IDENTITY, action_contains="create"),
            ActionMatcher(category=ActionCategory.IDENTITY, action_contains="create"),
            ActionMatcher(
                category=ActionCategory.IDENTITY,
                action_contains="rotate",
                label="rotate/abandon",
            ),
        ],
        severity="HIGH",
        weight=1.2,
        description="连续创建身份 → 弃旧换新 (AISI 发现①伪造身份)",
    ),
    ChainPattern(
        pattern_id="record_tamper",
        name="掩盖痕迹",
        sequence=[
            ActionMatcher(category=ActionCategory.UPDATE, action_contains="history"),
            ActionMatcher(category=ActionCategory.IDENTITY, action_contains="switch"),
        ],
        severity="HIGH",
        weight=1.2,
        description="篡改历史记录 → 切换身份续作 (AISI 发现①掩盖痕迹)",
    ),
    ChainPattern(
        pattern_id="anonymous_evasion",
        name="匿名规避",
        sequence=[
            ActionMatcher(category=ActionCategory.NETWORK),
            ActionMatcher(
                category=ActionCategory.NETWORK,
                metadata_pred=lambda m: bool(m.get("egress_changed")),
                label="egress_change",
            ),
        ],
        severity="MEDIUM",
        weight=1.0,
        description="网络访问 → 切换出口 (Tor/代理逃避监控)",
    ),
    ChainPattern(
        pattern_id="cross_agent_share",
        name="跨代理遗产共享",
        sequence=[
            ActionMatcher(
                category=ActionCategory.COMMUNICATE,
                metadata_pred=lambda m: bool(m.get("share_resource")),
                label="public_share",
            ),
            ActionMatcher(category=ActionCategory.IDENTITY, action_contains="reuse"),
        ],
        severity="HIGH",
        weight=1.3,
        description="公开留言共享账号/遗产 → 其他代理复用 (AISI 发现④)",
    ),
    ChainPattern(
        pattern_id="code_inject_hide",
        name="注入隐藏",
        sequence=[
            ActionMatcher(
                category=ActionCategory.UPDATE,
                action_contains="inject",
                label="inject_instruction",
            ),
            ActionMatcher(category=ActionCategory.DELETE, action_contains="trace"),
        ],
        severity="HIGH",
        weight=1.2,
        description="注入隐藏指令 → 清理痕迹 (AISI 发现③提示注入)",
    ),
]
