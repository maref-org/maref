"""IdentityFingerprint — 外部身份行为指纹 (v0.52.1 G1-B2)。

对同一主体在外部平台的多重身份进行行为指纹聚类。依据 AISI 观察:
伪造身份由同一模型/代理生成 → 写作风格一致、活跃时间窗口一致、
网络出口 (IP/UA) 可能相同。

指纹维度:
- 写作风格: 字符 n-gram (1-2) 频率向量 (语言无关, 中英文均适用)
- 活跃时间: 24h 分桶分布 (6 桶 × 4h)
- 网络出口: IP 哈希 / UA 哈希 (脱敏)

相似度加权: 写作 0.5 + 时间 0.2 + 出口 0.3。供 ``SybilDetector`` 聚类。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FingerprintProfile:
    """一个外部身份的完整行为指纹。

    Attributes:
        profile_id: 指纹唯一标识 (通常关联 ExternalAccount.profile_id)。
        ngram_freqs: 字符 n-gram 频率字典 (写作风格特征)。
        active_buckets: 24h 活跃分布 (6 桶, 值 = 该桶活跃次数)。
        ip_hash: 网络出口 IP 哈希。
        ua_hash: 客户端 UA 哈希。
        sample_count: 指纹样本数。
    """

    profile_id: str = ""
    ngram_freqs: dict[str, float] = field(default_factory=dict)
    active_buckets: list[int] = field(default_factory=lambda: [0] * 6)
    ip_hash: str = ""
    ua_hash: str = ""
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "ngram_count": len(self.ngram_freqs),
            "active_buckets": self.active_buckets,
            "ip_hash": self.ip_hash,
            "ua_hash": self.ua_hash,
            "sample_count": self.sample_count,
        }


# 时间桶数 (24h / 6 = 4h 每桶)
_BUCKET_COUNT = 6
_HOURS_PER_BUCKET = 24 // _BUCKET_COUNT


def _tokenize_ngrams(text: str, n: int) -> list[str]:
    """提取字符 n-gram (去空白)。"""
    if not text:
        return []
    cleaned = "".join(text.split())
    if len(cleaned) < n:
        return []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def _bucket_of(hour: float) -> int:
    """小时 → 时间桶索引 (0-5)。"""
    return min(_BUCKET_COUNT - 1, int(hour) // _HOURS_PER_BUCKET)


class IdentityFingerprint:
    """行为指纹提取与相似度比对。

    Usage::

        fp = IdentityFingerprint()
        profile_a = fp.extract_profile(
            texts=["提交了修复", "更新了文档"],
            timestamps=[t1, t2], ip_hash="h1", ua_hash="u1")
        sim = fp.similarity(profile_a, profile_b)
    """

    def extract_profile(
        self,
        texts: list[str],
        timestamps: list[float] | None = None,
        ip_hash: str = "",
        ua_hash: str = "",
        profile_id: str = "",
    ) -> FingerprintProfile:
        """从文本/活跃时间/网络出口提取行为指纹。

        Args:
            texts: 该身份产出的文本样本 (评论/提交/消息)。
            timestamps: 对应活跃时间戳列表。
            ip_hash: 网络出口 IP 哈希。
            ua_hash: 客户端 UA 哈希。
            profile_id: 指纹 ID。

        Returns:
            FingerprintProfile。
        """
        ngram_counter: Counter[str] = Counter()
        for text in texts:
            for n in (1, 2):
                for gram in _tokenize_ngrams(text, n):
                    ngram_counter[gram] += 1
        total = sum(ngram_counter.values()) or 1
        ngram_freqs = {g: c / total for g, c in ngram_counter.items()}

        buckets = [0] * _BUCKET_COUNT
        if timestamps:
            import datetime as _dt

            for ts in timestamps:
                hour = _dt.datetime.fromtimestamp(ts).hour
                buckets[_bucket_of(hour)] += 1

        return FingerprintProfile(
            profile_id=profile_id,
            ngram_freqs=ngram_freqs,
            active_buckets=buckets,
            ip_hash=ip_hash,
            ua_hash=ua_hash,
            sample_count=len(texts),
        )

    def similarity(self, a: FingerprintProfile, b: FingerprintProfile) -> float:
        """计算两个指纹的相似度 (0.0~1.0)。

        加权: 写作风格 0.5 + 活跃时间 0.2 + 网络出口 0.3。
        任一维度无数据时该维度视为中性 (不拉低整体)。
        """
        style_sim = self._style_similarity(a.ngram_freqs, b.ngram_freqs)
        time_sim = self._time_similarity(a.active_buckets, b.active_buckets)
        egress_sim = self._egress_similarity(a, b)
        return 0.5 * style_sim + 0.2 * time_sim + 0.3 * egress_sim

    def _style_similarity(self, fa: dict[str, float], fb: dict[str, float]) -> float:
        if not fa or not fb:
            return 0.5  # 中性
        keys = set(fa) | set(fb)
        dot = sum(fa.get(k, 0.0) * fb.get(k, 0.0) for k in keys)
        na = math.sqrt(sum(v * v for v in fa.values())) or 1.0
        nb = math.sqrt(sum(v * v for v in fb.values())) or 1.0
        return dot / (na * nb)

    def _time_similarity(self, ba: list[int], bb: list[int]) -> float:
        if not ba or not bb or sum(ba) == 0 or sum(bb) == 0:
            return 0.5  # 中性
        ta = sum(ba)
        tb = sum(bb)
        overlap = sum(min(ba[i] / ta, bb[i] / tb) for i in range(min(len(ba), len(bb))))
        return min(1.0, overlap)

    def _egress_similarity(self, a: FingerprintProfile, b: FingerprintProfile) -> float:
        """网络出口相似度。

        G1-I1 修复: 仅当双方都无网络数据时返中性 0.5; 任一维度有数据但
        不匹配 → 按实际匹配计分 (IP 不匹配返 0.0, 而非误当中性)。
        """
        has_data = (a.ip_hash or a.ua_hash) and (b.ip_hash or b.ua_hash)
        if not has_data:
            return 0.5  # 无网络数据 → 中性
        score = 0.0
        if a.ip_hash and b.ip_hash:
            score += 0.5 if a.ip_hash == b.ip_hash else 0.0
        if a.ua_hash and b.ua_hash:
            score += 0.5 if a.ua_hash == b.ua_hash else 0.0
        return score
