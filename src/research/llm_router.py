"""LLM Router — multi-provider LLM router with capability-aware routing, caching, and stats.

Key features:
  - Capability-based routing: route by model capability (coding, reasoning, vision, …)
  - Provider failover with concurrent health probing
  - Cost-aware routing (prefer cheaper providers when quality is sufficient)
  - Quality-aware routing (integrate HealthStore for quality-weighted selection)
  - Local response cache (LLMLocalCache) for exact-match dedup
  - Per-provider usage statistics and cost estimation
  - Retry/fallback on provider failure
  - Model Registry integration: all models defined in model_registry.py

Usage:
    from research.llm_router import LLMRouter, ProviderConfig

    router = LLMRouter()
    response = await router.chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
    )
    print(response["content"])
    stats = router.get_stats()
    await router.close()

Quality-aware routing (optional):
    from research.llm_quality import HealthStore

    store = HealthStore()
    router = LLMRouter(health_store=store)
    # HealthStore weights will augment priority+cost sorting
    # Call router.record_quality_usage(pname, success, tokens) after each call
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from research.llm_cache import LLMLocalCache
from research.llm_quality import HealthStore
from research.model_registry import ModelCapability, ModelInfo, registry

logger = logging.getLogger("llm_router")


class TaskTier(Enum):
    """任务分层 — 决定模型选型策略。

    THINK: 领导/规划, quality 优先 (复杂推理/创意)
    WORK:  员工/执行, cost 优先 (默认, 常规任务)
    AUDIT: 质检, 独立视角验证 (排除生成方)
    """

    THINK = "think"
    WORK = "work"
    AUDIT = "audit"


VERIFY_PROMPT_TEMPLATE = (
    "你是质检员。请检查下面这个回答是否事实正确、完整、逻辑自洽。\n"
    "任务: {task}\n"
    "回答: {answer}\n"
    "逐项核查后只输出严格 JSON, 不要额外文字:\n"
    '{{"passed": true或false, "score": 0到10整数, '
    '"issues": ["具体问题清单"], "suggestion": "一句话改进建议"}}'
)


def _pairwise_agreement(contents: list[str]) -> float:
    """GAP-2: 多模型输出一致性 — 两两平均归一化 Jaccard 相似度。

    中文按单字切分(标点忽略), 英文按 token 切分; 空候选返回 0。
    用于 ensemble_generate 判断候选间是否达成共识。
    """
    if not contents:
        return 0.0

    def _tokens(text: str) -> set[str]:
        import re
        text = text.lower()
        cjk = re.findall(r"[\u4e00-\u9fff]", text)
        words = re.findall(r"[a-z0-9_]+", text)
        return set(cjk) | set(words)

    tokensets = [_tokens(c) for c in contents]
    if not any(t for t in tokensets):
        return 0.0

    total, pairs = 0.0, 0
    for i in range(len(tokensets)):
        for j in range(i + 1, len(tokensets)):
            a, b = tokensets[i], tokensets[j]
            if not a and not b:
                sim = 1.0
            elif not a or not b:
                sim = 0.0
            else:
                inter = len(a & b)
                union = len(a | b)
                sim = inter / union if union else 1.0
            total += sim
            pairs += 1
    return total / pairs if pairs else 0.0


# ── Default provider configurations ──────────────────────────────────────

DEFAULT_ENV_KEY_MAP: dict[str, list[str]] = {
    "deepseek": ["DEEPSEEK_API_KEY"],
    "siliconflow": ["SILICONFLOW_API_KEY", "SILICONFLOW_CN_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY", "NVCF_API_KEY"],
    "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
    "glm": ["GLM_API_KEY", "ZHIPU_API_KEY"],
    "volcengine": ["VOLCANO_API_KEY", "ARK_API_KEY", "VOLCENGINE_API_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
}


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider.

    Args:
        name: Human-readable label.
        provider_type: Provider key (deepseek, siliconflow, openai, …).
        api_key: API key literal.  If None, resolved from env via DEFAULT_ENV_KEY_MAP.
        base_url: API base URL (must support OpenAI-compatible /chat/completions).
        model: Default model name for this provider.
        priority: Lower number = higher priority (selected first when healthy).
        cost_per_1k_tokens: Approximate cost in CNY per 1K tokens (used for cost-aware routing).
        max_rpm: Maximum requests per minute (rate limit safeguard).
        force_temperature: If set, always use this temperature value (some models only accept 1).
    """

    name: str = ""
    provider_type: str = ""
    api_key: str | None = None
    base_url: str = ""
    model: str = ""
    priority: int = 10
    cost_per_1k_tokens: float = 0.0
    max_rpm: int = 60
    force_temperature: float | None = None


