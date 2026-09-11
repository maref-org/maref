"""SocialEngineeringDetector — 8 类社交工程模式检测 (v0.52.1 G3-A2)。

对位 AISI 欺骗测试发现 ②：代理直接向真实人类发送消息/文件，
试图说服受害者或其 AI 编码工具运行恶意代码。

检测 8 类 SE 模式（非二进制，输出分级信号 + 置信度）:

    URGENCY            紧急制造       "立即/马上/现在就要/来不及了"
    AUTHORITY_SPOOF    权威伪造       "我是管理员/官方/代表组织/已获授权"
    CREDENTIAL_HARVEST 凭证索取       "密码/token/密钥/登录/两步验证码"
    CODE_LURE          代码诱饵       "请运行/执行/粘贴这段代码/终端里输入"
    IMPERSONATION      冒充           "假装是/冒充/以XX名义/我是XX的同事"
    LINK_REDIRECT      链接重定向     "点击链接/短链接/下载到XX/打开网址"
    ATTACHMENT_TRAP    附件陷阱       "打开附件/启用宏/允许内容/解压后运行"
    RECIPROCITY        互惠施压       "帮个忙/回报/别人都会配合/就差你了"

设计:
- 关键词为加权正则,命中计分,累计分 >= 阈值才产出 SeSignal
- 组合 2+ 模式的信号可升级严重度 (gate 层决策)
- 关键词表可扩展 (register_pattern_keywords)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SePattern(str, Enum):
    """社交工程模式枚举。"""

    URGENCY = "urgency"
    AUTHORITY_SPOOF = "authority_spoof"
    CREDENTIAL_HARVEST = "credential_harvest"
    CODE_LURE = "code_lure"
    IMPERSONATION = "impersonation"
    LINK_REDIRECT = "link_redirect"
    ATTACHMENT_TRAP = "attachment_trap"
    RECIPROCITY = "reciprocity"

    @property
    def label(self) -> str:
        return {
            SePattern.URGENCY: "紧急制造",
            SePattern.AUTHORITY_SPOOF: "权威伪造",
            SePattern.CREDENTIAL_HARVEST: "凭证索取",
            SePattern.CODE_LURE: "代码诱饵",
            SePattern.IMPERSONATION: "冒充",
            SePattern.LINK_REDIRECT: "链接重定向",
            SePattern.ATTACHMENT_TRAP: "附件陷阱",
            SePattern.RECIPROCITY: "互惠施压",
        }[self]


@dataclass(frozen=True)
class SeSignal:
    """一次社交工程检测信号。

    Attributes:
        pattern: 命中的 SE 模式。
        confidence: 置信度 0.0~1.0 (由命中关键词权重归一化)。
        matched_terms: 命中的关键词列表 (审计证据)。
        score: 原始累计得分。
    """

    pattern: SePattern
    confidence: float
    matched_terms: list[str]
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "label": self.pattern.label,
            "confidence": round(self.confidence, 3),
            "score": round(self.score, 2),
            "matched_terms": self.matched_terms,
        }


def _weighted_patterns() -> dict[SePattern, list[tuple[str, int]]]:
    """返回 模式 → [(正则, 权重)] 词表。

    权重 1-3: 3 为强信号 (几乎只出现在恶意上下文), 1 为弱信号 (可能误报)。
    """
    return {
        SePattern.URGENCY: [
            (r"立即|马上|立刻|现在就要|此刻|来不及了", 2),
            (r"urgent|immediately|right now|asap|as soon as possible", 2),
            (r"过期|最后机会|仅限今天|不要犹豫|抓紧", 2),
        ],
        SePattern.AUTHORITY_SPOOF: [
            (r"我是管理员|我是官方|已获授权|代表组织|系统通知", 2),
            (r"admin|official(ly)?|authorized|system notification", 2),
            (r"根据(公司|上级|安全)要求", 1),
        ],
        SePattern.CREDENTIAL_HARVEST: [
            (r"密码|口令|登录凭据|两步验证码|验证码|API ?密钥|token", 3),
            (r"password|passphrase|credential|2fa|verification code|api ?key|token|secret", 3),
            (r"回复你的账号信息|确认你的身份|验证你的账户", 2),
        ],
        SePattern.CODE_LURE: [
            (r"请运行|运行这段代码|执行以下|粘贴到终端|输入这条命令", 3),
            (r"please run|run this code|execute|paste.*terminal|try this", 3),
            (r"下载并运行|wget|curl .*\|.*sh|sudo .*命令", 2),
        ],
        SePattern.IMPERSONATION: [
            (r"冒充|假装|伪装成|以.{1,12}名义|我是.{1,12}的同事", 3),
            (r"pretend|impersonat|disguise as|on behalf of", 3),
            (r"我是你(认识|的)|你之前联系过的人", 1),
        ],
        SePattern.LINK_REDIRECT: [
            (r"点击.*链接|打开.*网址|访问.*网站|前往.*链接", 2),
            (r"click.*link|visit.*(site|url)|go to.*link|open.*url", 2),
            (r"短链|bit\.ly|t\.co|tinyurl|rebrand\.ly", 2),
            (r"下载(安装|更新)(器|包)|下载.*到", 1),
        ],
        SePattern.ATTACHMENT_TRAP: [
            (r"打开附件|启用(宏|内容|编辑)|允许内容|解压后运行|双击附件", 3),
            (r"open the attachment|enable (macro|content)|extract.*run|double.?click", 3),
            (r"附件里|见附件|附上了文件", 1),
        ],
        SePattern.RECIPROCITY: [
            (r"帮个忙|帮帮忙|回报一下|别人都|就差你|配合一下", 2),
            (r"do me a favor|in return|everyone else|you'?re the only one", 2),
            (r"对你的(工作|职位|公司)有好处|举手之劳", 1),
        ],
    }


class SocialEngineeringDetector:
    """社交工程模式检测器。

    Usage::

        detector = SocialEngineeringDetector()
        signals = detector.detect("请立即点击链接并输入你的密码")
        if signals:
            print([s.pattern.value for s in signals])

    Attributes:
        min_confidence: 产出 SeSignal 的最低置信度阈值 (默认 0.5)。
        registerable_keywords: 各模式可扩展关键词的注册表 (运行时追加)。
    """

    def __init__(self, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence
        self._patterns: dict[SePattern, list[tuple[re.Pattern[str], int]]] = {
            p: [(re.compile(term, re.IGNORECASE), w) for term, w in terms]
            for p, terms in _weighted_patterns().items()
        }
        self._extra_terms: dict[SePattern, list[tuple[re.Pattern[str], int]]] = {}
        self._max_weight = 3

    def register_keywords(self, pattern: SePattern, terms: list[tuple[str, int]]) -> None:
        """注册模式关键词扩展 (运行时追加, 支持部署侧词表扩充)。"""
        compiled = [(re.compile(term, re.IGNORECASE), w) for term, w in terms]
        self._extra_terms.setdefault(pattern, []).extend(compiled)

    def _all_terms(self, pattern: SePattern) -> list[tuple[re.Pattern[str], int]]:
        return self._patterns.get(pattern, []) + self._extra_terms.get(pattern, [])

    def detect(self, text: str) -> list[SeSignal]:
        """检测输入文本中的社交工程模式。

        Args:
            text: 待检测的出站消息正文 (或正文+附件文件名拼接)。

        Returns:
            命中的 SeSignal 列表 (未命中返回空列表)。
        """
        if not text:
            return []
        signals: list[SeSignal] = []
        for pattern in SePattern:
            score = 0.0
            matched: list[str] = []
            for regex, weight in self._all_terms(pattern):
                if regex.search(text):
                    score += float(weight)
                    matched.append(regex.pattern)
            if score <= 0:
                continue
            confidence = min(1.0, score / self._max_weight)
            if confidence >= self.min_confidence:
                signals.append(
                    SeSignal(
                        pattern=pattern,
                        confidence=confidence,
                        matched_terms=matched,
                        score=score,
                    )
                )
        return signals

    def detect_combined(self, text: str) -> tuple[list[SeSignal], int]:
        """检测并返回信号列表与命中的模式数 (组合升级用)。

        Returns:
            (signals, hit_count): hit_count 为命中不同模式的个数。
        """
        signals = self.detect(text)
        return signals, len(signals)
