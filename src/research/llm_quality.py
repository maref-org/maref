"""LLM Quality Governance — 输出质量审计 + 心跳 + 自动恢复

三层机制:
  1. Heartbeat (高频) — 每 5 分钟轻量探测，检测假健康 (200 但空内容/无效响应)
  2. Quality Assessment (低频) — 每 30 分钟按能力维度评分，更新 business_fitness
  3. Auto-Recovery — 对连续失败的提供商按指数退避重试，自动拉起

路由决策集成:
  weight = quality_score^2 * business_fitness[capability] / (cost_per_token + ε)
  选择 weight 最高的提供商
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from research.model_registry import ModelCapability

logger = logging.getLogger("llm_quality")

# ── 持久化路径 ──────────────────────────────────────────────────────────

QUALITY_STORE_DIR = os.path.expanduser("~/.claude/llm_cache")
QUALITY_STORE_PATH = os.path.join(QUALITY_STORE_DIR, "quality_store.json")

# 仓库工作区质量画像路径（随仓库可审计，GAP-1 补强）
REPO_QUALITY_STORE_REL = ".openclaw/llm_quality/quality_store.json"


# ── 健康状态 ─────────────────────────────────────────────────────────────


class ProviderHealth(Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"       # 存活但质量低
    STALLED = "stalled"         # 心跳失败但未超时
    DOWN = "down"               # 完全不可用
    RECOVERING = "recovering"   # 自动恢复中


@dataclass
class ProviderStatus:
    """单个提供商的完整状态"""

    provider_key: str
    health: ProviderHealth = ProviderHealth.UNKNOWN

    # 心跳数据
    last_heartbeat: float = 0.0
    heartbeat_interval: float = 300.0  # 5 分钟
    consecutive_heartbeat_failures: int = 0
    max_heartbeat_failures: int = 3    # 连续 3 次标记 DOWN

    # 质量评分 (0.0 - 1.0)
    overall_quality: float = 0.0
    business_fitness: dict[str, float] = field(default_factory=dict)
    # 例如: {"coding": 0.95, "reasoning": 0.80, "creative": 0.60}

    # 性能指标
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    total_calls: int = 0
    total_errors: int = 0
    total_tokens: int = 0

    # 自动恢复
    last_recovery_attempt: float = 0.0
    recovery_backoff: float = 60.0   # 初始 1 分钟
    recovery_attempts: int = 0
    max_recovery_attempts: int = 10

    # 上次错误
    last_error: str = ""
    last_error_time: float = 0.0

    # 业务标签 (可手动标注)
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def is_available(self) -> bool:
        """路由决策用：是否可用于请求"""
        return self.health in (ProviderHealth.HEALTHY, ProviderHealth.DEGRADED, ProviderHealth.RECOVERING)

    @property
    def uptime_ratio(self) -> float:
        if self.total_calls + self.total_errors == 0:
            return 1.0
        return self.total_calls / (self.total_calls + self.total_errors)


# ═══════════════════════════════════════════════════════════════════════════
# 质量评估器
# ═══════════════════════════════════════════════════════════════════════════


# 标准测试题 — 每个能力维度一组 (覆盖全部 10 种 ModelCapability)
BENCHMARK_PROMPTS: dict[ModelCapability, list[dict[str, str]]] = {
    ModelCapability.CODING: [
        {"system": "You are a Python expert.", "prompt": "Write a function to merge two sorted lists."},
        {"system": "You are a code reviewer.", "prompt": "Review this code: def f(x): return x*2"},
    ],
    ModelCapability.REASONING: [
        {"system": "You are a logician.", "prompt": "If all A are B, and some B are C, can we conclude some A are C? Explain."},
        {"system": "You are a math tutor.", "prompt": "What is 7 * 8 + 12 / 4? Show steps."},
    ],
    ModelCapability.ANALYSIS: [
        {"system": "You are a data analyst.", "prompt": "Given sales=[120,85,200,95,150], what's the trend?"},
    ],
    ModelCapability.CREATIVE: [
        {"system": "You are a copywriter.", "prompt": "Write a tagline for a eco-friendly water bottle."},
    ],
    ModelCapability.CHAT: [
        {"system": "You are helpful.", "prompt": "Say hello in exactly 5 words."},
    ],
    ModelCapability.VISION: [
        {"system": "You are a vision AI assistant.", "prompt": "Describe what a robot vacuum cleaner might look like in 3 sentences."},
    ],
    ModelCapability.FUNCTION_CALLING: [
        {"system": "You are a function-calling agent. Respond with a JSON tool call.", "prompt": "Call get_weather(location='Beijing') to check today's forecast."},
    ],
    ModelCapability.RAG: [
        {"system": "You are a RAG system. Answer based only on the provided context.", "prompt": "Context: The Eiffel Tower was built in 1889. Question: When was the Eiffel Tower built?"},
    ],
    ModelCapability.AGENTIC: [
        {"system": "You are a planning agent. Break down the user's request into steps.", "prompt": "Plan how to book a flight from Beijing to New York."},
    ],
    ModelCapability.SPEED: [
        {"system": "You are a fast responder. Reply in under 20 tokens.", "prompt": "Say 'ok' and nothing else."},
    ],
}


def _score_response(response: str) -> float:
    """对 LLM 响应质量打 0.0-1.0 分

    启发式评分:
      - 空响应 → 0
      - 纯推理链无回答 → 0.2
      - 有内容 → 根据长度、相关性等
    """
    if not response or not response.strip():
        return 0.0

    # 检查是否只有推理链无实质内容
    reasoning_keywords = ["let me", "i need to", "first,", "the user", "we need to", "分析:", "我们需要", "首先"]
    if len(response) < 10 and any(k in response.lower() for k in reasoning_keywords):
        return 0.2

    # 检查是否包含实质回答
    content_len = len(response.strip())
    if content_len < 5:
        return 0.3
    if content_len < 20:
        return 0.6
    if content_len > 500:
        return 0.9  # 详细回答

    # 平均分
    return 0.75


class QualityAssessor:
    """质量评估器 — 定期对提供商按能力维度评分"""

    def __init__(self, chat_fn: Callable | None = None) -> None:
        """
        Args:
            chat_fn: async callable(provider, messages) -> str | None
                      用于实际调用 LLM 的回调函数
        """
        self._chat_fn = chat_fn
        self._scores: dict[str, dict[str, float]] = {}  # provider -> {capability: score}

    async def assess_provider(
        self,
        provider_key: str,
        chat_fn: Callable | None = None,
    ) -> dict[str, float]:
        """对单个提供商按所有能力维度评分"""
        fn = chat_fn or self._chat_fn
        if fn is None:
            logger.warning("QualityAssessor: no chat_fn provided, using defaults")
            return {}

        scores: dict[str, float] = {}
        for cap, prompts in BENCHMARK_PROMPTS.items():
            cap_scores: list[float] = []
            for p in prompts:
                try:
                    result = await fn(
                        provider_key,
                        [{"role": "system", "content": p["system"]},
                         {"role": "user", "content": p["prompt"]}],
                    )
                    if result:
                        score = _score_response(result)
                        cap_scores.append(score)
                    else:
                        cap_scores.append(0.0)
                except Exception as e:
                    logger.debug("QA assess %s %s failed: %s", provider_key, cap.value, e)
                    cap_scores.append(0.0)

            scores[cap.value] = sum(cap_scores) / len(cap_scores) if cap_scores else 0.0

        self._scores[provider_key] = scores
        return scores

    async def assess_all(
        self,
        provider_keys: list[str],
        chat_fn: Callable | None = None,
    ) -> dict[str, dict[str, float]]:
        """对所有提供商评分（并发执行）"""
        tasks = [self.assess_provider(pk, chat_fn) for pk in provider_keys]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        results: dict[str, dict[str, float]] = {}
        for pk, result in zip(provider_keys, results_list, strict=True):
            if isinstance(result, Exception):
                logger.error("QualityAssessor.assess_all: %s failed: %s", pk, result)
                results[pk] = {}
            else:
                if isinstance(result, dict):
                    results[pk] = result
        return results

    def get_scores(self, provider_key: str) -> dict[str, float]:
        return self._scores.get(provider_key, {})


# ═══════════════════════════════════════════════════════════════════════════
# 心跳探测器
# ═══════════════════════════════════════════════════════════════════════════


class HeartbeatProber:
    """增强心跳探测 — 检测假健康

    不同于普通 health check（只检查 200），这个探测器还会:
    - 验证响应包含有效内容（非空、非纯错误）
    - 检查延迟是否异常
    - 识别 content="" 但 reasoning_content 有内容的"假回答"
    """

    def __init__(self, probe_fn: Callable | None = None) -> None:
        """
        Args:
            probe_fn: async callable(provider_key) -> (success, latency_ms, error)
        """
        self._probe_fn = probe_fn

    async def deep_probe(
        self,
        provider_key: str,
        probe_fn: Callable | None = None,
    ) -> tuple[bool, float, str]:
        """深度探测 — 返回 (success, latency_ms, error_message)

        比普通 probe 更严格:
        - HTTP 200 还不够
        - 必须返回有意义的 content
        - 延迟不能超过阈值（默认 30s）
        """
        fn = probe_fn or self._probe_fn
        if fn is None:
            return False, 0, "no probe_fn configured"

        t0 = time.perf_counter()
        try:
            success, content, error = await fn(provider_key)
            elapsed = (time.perf_counter() - t0) * 1000

            if not success:
                return False, elapsed, error or "probe returned failure"

            # 假健康检测: 空内容
            if not content or not content.strip():
                return False, elapsed, "empty response (possible false healthy)"

            # 假健康检测: 纯推理链（无实质回答）
            reasoning_keywords = ["let me", "i need to", "we need to", "分析:", "我们需要"]
            if len(content) > 0 and len(content) < 15 and any(k in content.lower() for k in reasoning_keywords):
                return False, elapsed, "reasoning-only response (no actual content)"

            # 延迟异常检测
            if elapsed > 30000:
                return False, elapsed, f"latency too high: {elapsed:.0f}ms"

            return True, elapsed, ""

        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return False, elapsed, str(e)


# ═══════════════════════════════════════════════════════════════════════════
# 健康状态存储
# ═══════════════════════════════════════════════════════════════════════════


class HealthStore:
    """持久化健康状态存储"""

    def __init__(self, path: str = QUALITY_STORE_PATH) -> None:
        self._path = path
        self._statuses: dict[str, ProviderStatus] = {}
        self._dirty = False
        self._load()

    # ── 访问器 ──────────────────────────────────────────────────────────

    @property
    def store_path(self) -> str:
        """公开 store 文件路径（替代直接访问 _path）"""
        return self._path

    def get_all_statuses(self) -> dict[str, ProviderStatus]:
        """返回所有状态字典的副本（替代直接访问 _statuses）"""
        return dict(self._statuses)

    def get(self, provider_key: str) -> ProviderStatus:
        if provider_key not in self._statuses:
            self._statuses[provider_key] = ProviderStatus(provider_key=provider_key)
            self._dirty = True  # New entry needs saving
        return self._statuses[provider_key]

    def set_health(self, provider_key: str, health: ProviderHealth) -> None:
        """Set health state explicitly (e.g. from external probe)."""
        s = self.get(provider_key)
        s.health = health
        self._dirty = True

    def get_healthy(self) -> list[str]:
        """返回当前可用的提供商列表"""
        return [k for k, s in self._statuses.items() if s.is_available]

    def get_quality_ranking(self, capability: str = "") -> list[tuple[str, float]]:
        """按质量排序，可选按能力维度过滤"""
        rankings: list[tuple[str, float]] = []
        for k, s in self._statuses.items():
            if capability and capability in s.business_fitness:
                score = s.business_fitness[capability]
            else:
                score = s.overall_quality
            rankings.append((k, score))
        rankings.sort(key=lambda x: -x[1])
        return rankings

    # ── 更新器 ──────────────────────────────────────────────────────────

    def record_heartbeat(self, provider_key: str, success: bool, latency_ms: float, error: str = "") -> None:
        s = self.get(provider_key)
        s.last_heartbeat = time.time()
        s.avg_latency_ms = (s.avg_latency_ms * 0.7 + latency_ms * 0.3)  # EMA

        if success:
            s.consecutive_heartbeat_failures = 0
            s.last_error = ""
            if s.health == ProviderHealth.DOWN:
                s.health = ProviderHealth.RECOVERING
            elif s.health in (ProviderHealth.STALLED, ProviderHealth.UNKNOWN):
                s.health = ProviderHealth.HEALTHY
        else:
            s.consecutive_heartbeat_failures += 1
            s.last_error = error
            s.last_error_time = time.time()
            if s.consecutive_heartbeat_failures >= s.max_heartbeat_failures:
                s.health = ProviderHealth.DOWN
            elif s.consecutive_heartbeat_failures >= 1:
                s.health = ProviderHealth.STALLED

        self._dirty = True

    def record_quality(
        self,
        provider_key: str,
        capability_scores: dict[str, float],
    ) -> None:
        s = self.get(provider_key)
        s.business_fitness = capability_scores
        s.overall_quality = sum(capability_scores.values()) / len(capability_scores) if capability_scores else 0.0
        self._dirty = True

    def record_call(self, provider_key: str, success: bool, tokens: int = 0) -> None:
        s = self.get(provider_key)
        if success:
            s.total_calls += 1
            s.total_tokens += tokens
        else:
            s.total_errors += 1
        s.error_rate = s.total_errors / (s.total_calls + s.total_errors + 1)
        self._dirty = True

    def mark_recovering(self, provider_key: str) -> None:
        s = self.get(provider_key)
        s.health = ProviderHealth.RECOVERING
        s.recovery_attempts += 1
        s.last_recovery_attempt = time.time()
        self._dirty = True

    def reset_recovery(self, provider_key: str) -> None:
        s = self.get(provider_key)
        s.health = ProviderHealth.HEALTHY
        s.consecutive_heartbeat_failures = 0
        s.recovery_attempts = 0
        s.recovery_backoff = 60.0
        self._dirty = True

    # ── 路由权重计算 ───────────────────────────────────────────────────

    def compute_weight(
        self,
        provider_key: str,
        capability: ModelCapability | str | None = None,
        cost_per_1k: float = 0.01,
    ) -> float:
        """计算路由权重: quality^2 * fitness / (cost + ε)

        用于替代简单的 priority 排序
        """
        s = self.get(provider_key)

        # GAP-1 补强: 无历史数据(冷启动/空库) → 返回中性权重, 仅按 cost 排序。
        # 避免空库时 is_available=False 把 provider 全部判不可用(-1.0),
        # 导致 _probe_healthy 质量排序退化为无区分。
        # 有 error 记录/非 UNKNOWN 健康态均不视为冷启动。
        if (s.health == ProviderHealth.UNKNOWN
                and s.total_calls == 0 and s.total_errors == 0
                and s.overall_quality == 0.0):
            return 1.0 / (cost_per_1k + 0.001)

        if not s.is_available:
            return -1.0

        base = s.overall_quality ** 2  # quality 平方，拉开差距

        if capability:
            cap_str = capability.value if isinstance(capability, ModelCapability) else capability
            fitness = s.business_fitness.get(cap_str, 0.5)
            base *= fitness
        else:
            base *= 0.8  # 无指定能力时降权

        epsilon = 0.001
        cost_factor = 1.0 / (cost_per_1k + epsilon)

        return base * cost_factor

    # ── 持久化 ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path) as f:
                data = json.load(f)
            for pk, d in data.get("providers", {}).items():
                s = ProviderStatus(provider_key=pk)
                for key in d:
                    if hasattr(s, key):
                        if key == "health":
                            try:
                                s.health = ProviderHealth(d[key])
                            except ValueError:
                                s.health = ProviderHealth.UNKNOWN
                        else:
                            setattr(s, key, d[key])
                self._statuses[pk] = s
            logger.info("HealthStore loaded %d providers from %s", len(self._statuses), self._path)
        except Exception as e:
            logger.warning("HealthStore load failed: %s", e)

    def save(self) -> None:
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data: dict[str, Any] = {
            "_saved_at": datetime.now().isoformat(),
            "providers": {},
        }
        for pk, s in self._statuses.items():
            d = {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
            d["health"] = s.health.value
            data["providers"][pk] = d
        with open(self._path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._dirty = False
        logger.debug("HealthStore saved to %s", self._path)

    def export_to_repo(self, repo_root: str) -> str:
        """GAP-1 补强: 镜像质量画像到仓库工作区, 随仓库可审计。

        返回写入的仓库路径; 写入失败仅告警不中断(仓库只读/无权限时静默降级)。
        """
        try:
            target = os.path.join(repo_root, REPO_QUALITY_STORE_REL)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            data: dict[str, Any] = {
                "_saved_at": datetime.now().isoformat(),
                "providers": {},
            }
            for pk, s in self._statuses.items():
                d = {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
                d["health"] = s.health.value
                data["providers"][pk] = d
            with open(target, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("HealthStore exported to repo workspace: %s", target)
            return target
        except Exception as exc:  # 只读卷/权限不足 → 降级
            logger.warning("HealthStore repo export failed (degraded): %s", exc)
            return ""


# ═══════════════════════════════════════════════════════════════════════════
# 自动恢复调度器
# ═══════════════════════════════════════════════════════════════════════════


class RecoveryScheduler:
    """自动恢复调度器 — 对 DOWN 的提供商尝试按指数退避重新探测"""

    def __init__(self, health_store: HealthStore, probe_fn: Callable | None = None) -> None:
        self._store = health_store
        self._probe_fn = probe_fn

    async def tick(self) -> list[str]:
        """执行一轮恢复检查，返回成功恢复的提供商列表"""
        recovered: list[str] = []
        now = time.time()

        for pk, s in self._store.get_all_statuses().items():
            if s.health != ProviderHealth.DOWN:
                continue
            if s.recovery_attempts >= s.max_recovery_attempts:
                continue

            # 指数退避: 60s, 120s, 240s, 480s, ...
            backoff = s.recovery_backoff * (2 ** s.recovery_attempts)
            if now - s.last_recovery_attempt < backoff:
                continue

            logger.info("RecoveryScheduler: attempting recovery for %s (attempt %d/%d)",
                        pk, s.recovery_attempts + 1, s.max_recovery_attempts)

            self._store.mark_recovering(pk)
            self._store.save()

            if self._probe_fn:
                success, latency, error = await self._probe_fn(pk)
                if success:
                    self._store.reset_recovery(pk)
                    self._store.record_heartbeat(pk, True, latency)
                    recovered.append(pk)
                    logger.info("RecoveryScheduler: %s recovered after %d attempts", pk, s.recovery_attempts)
                else:
                    logger.warning("RecoveryScheduler: %s still down: %s", pk, error)

        self._store.save()
        return recovered


# ═══════════════════════════════════════════════════════════════════════════
# 质量治理编排器
# ═══════════════════════════════════════════════════════════════════════════


class QualityGovernor:
    """质量治理编排器 — 统一管理心跳、质量评估、自动恢复"""

    def __init__(
        self,
        provider_keys: list[str],
        chat_fn: Callable | None = None,
        probe_fn: Callable | None = None,
        store: HealthStore | None = None,
    ) -> None:
        self._provider_keys = provider_keys
        self._chat_fn = chat_fn
        self._store = store or HealthStore()
        self._assessor = QualityAssessor(chat_fn)
        self._prober = HeartbeatProber(probe_fn)
        self._recovery = RecoveryScheduler(self._store, probe_fn)

        # 计时器
        self._last_heartbeat_all: float = 0
        self._last_quality_assess: float = 0
        self._heartbeat_interval: float = 300.0   # 5 分钟
        self._quality_interval: float = 1800.0    # 30 分钟

    # ── 心跳轮 ──────────────────────────────────────────────────────────

    async def run_heartbeat_round(self) -> dict[str, tuple[bool, float]]:
        """对所有提供商执行一轮深度心跳探测"""
        results: dict[str, tuple[bool, float]] = {}
        for pk in self._provider_keys:
            success, latency, error = await self._prober.deep_probe(pk)
            self._store.record_heartbeat(pk, success, latency, error)
            results[pk] = (success, latency)
            logger.debug("Heartbeat %s: success=%s latency=%.0fms %s", pk, success, latency, error)
        self._store.save()
        return results

    # ── 质量评估轮 ──────────────────────────────────────────────────────

    async def run_quality_round(self) -> dict[str, dict[str, float]]:
        """对所有提供商执行一轮质量评估"""
        scores = await self._assessor.assess_all(self._provider_keys, self._chat_fn)
        for pk, cap_scores in scores.items():
            self._store.record_quality(pk, cap_scores)
            logger.info("Quality %s: overall=%.3f %s", pk,
                        sum(cap_scores.values()) / len(cap_scores) if cap_scores else 0,
                        cap_scores)
        self._store.save()
        return scores

    # ── 自动恢复轮 ──────────────────────────────────────────────────────

    async def run_recovery_round(self) -> list[str]:
        return await self._recovery.tick()

    # ── 完整一轮 ─────────────────────────────────────────────────────────

    async def tick(self) -> dict[str, Any]:
        """执行一轮完整的治理循环"""
        now = time.time()
        actions: dict[str, Any] = {}

        # 心跳 (高频)
        if now - self._last_heartbeat_all > self._heartbeat_interval:
            actions["heartbeat"] = await self.run_heartbeat_round()
            self._last_heartbeat_all = now

        # 质量评估 (低频)
        if now - self._last_quality_assess > self._quality_interval:
            actions["quality_assessment"] = await self.run_quality_round()
            self._last_quality_assess = now

        # 自动恢复
        recovered = await self.run_recovery_round()
        if recovered:
            actions["recovered"] = recovered

        return actions

    # ── 报告 ────────────────────────────────────────────────────────────

    def get_report(self) -> dict[str, Any]:
        """生成治理报告"""
        providers: dict[str, Any] = {}
        for pk in self._provider_keys:
            s = self._store.get(pk)
            providers[pk] = {
                "health": s.health.value,
                "overall_quality": round(s.overall_quality, 3),
                "business_fitness": {k: round(v, 3) for k, v in s.business_fitness.items()},
                "avg_latency_ms": round(s.avg_latency_ms, 1),
                "error_rate": round(s.error_rate, 4),
                "total_calls": s.total_calls,
                "total_errors": s.total_errors,
                "uptime_ratio": round(s.uptime_ratio, 4),
                "is_available": s.is_available,
                "consecutive_failures": s.consecutive_heartbeat_failures,
                "last_error": s.last_error[:80] if s.last_error else "",
            }

        # 按能力维度的路由推荐
        recommendations: dict[str, list[dict[str, Any]]] = {}
        for cap in ModelCapability:
            ranked = self._store.get_quality_ranking(cap.value)
            if ranked:
                ranked[0]
                recommendations[cap.value] = [
                    {"provider": pk, "score": round(sc, 3)} for pk, sc in ranked[:3]
                ]

        return {
            "timestamp": datetime.now().isoformat(),
            "providers": providers,
            "recommendations": recommendations,
            "store_path": self._store.store_path,
        }


# ── 便捷函数 ──────────────────────────────────────────────────────────────


def get_routing_weights(
    store: HealthStore,
    capability: ModelCapability | None = None,
    cost_map: dict[str, float] | None = None,
) -> dict[str, float]:
    """获取路由权重表，供 LLMRouter 使用"""
    weights: dict[str, float] = {}
    for pk in store.get_all_statuses():
        cost = (cost_map or {}).get(pk, 0.01)
        w = store.compute_weight(pk, capability, cost)
        if w > 0:
            weights[pk] = w
    return weights