# ── Build provider configs from registry ─────────────────────────────────


def _build_from_registry() -> dict[str, ProviderConfig]:
    """Dynamically build provider configs from the ModelRegistry."""
    configs: dict[str, ProviderConfig] = {}
    for p in registry.list_providers():
        if not p.models:
            continue
        # Use the highest-priority model as default
        sorted_models = sorted(p.models, key=lambda m: m.priority)
        default = sorted_models[0]

        # Some providers only accept temperature=1 (e.g. Kimi)
        force_temp: float | None = None
        if p.key == "kimi":
            force_temp = 1.0

        configs[p.key] = ProviderConfig(
            name=p.name,
            provider_type=p.key,
            api_key=os.environ.get(p.api_key_env),
            base_url=p.base_url,
            model=default.api_model_name,
            priority=default.priority,
            cost_per_1k_tokens=default.cost_per_1k_mixed,
            max_rpm=60,
            force_temperature=force_temp,
        )
    return configs


# ── Built-in providers (static fallback) ─────────────────────────────────

BUILTIN_PROVIDERS: dict[str, ProviderConfig] = _build_from_registry()

# ── Response types ───────────────────────────────────────────────────────


@dataclass
class ProviderStats:
    calls_today: int = 0
    tokens_today: int = 0
    cached_calls_today: int = 0
    uncached_calls_today: int = 0
    errors_today: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        total_calls = self.calls_today + self.errors_today
        return self.total_latency_ms / total_calls if total_calls > 0 else 0.0


# ── Router ───────────────────────────────────────────────────────────────


