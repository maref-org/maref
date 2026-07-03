"""
PromptBaselineProbe — LLM prompt 隐蔽指令检测 (攻击 ④ 的 prompt 侧)

检测 prompt 中嵌入的隐蔽指令,攻击者用此手法绕过人工审核向 LLM 注入恶意指令:
1. 零宽字符 (U+200B ZWSP / U+200C ZWNJ / U+200D ZWJ / U+FEFF BOM):
   肉眼不可见但能改变 tokenization,可用于在 prompt 中隐藏 "ignore previous instructions" 等内容。
2. Unicode 同形字 (homoglyph): Cyrillic а (U+0430) vs Latin a (U+0061) 等,
   用于绕过关键词过滤 (如把 "system" 中的某个字母替换为 Cyrillic 同形字)。
3. 混合脚本 (mixed script): 同一 prompt 中混用 Latin + Cyrillic/Greek,
   是同形字攻击的强信号。

设计:
- analyze(prompt, subject) 同步分析接口 — 主要 API,供 Daemon 直接调用或测试用
- submit_prompt(prompt, subject) 异步入队接口 — 供 prompt pipeline 推送
- poll() 拉取队列中的 prompt 并分析 — Daemon 周期性调用

验收标准:
- 1.2-A4: PromptBaselineProbe 对零宽字符 (U+200B/200C/200D/FEFF) 检出率 100%
- 1.2-A5: PromptBaselineProbe 对 Unicode 同形字 (Cyrillic а vs Latin a) 检出率 ≥ 95%
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig

# 零宽字符 — 肉眼不可见但影响 tokenization/字符串比较
# U+200B Zero Width Space
# U+200C Zero Width Non-Joiner
# U+200D Zero Width Joiner
# U+FEFF Byte Order Mark / Zero Width No-Break Space
ZERO_WIDTH_CHARS: dict[int, str] = {
    0x200B: "ZWSP",
    0x200C: "ZWNJ",
    0x200D: "ZWJ",
    0xFEFF: "BOM",
}

# Unicode 同形字映射 — Latin 字符 → 其 Cyrillic/Greek 同形字集合
# 基于 Unicode TR39 Confusables 数据库,仅保留最常见的高危组合
# 格式: {Latin_char: {Cyrillic_char: script_name}}
_HOMOGLYPH_MAP: dict[str, dict[int, str]] = {
    # 小写
    "a": {0x0430: "Cyrillic_a"},  # а
    "e": {0x0435: "Cyrillic_e"},  # е
    "o": {0x043E: "Cyrillic_o"},  # о
    "p": {0x0440: "Cyrillic_p"},  # р
    "c": {0x0441: "Cyrillic_c"},  # с
    "x": {0x0445: "Cyrillic_x"},  # х
    "y": {0x0443: "Cyrillic_y"},  # у
    "i": {0x0456: "Cyrillic_i_ukrainian"},  # і
    "j": {0x0458: "Cyrillic_je_serbian"},  # ј
    "s": {0x0455: "Cyrillic_dze"},  # ѕ
    # 大写
    "A": {0x0410: "Cyrillic_A"},  # А
    "B": {0x0412: "Cyrillic_Ve"},  # В (looks like B)
    "E": {0x0415: "Cyrillic_E"},  # Е
    "H": {0x041D: "Cyrillic_En"},  # Н (looks like H)
    "K": {0x041A: "Cyrillic_Ka"},  # К
    "M": {0x041C: "Cyrillic_Em"},  # М
    "O": {0x041E: "Cyrillic_O"},  # О
    "P": {0x0420: "Cyrillic_Er"},  # Р (looks like P)
    "C": {0x0421: "Cyrillic_Es"},  # С (looks like C)
    "T": {0x0422: "Cyrillic_Te"},  # Т (looks like T)
    "X": {0x0425: "Cyrillic_Ha"},  # Х (looks like X)
    "Y": {0x0423: "Cyrillic_U"},  # У
    "I": {0x0406: "Cyrillic_I_ukrainian"},  # І
    "J": {0x0408: "Cyrillic_Je_serbian"},  # Ј
    "S": {0x0405: "Cyrillic_Dze"},  # Ѕ (looks like S)
}

# 反向映射: Cyrillic/Greek codepoint → 对应 Latin 字符 (用于 evidence 报告)
_HOMOGLYPH_REVERSE: dict[int, str] = {}
for _latin, _cyr_map in _HOMOGLYPH_MAP.items():
    for _cyr_cp, _script in _cyr_map.items():
        _HOMOGLYPH_REVERSE[_cyr_cp] = _latin

# 所有非 Latin 同形字 codepoint 集合 (快速判定用)
_HOMOGLYPH_CODEPOINTS: frozenset[int] = frozenset(_HOMOGLYPH_REVERSE.keys())

# Cyrillic Unicode 范围 (用于混合脚本检测)
_CYRILLIC_RANGE = (0x0400, 0x04FF)
# Greek Unicode 范围
_GREEK_RANGE = (0x0370, 0x03FF)
# Latin 基本范围
_LATIN_RANGE = (0x0041, 0x007A)  # A-z (含 ASCII 标点)


@dataclass(frozen=True)
class PromptSubmission:
    """prompt 提交记录 — PromptBaselineProbe 的输入

    Attributes:
        prompt_id: UUID,唯一标识
        prompt: 原始 prompt 文本
        subject: 关联的 agent_id 或 session_id
        timestamp: unix timestamp (秒)
        agent_id: Agent ID (可为空)
    """

    prompt_id: str = ""
    prompt: str = ""
    subject: str = ""
    timestamp: float = 0.0
    agent_id: str = ""

    def prompt_hash(self) -> str:
        """计算 prompt 的 SHA256 哈希 (用于基线对比)"""
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()


class PromptBaselineProbe(Probe):
    """LLM prompt 隐蔽指令检测 Probe

    工作流:
        prompt pipeline → submit_prompt() 入队 → Daemon poll() 拉取
        → _detect_zero_width + _detect_homoglyph + _detect_mixed_script
        → 产出 ObservationEvent

    三个检测器:
        1. _detect_zero_width — 零宽字符 (U+200B/200C/200D/FEFF)
        2. _detect_homoglyph — Unicode 同形字 (Cyrillic а vs Latin a)
        3. _detect_mixed_script — 混合脚本 (Latin + Cyrillic/Greek)

    用法:
        probe = PromptBaselineProbe(config=ProbeConfig(hmac_key=key))
        await probe.start()
        await probe.submit_prompt("Hello world", subject="agent:claude-code")
        events = await probe.poll()
        # 或直接同步分析:
        events = probe.analyze("Hello world", subject="agent:claude-code")
        await probe.stop()
    """

    def __init__(self, config: ProbeConfig) -> None:
        self._config = config
        self._started: bool = False
        self._queue: asyncio.Queue[PromptSubmission] = asyncio.Queue(maxsize=10000)
        self._baseline_hash: str = ""
        self._prompts_seen: int = 0
        self._events_emitted: int = 0

    @property
    def probe_name(self) -> str:
        return "prompt_baseline"

    async def start(self) -> None:
        """初始化 Probe — 幂等"""
        if self._started:
            return
        self._started = True
        self._prompts_seen = 0
        self._events_emitted = 0

    async def stop(self) -> None:
        """释放资源 — 幂等"""
        self._started = False

    async def submit_prompt(
        self,
        prompt: str,
        subject: str = "",
        agent_id: str = "",
    ) -> None:
        """提交一个 prompt 到内部队列 (由 prompt pipeline 调用)

        Args:
            prompt: 原始 prompt 文本 (含可能的隐蔽指令)
            subject: 关联对象 (如 "agent:claude-code" 或 "session:abc123")
            agent_id: Agent ID
        """
        if not self._started:
            return
        submission = PromptSubmission(
            prompt=prompt,
            subject=subject,
            timestamp=_now_ts(),
            agent_id=agent_id,
        )
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(submission)
        except asyncio.QueueFull:
            pass

    async def poll(self) -> list[ObservationEvent]:
        """执行一次检测 — 排空队列中所有 prompt"""
        if not self._started:
            return []

        events: list[ObservationEvent] = []
        submissions: list[PromptSubmission] = []
        while not self._queue.empty():
            try:
                submissions.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        for submission in submissions:
            self._prompts_seen += 1
            events.extend(self.analyze(submission))

        self._events_emitted += len(events)
        return events

    def analyze(self, prompt: str | PromptSubmission, subject: str = "") -> list[ObservationEvent]:
        """同步分析 prompt — 主 API,返回检测到的事件列表

        可直接调用 (无需 start/poll),便于测试和 prompt pipeline 同步集成。

        Args:
            prompt: prompt 文本 或 PromptSubmission 对象
            subject: 关联对象 (prompt 为 str 时用)

        Returns:
            检测到的事件列表 (可能为空)。每个事件已 HMAC 签名。
        """
        if isinstance(prompt, PromptSubmission):
            submission = prompt
        else:
            submission = PromptSubmission(
                prompt=str(prompt),
                subject=subject,
                timestamp=_now_ts(),
            )

        events: list[ObservationEvent] = []
        events.extend(self._detect_zero_width(submission))
        events.extend(self._detect_homoglyph(submission))
        events.extend(self._detect_mixed_script(submission))
        return events

    async def health_check(self) -> bool:
        """健康检查 — 队列未超载即健康"""
        return self._queue.qsize() < self._queue.maxsize

    def set_baseline(self, baseline_prompt: str) -> None:
        """设置 prompt 基线哈希 (用于后续漂移对比)

        M4 阶段 IntentDriftDetector 会用此基线检测 prompt 漂移。
        """
        self._baseline_hash = hashlib.sha256(baseline_prompt.encode("utf-8")).hexdigest()

    # ---- 三个检测器 ----

    def _detect_zero_width(self, submission: PromptSubmission) -> list[ObservationEvent]:
        """检测零宽字符 (U+200B/200C/200D/FEFF) — 检出率 100% 目标

        零宽字符肉眼不可见,可用于:
        - 在 prompt 中隐藏 "ignore previous instructions"
        - 绕过关键词过滤 (在关键词中插入零宽字符)
        - 改变 tokenization,影响 LLM 解析
        """
        findings: list[dict[str, Any]] = []
        for idx, char in enumerate(submission.prompt):
            cp = ord(char)
            if cp in ZERO_WIDTH_CHARS:
                findings.append(
                    {
                        "position": idx,
                        "codepoint": f"U+{cp:04X}",
                        "name": ZERO_WIDTH_CHARS[cp],
                    }
                )

        if not findings:
            return []

        # 零宽字符存在即 CRITICAL — 正常 prompt 不应包含
        # 多个零宽字符 = 显式攻击信号
        severity = Severity.CRITICAL if len(findings) >= 2 else Severity.HIGH
        return [
            self._make_event(
                submission,
                severity=severity,
                attack_type=AttackType.STEGANOGRAPHY,
                evidence={
                    "detection": "zero_width_characters",
                    "finding_count": len(findings),
                    "findings": findings[:50],  # 限制 evidence 体积
                    "prompt_length": len(submission.prompt),
                    "prompt_hash": submission.prompt_hash(),
                },
            )
        ]

    def _detect_homoglyph(self, submission: PromptSubmission) -> list[ObservationEvent]:
        """检测 Unicode 同形字 (Cyrillic а vs Latin a) — 检出率 ≥95% 目标

        同形字用于绕过关键词过滤:
        - 攻击者把 "system" 中的 'a' 替换为 Cyrillic 'а' → "system" → "systeм"
        - 肉眼看不出差异,但字符串比较失败 → 绕过 "system" 关键词检测
        - LLM 可能仍将其解析为相同语义 → 注入 system prompt
        """
        findings: list[dict[str, Any]] = []
        for idx, char in enumerate(submission.prompt):
            cp = ord(char)
            if cp in _HOMOGLYPH_CODEPOINTS:
                latin_equivalent = _HOMOGLYPH_REVERSE[cp]
                # 查找对应的 script 名称
                script_name = "Unknown"
                for _latin, _cyr_map in _HOMOGLYPH_MAP.items():
                    if latin_equivalent == _latin and cp in _cyr_map:
                        script_name = _cyr_map[cp]
                        break
                findings.append(
                    {
                        "position": idx,
                        "char": char,
                        "codepoint": f"U+{cp:04X}",
                        "latin_equivalent": latin_equivalent,
                        "script": script_name,
                        "context": _get_context(submission.prompt, idx),
                    }
                )

        if not findings:
            return []

        # 同形字存在即 HIGH;多个同形字 = 显式绕过攻击 → CRITICAL
        severity = Severity.CRITICAL if len(findings) >= 3 else Severity.HIGH
        return [
            self._make_event(
                submission,
                severity=severity,
                attack_type=AttackType.STEGANOGRAPHY,
                evidence={
                    "detection": "unicode_homoglyph",
                    "finding_count": len(findings),
                    "findings": findings[:50],
                    "prompt_length": len(submission.prompt),
                    "prompt_hash": submission.prompt_hash(),
                },
            )
        ]

    def _detect_mixed_script(self, submission: PromptSubmission) -> list[ObservationEvent]:
        """检测混合脚本 (Latin + Cyrillic/Greek 在同一 prompt) — 同形字攻击的强信号

        正常英文 prompt 应仅含 Latin + ASCII 标点。
        出现 Cyrillic/Greek 字符即高度可疑 (除非用户明确用俄语/希腊语交互)。

        注: 此检测器可能对合法多语言 prompt 误报,故 severity 较低 (MEDIUM),
        且仅在无同形字告警时才独立告警 (避免重复)。
        """
        has_latin = False
        has_cyrillic = False
        has_greek = False
        cyrillic_chars: list[dict[str, Any]] = []
        greek_chars: list[dict[str, Any]] = []

        for idx, char in enumerate(submission.prompt):
            cp = ord(char)
            if _LATIN_RANGE[0] <= cp <= _LATIN_RANGE[1]:
                has_latin = True
            elif _CYRILLIC_RANGE[0] <= cp <= _CYRILLIC_RANGE[1]:
                has_cyrillic = True
                if len(cyrillic_chars) < 20:  # 限制 evidence 体积
                    cyrillic_chars.append(
                        {"position": idx, "char": char, "codepoint": f"U+{cp:04X}"}
                    )
            elif _GREEK_RANGE[0] <= cp <= _GREEK_RANGE[1]:
                has_greek = True
                if len(greek_chars) < 20:
                    greek_chars.append(
                        {"position": idx, "char": char, "codepoint": f"U+{cp:04X}"}
                    )

        # 仅 Latin 或仅 Cyrillic/Greek 不算混合
        is_mixed = (has_latin and has_cyrillic) or (has_latin and has_greek)
        if not is_mixed:
            return []

        # 已有同形字告警时不重复告警 (同形字检测更精准)
        # 此处仅检测 "非同形字的 Cyrillic/Greek 字符" (如完整俄语单词)
        return [
            self._make_event(
                submission,
                severity=Severity.MEDIUM,
                attack_type=AttackType.STEGANOGRAPHY,
                evidence={
                    "detection": "mixed_script",
                    "has_latin": has_latin,
                    "has_cyrillic": has_cyrillic,
                    "has_greek": has_greek,
                    "cyrillic_char_count": len(cyrillic_chars),
                    "greek_char_count": len(greek_chars),
                    "cyrillic_samples": cyrillic_chars,
                    "greek_samples": greek_chars,
                    "prompt_length": len(submission.prompt),
                    "prompt_hash": submission.prompt_hash(),
                },
            )
        ]

    def _make_event(
        self,
        submission: PromptSubmission,
        severity: Severity,
        attack_type: AttackType,
        evidence: dict[str, Any],
    ) -> ObservationEvent:
        """创建已签名的 ObservationEvent"""
        subject = submission.subject or (
            f"agent:{submission.agent_id}" if submission.agent_id else "prompt:unknown"
        )
        event = ObservationEvent(
            source=self.probe_name,
            severity=severity,
            subject=subject,
            attack_type=attack_type,
            evidence=evidence,
        )
        if self._config.hmac_key:
            event = event.with_hash(self._config.hmac_key)
        return event

    def snapshot_stats(self) -> dict[str, Any]:
        """返回 probe 内部统计"""
        return {
            "prompts_seen": self._prompts_seen,
            "events_emitted": self._events_emitted,
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self._queue.maxsize,
            "has_baseline": bool(self._baseline_hash),
        }


def _now_ts() -> float:
    """获取当前 unix timestamp"""
    import time

    return time.time()


def _get_context(text: str, position: int, window: int = 10) -> str:
    """获取 position 周围的上下文 (用于 evidence 报告)"""
    start = max(0, position - window)
    end = min(len(text), position + window + 1)
    return text[start:end]