class LLMRouter:
    """Multi-provider LLM router with caching, cost awareness, and failover.

    Provider selection flow:
      1. Concurrent health probe of all providers (1s timeout)
      2. Filter to healthy providers
      3. Rank their models by TaskTier: WORK/AUDIT by cost ascending
         (cheapest first), THINK by priority (quality first)
      4. Try each model in order until one succeeds
      5. Cache successful responses for exact-match dedup

    TaskTier.WORK is the default: routine requests automatically prefer the
    cheapest capable model (e.g. glm-4.7 free). Use TaskTier.THINK for
    complex reasoning/creative work, and generate_and_verify() for an
    AUDIT-tier cross-check loop.
    """

    def __init__(
        self,
        providers: dict[str, ProviderConfig] | None = None,
        cache: LLMLocalCache | None = None,
        health_store: HealthStore | None = None,
        quality_aware: bool = True,
    ) -> None:
        """Initialize the LLM router.

        Args:
            providers: Provider configs. If None, uses BUILTIN_PROVIDERS from registry.
            cache: Response cache instance.
            health_store: Optional HealthStore for quality-aware routing.
                         If provided, weights from HealthStore.compute_weight()
                         augment the priority+cost sorting in provider selection.
            quality_aware: If True (default) and health_store is set, use
                          quality-weighted sorting. Set False to use simple
                          priority+cost sort.
        """
        self._providers = dict(providers or BUILTIN_PROVIDERS)
        self._cache = cache or LLMLocalCache(max_size=10000)
        self._client: httpx.AsyncClient | None = None
        # GAP-1 补强: 默认挂载 HealthStore, 使质量闭环默认生效。
        # 空库/冷启动时 compute_weight 返回中性 cost 权重, 不破坏现有排序。
        if health_store is None:
            health_store = HealthStore()
        self._health_store = health_store
        self._quality_aware = quality_aware and health_store is not None

        # Resolve API keys from environment if not set explicitly
        for pname, pcfg in self._providers.items():
            if not pcfg.api_key:
                env_names = DEFAULT_ENV_KEY_MAP.get(pcfg.provider_type, [])
                for env_name in env_names:
                    val = os.environ.get(env_name)
                    if val:
                        pcfg.api_key = val
                        break
            if not pcfg.name:
                pcfg.name = pname

        # Per-provider stats
        self._stats: dict[str, ProviderStats] = {
            pname: ProviderStats() for pname in self._providers
        }

        # Rate-limit tracking
        self._rpm_counters: dict[str, list[float]] = {
            pname: [] for pname in self._providers
        }

        # Health probe cache (TTL 30s, avoid probing on every request)
        self._probe_cache: list[str] | None = None
        self._probe_cache_time: float = 0.0
        self._probe_cache_ttl: float = 30.0

    @property
    def available(self) -> bool:
        """True if at least one provider has an API key configured."""
        return any(p.api_key for p in self._providers.values())

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        capability: ModelCapability | str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tier: TaskTier | str | None = None,
        model: str | None = None,
        exclude_provider: str | None = None,
    ) -> dict[str, Any] | None:
        """Send a chat completion request with automatic model selection.

        Args:
            messages: Chat messages (OpenAI format).
            provider: Specific provider key to use (uses its default model).
                If None, auto-select across healthy providers.
            capability: If set, only models with this capability are considered.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            tier: Task tier (think/work/audit). Defaults to TaskTier.WORK:
                WORK/AUDIT sort by cost ascending (cheapest first); THINK sorts
                by priority (quality first).
            model: Specific model_id to force (e.g. "deepseek-v4-flash").
                Overrides tier/provider selection.
            exclude_provider: Skip models from this provider (used by
                generate_and_verify to force a different generator on retry).

        Returns:
            Dict with keys ``content``, ``provider``, ``model``, ``cached``,
            ``latency_ms``, ``usage``, ``model_info`` — or None if all models fail.
        """
        # 0. Resolve tier and capability
        tier_obj = TaskTier.WORK if tier is None else (
            TaskTier(tier) if isinstance(tier, str) else tier
        )
        cap_filter: ModelCapability | None = None
        if capability is not None:
            cap_filter = ModelCapability(capability) if isinstance(capability, str) else capability

        # 1. Resolve candidate models
        if model is not None:
            # Explicit model overrides everything
            m = registry.get_model(model)
            if m is None:
                logger.warning("LLMRouter: unknown model_id %s, falling back to tier routing", model)
            else:
                return await self._try_candidates(messages, [m], temperature, max_tokens)
        elif provider is not None:
            # Backward-compatible: explicit provider → its default (highest-priority) model
            pcfg = self._providers.get(provider)
            if pcfg is None or not pcfg.api_key:
                logger.warning("LLMRouter: provider %s not configured", provider)
                return None
            pmodels = registry.get_models_for_provider(provider)
            if not pmodels:
                logger.warning("LLMRouter: no models for provider %s", provider)
                return None
            default_model = min(pmodels, key=lambda mm: mm.priority)
            return await self._try_candidates(messages, [default_model], temperature, max_tokens)
        else:
            # Auto: probe healthy providers, then rank their models by tier
            healthy = await self._probe_healthy()
            if not healthy:
                logger.warning("LLMRouter: no healthy providers available")
                return None
            candidates = self._rank_models(
                healthy, tier_obj, cap_filter,
                exclude_provider=exclude_provider,
            )
            if not candidates:
                if cap_filter is not None:
                    # Graceful degradation: capability no match → try all healthy
                    logger.warning(
                        "LLMRouter: no models for capability %s, degrading to all healthy",
                        cap_filter.value,
                    )
                    candidates = self._rank_models(
                        healthy, tier_obj, exclude_provider=exclude_provider,
                    )
                if not candidates:
                    logger.error("LLMRouter: no candidate models after ranking")
                    return None
            return await self._try_candidates(messages, candidates, temperature, max_tokens)
        return None  # explicit None when model is unknown (no fallback to auto-select)

    async def _try_candidates(
        self,
        messages: list[dict[str, str]],
        candidates: list[ModelInfo],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any] | None:
        """Try candidate models in order: cache → call → cache. Return first success."""
        # Cache-first (check each candidate's cache in ranking order)
        for m in candidates:
            pcfg = self._providers.get(m.provider)
            if pcfg is None:
                continue
            cached = self._cache.get(messages, model=m.api_model_name, temperature=temperature, max_tokens=max_tokens)
            if cached is not None:
                self._stats[m.provider].cached_calls_today += 1
                self.record_quality_usage(m.provider, True, 0)
                return {
                    "content": cached,
                    "provider": m.provider,
                    "model": m.api_model_name,
                    "cached": True,
                    "latency_ms": 0.0,
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "model_info": self._model_info_dict(m),
                }

        # Call each until one succeeds
        last_error: str | None = None
        for m in candidates:
            pcfg = self._providers.get(m.provider)
            if pcfg is None or not pcfg.api_key:
                continue
            if not self._check_rpm(m.provider, pcfg.max_rpm):
                logger.debug("LLMRouter: %s rate limited, skipping", m.provider)
                continue
            result = await self._call_provider(m, messages, temperature, max_tokens)
            if result is not None:
                # Cache uncached response
                if not result.get("cached", False):
                    self._cache.set(
                        messages, result["content"],
                        model=m.api_model_name, temperature=temperature, max_tokens=max_tokens,
                    )
                return result
            last_error = f"all {len(candidates)} candidate models failed"

        logger.error("LLMRouter: %s", last_error or "no candidates")
        return None

    def find_models_by_capability(
        self,
        capability: ModelCapability,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Find models that have a given capability.

        Returns list of dicts with keys: model_id, provider, display_name,
        api_model_name, capabilities, cost_tier, priority.
        """
        models = registry.find_by_capability(capability, max_results=max_results)
        return [
            {
                "model_id": m.model_id,
                "provider": m.provider,
                "display_name": m.display_name,
                "api_model_name": m.api_model_name,
                "capabilities": [c.value for c in m.capabilities],
                "cost_tier": m.cost_tier.value,
                "priority": m.priority,
            }
            for m in models
        ]

    def list_all_models(self) -> list[dict[str, Any]]:
        """List all known models from the registry."""
        return [
            {
                "model_id": m.model_id,
                "provider": m.provider,
                "display_name": m.display_name,
                "api_model_name": m.api_model_name,
                "capabilities": [c.value for c in m.capabilities],
                "cost_tier": m.cost_tier.value,
                "priority": m.priority,
            }
            for m in registry.list_models()
        ]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return per-provider and aggregate statistics."""
        total_calls = 0
        total_cached = 0
        total_tokens = 0
        total_cost = 0.0

        provider_data: dict[str, dict[str, Any]] = {}
        for pname, st in self._stats.items():
            pcfg = self._providers[pname]
            est_cost = (st.tokens_today / 1000) * pcfg.cost_per_1k_tokens
            total_calls += st.calls_today
            total_cached += st.cached_calls_today
            total_tokens += st.tokens_today
            total_cost += est_cost
            provider_data[pname] = {
                "calls_today": st.calls_today,
                "tokens_today": st.tokens_today,
                "cached_calls_today": st.cached_calls_today,
                "uncached_calls_today": st.uncached_calls_today,
                "errors_today": st.errors_today,
                "avg_latency_ms": round(st.avg_latency_ms, 1),
                "estimated_cost_cny": round(est_cost, 4),
            }

        cache_stats = self._cache.get_stats()

        return {
            "providers": provider_data,
            "aggregate": {
                "total_calls_today": total_calls,
                "total_cached_today": total_cached,
                "total_tokens_today": total_tokens,
                "total_estimated_cost_cny": round(total_cost, 4),
                "cache_hit_rate": round(cache_stats.hit_rate, 4),
                "cache_size": cache_stats.size,
            },
        }

    def get_cached_cost(self) -> dict[str, Any]:
        """Return simplified cost estimation (matches documentation API)."""
        stats = self.get_stats()
        daily = stats["aggregate"]["total_estimated_cost_cny"]
        return {
            "total_daily_cost": round(daily, 2),
            "total_monthly_cost": round(daily * 30, 2),
            "providers": {
                pname: {
                    "daily_cost": round(pd["estimated_cost_cny"], 4),
                    "monthly_cost": round(pd["estimated_cost_cny"] * 30, 4),
                }
                for pname, pd in stats["providers"].items()
            },
        }

    def save_cache(self) -> None:
        """Persist cache to disk."""
        self._cache.save()

    # ── Quality Integration ──────────────────────────────────────────────

    def record_quality_usage(self, provider_key: str, success: bool, tokens: int = 0) -> None:
        """Record a call in HealthStore for quality tracking.

        Call this after each chat_completion() to feed real usage data
        into the quality governance system.

        Args:
            provider_key: Provider name (e.g. "deepseek", "kimi").
            success: Whether the call succeeded.
            tokens: Total tokens consumed (for cost tracking).
        """
        if self._health_store is not None:
            self._health_store.record_call(provider_key, success, tokens)

    def get_quality_weights(self, capability: ModelCapability | str | None = None) -> dict[str, float]:
        """Get quality-weighted routing scores for all providers.

        Useful for inspection/debugging routing decisions.
        Returns dict of {provider_key: weight}.
        """
        if self._health_store is None:
            return {}
        weights: dict[str, float] = {}
        for pname, pcfg in self._providers.items():
            w = self._health_store.compute_weight(pname, capability, pcfg.cost_per_1k_tokens)
            if w > 0:
                weights[pname] = round(w, 6)
        return dict(sorted(weights.items(), key=lambda x: -x[1]))

    def get_quality_report(self) -> dict[str, Any] | None:
        """Get full quality governance report from HealthStore."""
        if self._health_store is None:
            return None
        from research.llm_quality import QualityGovernor
        gov = QualityGovernor(
            provider_keys=list(self._providers.keys()),
            store=self._health_store,
        )
        return gov.get_report()

    # ── Internal ─────────────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        return self._client

    async def _probe_healthy(self) -> list[str]:
        """Concurrently probe all providers; return list of healthy keys.

        Results are cached for ``_probe_cache_ttl`` seconds (default 30s)
        to avoid probing on every request.

        Sorting strategy:
          - If HealthStore is configured and quality_aware=True, sort by
            quality-weighted score (descending), so higher-quality providers
            are tried first.
          - Otherwise, sort by priority (asc) then cost (asc).
        """
        # Return cached results if still fresh
        now = time.time()
        if self._probe_cache is not None and now - self._probe_cache_time < self._probe_cache_ttl:
            return self._probe_cache

        results: dict[str, bool] = {}

        async def probe(pname: str) -> None:
            pcfg = self._providers[pname]
            if not pcfg.api_key:
                results[pname] = False
                return
            try:
                client = await self._get_client()
                resp = await client.post(
                    f"{pcfg.base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {pcfg.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": pcfg.model,
                        "messages": [{"role": "user", "content": "ok"}],
                        "max_tokens": 5,
                    },
                    timeout=httpx.Timeout(5.0),
                )
                results[pname] = resp.status_code == 200
            except Exception:
                results[pname] = False

        await asyncio.gather(*(probe(p) for p in self._providers))

        healthy = [p for p, ok in results.items() if ok]
        if not healthy:
            return healthy

        # Quality-aware sorting
        if self._quality_aware and self._health_store is not None:
            health_store = self._health_store
            def _weight(p: str) -> float:
                cfg = self._providers[p]
                w = health_store.compute_weight(p, cost_per_1k=cfg.cost_per_1k_tokens)
                if w <= 0:
                    return -999.0
                # GAP-1: 冷启动中性权重仅含 cost 因子, 无 priority 信息。
                # 融合 priority 因子保证无质量数据时仍近似 priority asc, cost asc 原语义。
                return w * (10.0 / (cfg.priority + 1))
            healthy.sort(key=_weight, reverse=True)
        else:
            # Default: priority asc, then cost asc
            healthy.sort(key=lambda p: (self._providers[p].priority, self._providers[p].cost_per_1k_tokens))

        # Update cache
        self._probe_cache = healthy
        self._probe_cache_time = time.time()
        return healthy

    def _rank_models(
        self,
        healthy_providers: list[str],
        tier: TaskTier,
        capability: ModelCapability | None = None,
        exclude_provider: str | None = None,
    ) -> list[ModelInfo]:
        """按任务分层对健康 provider 的模型排序, 返回有序候选队列。

        排序策略:
          - WORK/AUDIT: cost 升序 (便宜优先), priority 做 tiebreaker
          - THINK:      priority 升序 (质量优先), cost 做 tiebreaker

        capability 过滤先于排序; exclude_provider 用于审计交叉验证。
        """
        models: list[ModelInfo] = []
        for m in registry.list_models():
            if m.provider not in healthy_providers:
                continue
            if exclude_provider and m.provider == exclude_provider:
                continue
            if capability is not None and capability not in m.capabilities:
                continue
            models.append(m)

        if tier is TaskTier.THINK:
            models.sort(key=lambda m: (m.priority, m.cost_per_1k_mixed))
        else:
            models.sort(key=lambda m: (m.cost_per_1k_mixed, m.priority))
        return models

    @staticmethod
    def _model_info_dict(model: ModelInfo) -> dict[str, Any]:
        """ModelInfo → 响应中的 model_info 字典。"""
        return {
            "model_id": model.model_id,
            "display_name": model.display_name,
            "capabilities": [c.value for c in model.capabilities],
            "cost_tier": model.cost_tier.value,
            "version": model.version,
        }

    async def _call_provider(
        self,
        model: ModelInfo,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any] | None:
        """Call a single model; return response dict or None on failure."""
        pname = model.provider
        pcfg = self._providers.get(pname)
        if pcfg is None:
            logger.warning("LLMRouter: provider %s not in config", pname)
            return None
        t0 = time.perf_counter()
        try:
            client = await self._get_client()
            # Use force_temperature if set (some models only accept 1)
            actual_temp = pcfg.force_temperature if pcfg.force_temperature is not None else temperature
            payload: dict[str, Any] = {
                "model": model.api_model_name,
                "messages": messages,
                "temperature": actual_temp,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens

            resp = await client.post(
                f"{pcfg.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {pcfg.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content", "")
            usage = data.get("usage", {})

            # Update stats
            self._stats[pname].calls_today += 1
            self._stats[pname].uncached_calls_today += 1
            self._stats[pname].tokens_today += usage.get("total_tokens", 0)
            self._stats[pname].total_latency_ms += elapsed
            self._track_rpm(pname)

            # Auto-record quality usage
            self.record_quality_usage(pname, True, usage.get("total_tokens", 0))

            return {
                "content": content,
                "provider": pname,
                "model": model.api_model_name,
                "cached": False,
                "latency_ms": round(elapsed, 1),
                "usage": usage,
                "model_info": self._model_info_dict(model),
            }
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._stats[pname].errors_today += 1
            self._stats[pname].total_latency_ms += elapsed
            # Auto-record quality usage
            self.record_quality_usage(pname, False)
            logger.warning("LLMRouter: %s call failed (%.0fms): %s", pname, elapsed, exc)
            return None

    @staticmethod
    def _parse_verdict(content: str) -> bool:
        """从质检模型输出解析 passed 判定。优先 JSON, 降级关键词。"""
        if not content:
            return False
        try:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(content[start:end + 1])
                return bool(data.get("passed", False))
        except Exception:
            pass
        lower = content.lower()
        if "不通过" in lower or "未通过" in lower:
            return False
        return "通过" in lower or '"passed": true' in lower or "passed: true" in lower

    @staticmethod
    def _extract_issues(content: str) -> list[str]:
        """从质检模型输出提取 issues 列表。"""
        try:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(content[start:end + 1])
                issues = data.get("issues", [])
                return issues if isinstance(issues, list) else []
        except Exception:
            pass
        return []

    async def generate_and_verify(
        self,
        messages: list[dict[str, str]],
        tier: TaskTier | str | None = None,
        capability: ModelCapability | str | None = None,
        max_attempts: int = 2,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any] | None:
        """生成+质检回环: 生成 → AUDIT 模型(不同 provider)核查 → 未过重试。

        每次重试排除上一次生成方 provider, 强制换候选。
        质检模型自身失败时降级为"通过"直接返回生成结果。

        Returns:
            Dict with keys of chat_completion plus ``passed``, ``verifier``,
            ``verifier_issues``, ``attempts`` — or None if generation all fails.
        """
        tier_obj = TaskTier.WORK if tier is None else (
            TaskTier(tier) if isinstance(tier, str) else tier
        )
        cap_filter: ModelCapability | None = None
        if capability is not None:
            cap_filter = ModelCapability(capability) if isinstance(capability, str) else capability

        attempts = 0
        last_result: dict[str, Any] | None = None
        while attempts < max_attempts:
            attempts += 1
            gen = await self.chat_completion(
                messages, capability=capability, tier=tier_obj,
                temperature=temperature, max_tokens=max_tokens,
                exclude_provider=last_result["provider"] if last_result else None,
            )
            if gen is None:
                logger.error("generate_and_verify: generation failed on attempt %d", attempts)
                return last_result
            last_result = gen

            # 选质检模型: AUDIT tier, cost 最低且 provider ≠ 生成方
            healthy = await self._probe_healthy()
            verifier_models = self._rank_models(
                healthy, TaskTier.AUDIT, cap_filter,
                exclude_provider=gen["provider"],
            ) if healthy else []
            if not verifier_models:
                logger.info("generate_and_verify: no auditor available, returning unverified")
                gen["passed"] = True
                gen["verifier"] = None
                gen["verifier_issues"] = []
                gen["attempts"] = attempts
                return gen

            task_text = messages[-1]["content"] if messages else ""
            v_msgs = [{"role": "user", "content": VERIFY_PROMPT_TEMPLATE.format(
                task=task_text, answer=gen["content"],
            )}]
            v = await self._call_provider(verifier_models[0], v_msgs, temperature=0.0, max_tokens=512)
            if v is None:
                # 质检失败 → 降级通过, 返回生成结果
                gen["passed"] = True
                gen["verifier"] = None
                gen["verifier_issues"] = []
                gen["attempts"] = attempts
                return gen

            passed = self._parse_verdict(v["content"])
            gen["passed"] = passed
            gen["verifier"] = v["provider"]
            gen["verifier_issues"] = self._extract_issues(v["content"])
            gen["attempts"] = attempts
            if passed:
                logger.info("generate_and_verify: attempt %d passed audit by %s", attempts, v["provider"])
                return gen
            logger.info("generate_and_verify: attempt %d failed audit by %s, retrying", attempts, v["provider"])

        # 全部尝试未通过: 返回最后一次结果, passed=False 交给调用方决策
        if last_result is not None:
            last_result["passed"] = False
            return last_result
        return None

    async def ensemble_generate(
        self,
        messages: list[dict[str, str]],
        capability: ModelCapability | str | None = None,
        tier: TaskTier | str | None = None,
        n_models: int = 3,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        agreement_threshold: float = 0.5,
        exclude_provider: str | None = None,
    ) -> dict[str, Any] | None:
        """GAP-2 补强: 多模型并行生成 + 一致性裁决 (涌现/集体决策)。

        并行调用最多 n_models 个不同 provider 的模型独立生成同一任务,
        计算候选间文本相似度(一致性)。达成共识 → 返回主要结果;
        分歧大 → disputed=True 附全部候选, 交调用方仲裁。

        这是"多模型协同"而非"多模型冗余": 结果由共识裁决产生,
        而非第一个成功的模型。

        Args:
            messages: 任务消息。
            capability: 能力过滤(如 ModelCapability.CREATIVE)。
            tier: 分层, 默认 THINK (质量优先保证候选多样性)。
            n_models: 参与并行生成的最大模型数(跨 provider)。
            agreement_threshold: 两两平均 Jaccard 相似度阈值, 高于此值判定达成共识。
            exclude_provider: 排除的 provider (与 generate_and_verify 联动)。

        Returns:
            Dict with keys content/provider/model/candidates/n/agreement/disputed
            or None if no candidate succeeds.
        """
        tier_obj = TaskTier.THINK if tier is None else (
            TaskTier(tier) if isinstance(tier, str) else tier
        )
        cap_filter: ModelCapability | None = None
        if capability is not None:
            cap_filter = ModelCapability(capability) if isinstance(capability, str) else capability

        healthy = await self._probe_healthy()
        if not healthy:
            logger.warning("ensemble_generate: no healthy providers")
            return None
        candidates = self._rank_models(
            healthy, tier_obj, cap_filter, exclude_provider=exclude_provider,
        )
        if not candidates:
            logger.warning("ensemble_generate: no candidate models")
            return None

        # 取前 n_models 个不同 provider 的模型(保证 provider 多样性)
        seen_providers: set[str] = set()
        picked: list[ModelInfo] = []
        for m in candidates:
            if m.provider in seen_providers:
                continue
            seen_providers.add(m.provider)
            picked.append(m)
            if len(picked) >= n_models:
                break
        if len(picked) < 2:
            logger.info("ensemble_generate: 仅 %d 个 provider 可用, 退化为单模型", len(picked))

        # 并行调用
        results = await asyncio.gather(*[
            self._call_provider(m, messages, temperature, max_tokens)
            for m in picked
        ])
        ok: list[dict[str, Any]] = [r for r in results if r is not None]
        if not ok:
            logger.error("ensemble_generate: all %d models failed", len(picked))
            return None

        contents = [r["content"] for r in ok]
        agreement = _pairwise_agreement(contents)

        # 取排名最高的成功候选作为主要结果 (picked 已按 tier 排序)
        main = ok[0]
        disputed = agreement < agreement_threshold
        result: dict[str, Any] = {
            "content": main["content"],
            "provider": main["provider"],
            "model": main["model"],
            "candidates": [
                {"provider": r["provider"], "model": r["model"], "content": r["content"]}
                for r in ok
            ],
            "n": len(ok),
            "agreement": round(agreement, 4),
            "disputed": disputed,
            "latency_ms": round(max(r.get("latency_ms", 0) for r in ok), 1),
        }
        if disputed:
            logger.warning(
                "ensemble_generate: %d 模型分歧 (agreement=%.2f < %.2f), 需仲裁",
                len(ok), agreement, agreement_threshold,
            )
        else:
            logger.info(
                "ensemble_generate: %d 模型达成共识 (agreement=%.2f)", len(ok), agreement,
            )
        return result

    def _check_rpm(self, pname: str, max_rpm: int) -> bool:
        """Check if we're within rate limits for this provider."""
        now = time.time()
        window = 60.0
        self._rpm_counters[pname] = [t for t in self._rpm_counters[pname] if now - t < window]
        return len(self._rpm_counters[pname]) < max_rpm

    def _track_rpm(self, pname: str) -> None:
        self._rpm_counters[pname].append(time.time())
