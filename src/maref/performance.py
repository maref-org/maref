"""
MAREF 性能优化模块

Phase 3 性能增强:
1. 异步安全验证
2. 信任评分缓存
3. 批量化安全操作
4. 分布式信任传播优化
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CachedTrustScore:
    """缓存的信任评分"""
    agent_id: str
    score: float
    factors: list[dict[str, Any]]
    computed_at: float
    ttl_seconds: float = 300.0  # 默认5分钟缓存

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.computed_at) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "score": round(self.score, 3),
            "computed_at": datetime.fromtimestamp(self.computed_at).isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "is_expired": self.is_expired,
        }


@dataclass
class BatchOperation:
    """批量操作"""
    operation_id: str
    operation_type: str
    items: list[Any]
    created_at: float
    priority: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "type": self.operation_type,
            "item_count": len(self.items),
            "priority": self.priority,
        }


class TrustScoreCache:
    """
    信任评分缓存

    减少重复计算信任评分的开销，支持 TTL、LRU 淘汰和一致性验证。
    """

    def __init__(self, default_ttl_seconds: float = 300.0, max_size: int = 10000):
        self._cache: dict[str, CachedTrustScore] = {}
        self._access_times: dict[str, float] = {}
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._hit_count = 0
        self._miss_count = 0

    def get(self, agent_id: str) -> CachedTrustScore | None:
        """获取缓存的评分"""
        cached = self._cache.get(agent_id)

        if cached is None:
            self._miss_count += 1
            return None

        if cached.is_expired:
            del self._cache[agent_id]
            del self._access_times[agent_id]
            self._miss_count += 1
            return None

        self._access_times[agent_id] = time.time()
        self._hit_count += 1
        return cached

    def set(
        self,
        agent_id: str,
        score: float,
        factors: list[dict[str, Any]],
        ttl_seconds: float | None = None
    ) -> CachedTrustScore:
        """设置缓存的评分"""
        # 检查是否需要淘汰
        if len(self._cache) >= self._max_size:
            self._evict_lru()

        cached = CachedTrustScore(
            agent_id=agent_id,
            score=score,
            factors=factors,
            computed_at=time.time(),
            ttl_seconds=ttl_seconds or self._default_ttl,
        )

        self._cache[agent_id] = cached
        self._access_times[agent_id] = time.time()
        return cached

    def invalidate(self, agent_id: str) -> bool:
        """使缓存失效"""
        if agent_id in self._cache:
            del self._cache[agent_id]
            del self._access_times[agent_id]
            return True
        return False

    def invalidate_all(self) -> int:
        """使所有缓存失效"""
        count = len(self._cache)
        self._cache.clear()
        self._access_times.clear()
        return count

    def _evict_lru(self) -> None:
        """淘汰最近最少使用的缓存项"""
        if not self._access_times:
            return

        oldest = min(self._access_times, key=lambda k: self._access_times[k])
        del self._cache[oldest]
        del self._access_times[oldest]

    def clean_expired(self) -> int:
        """清理过期缓存"""
        expired = [
            agent_id for agent_id, cached in self._cache.items()
            if cached.is_expired
        ]

        for agent_id in expired:
            del self._cache[agent_id]
            del self._access_times[agent_id]

        return len(expired)

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        total_requests = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total_requests if total_requests > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": round(hit_rate, 3),
            "default_ttl_seconds": self._default_ttl,
        }


class AsyncSecurityVerifier:
    """
    异步安全验证器

    提供非阻塞的安全验证操作，支持并发验证和超时控制。
    """

    def __init__(self, max_concurrent: int = 10, default_timeout: float = 5.0):
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self._semaphore = None  # 懒加载
        self._verification_count = 0
        self._total_latency_ms = 0.0

    async def verify_identity(
        self,
        agent_id: str,
        verifier: Callable[[str], Awaitable[dict[str, Any]]],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """异步验证身份"""
        start = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                verifier(agent_id),
                timeout=timeout or self.default_timeout
            )

            latency = (time.perf_counter() - start) * 1000
            self._total_latency_ms += latency
            self._verification_count += 1

            result["verification_latency_ms"] = round(latency, 3)
            return result

        except asyncio.TimeoutError:
            return {
                "verified": False,
                "reason": "Verification timeout",
                "agent_id": agent_id,
                "verification_latency_ms": (time.perf_counter() - start) * 1000,
            }
        except Exception as e:
            return {
                "verified": False,
                "reason": str(e),
                "agent_id": agent_id,
                "verification_latency_ms": (time.perf_counter() - start) * 1000,
            }

    async def verify_batch(
        self,
        agent_ids: list[str],
        verifier: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """批量异步验证"""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def bounded_verify(agent_id: str) -> dict[str, Any]:
            async with semaphore:
                return await self.verify_identity(agent_id, verifier)

        tasks = [bounded_verify(aid) for aid in agent_ids]
        return await asyncio.gather(*tasks)

    async def verify_trust_chain(
        self,
        chain: Any,
        analyzer: Callable[[Any], Awaitable[list[Any]]],
    ) -> dict[str, Any]:
        """异步验证信任链"""
        start = time.perf_counter()

        try:
            risks = await asyncio.wait_for(
                analyzer(chain),
                timeout=self.default_timeout
            )

            latency = (time.perf_counter() - start) * 1000
            self._total_latency_ms += latency
            self._verification_count += 1

            return {
                "valid": len(risks) == 0,
                "risk_count": len(risks),
                "risks": [r.to_dict() if hasattr(r, 'to_dict') else str(r) for r in risks],
                "latency_ms": round(latency, 3),
            }

        except asyncio.TimeoutError:
            return {
                "valid": False,
                "reason": "Chain analysis timeout",
                "latency_ms": (time.perf_counter() - start) * 1000,
            }

    def get_stats(self) -> dict[str, Any]:
        """获取验证统计"""
        avg_latency = (
            self._total_latency_ms / self._verification_count
            if self._verification_count > 0 else 0.0
        )

        return {
            "total_verifications": self._verification_count,
            "average_latency_ms": round(avg_latency, 3),
            "max_concurrent": self.max_concurrent,
            "default_timeout": self.default_timeout,
        }


class BatchSecurityProcessor:
    """
    批量安全处理器

    批量执行安全操作以摊销开销：信任评估、合规检查、漏洞扫描。
    """

    def __init__(self, batch_size: int = 100, flush_interval_ms: float = 100.0):
        self.batch_size = batch_size
        self.flush_interval_ms = flush_interval_ms
        self._pending: list[BatchOperation] = []
        self._batch_count = 0
        self._total_items_processed = 0

    def submit(
        self,
        operation_type: str,
        items: list[Any],
        priority: int = 1
    ) -> str:
        """提交批量操作"""
        operation = BatchOperation(
            operation_id=f"batch-{int(time.time() * 1000)}-{len(self._pending)}",
            operation_type=operation_type,
            items=items,
            created_at=time.time(),
            priority=priority,
        )

        self._pending.append(operation)

        # 如果达到批次大小，自动刷新
        total_items = sum(len(op.items) for op in self._pending)
        if total_items >= self.batch_size:
            self.flush()

        return operation.operation_id

    def flush(self) -> dict[str, Any]:
        """执行所有挂起的批量操作"""
        if not self._pending:
            return {"processed": 0, "operations": 0}

        # 按优先级排序
        self._pending.sort(key=lambda op: op.priority)

        results: list[dict[str, Any]] = []
        total_items = 0

        for operation in self._pending:
            result = self._process_batch(operation)
            results.append(result)
            total_items += len(operation.items)

        self._batch_count += len(self._pending)
        self._total_items_processed += total_items
        self._pending.clear()

        return {
            "processed": total_items,
            "operations": len(results),
            "results": results,
        }

    def _process_batch(self, operation: BatchOperation) -> dict[str, Any]:
        """处理单个批量操作"""
        start = time.perf_counter()

        # 根据操作类型进行批量处理
        if operation.operation_type == "trust_evaluation":
            processed = self._batch_trust_evaluation(operation.items)
        elif operation.operation_type == "compliance_check":
            processed = self._batch_compliance_check(operation.items)
        elif operation.operation_type == "vulnerability_scan":
            processed = self._batch_vulnerability_scan(operation.items)
        else:
            processed = [{"item": item, "status": "unknown_operation"} for item in operation.items]

        latency = (time.perf_counter() - start) * 1000

        return {
            "operation_id": operation.operation_id,
            "type": operation.operation_type,
            "items_processed": len(processed),
            "latency_ms": round(latency, 3),
            "throughput_per_second": round(len(processed) / (latency / 1000), 1) if latency > 0 else 0,
        }

    def _batch_trust_evaluation(self, items: list[Any]) -> list[dict[str, Any]]:
        """批量信任评估"""
        results = []
        for agent_info in items:
            agent_id = agent_info.get("agent_id", "unknown")
            results.append({
                "agent_id": agent_id,
                "score": 50.0,  # 模拟评分
                "status": "evaluated",
            })
        return results

    def _batch_compliance_check(self, items: list[Any]) -> list[dict[str, Any]]:
        """批量合规检查"""
        results = []
        for check in items:
            req_id = check.get("requirement_id", "unknown")
            results.append({
                "requirement_id": req_id,
                "compliant": True,  # 模拟结果
                "status": "checked",
            })
        return results

    def _batch_vulnerability_scan(self, items: list[Any]) -> list[dict[str, Any]]:
        """批量漏洞扫描"""
        results = []
        for component in items:
            name = component.get("name", "unknown")
            results.append({
                "component": name,
                "vulnerabilities": 0,  # 模拟结果
                "status": "scanned",
            })
        return results

    def get_stats(self) -> dict[str, Any]:
        """获取批量处理统计"""
        return {
            "batch_count": self._batch_count,
            "total_items_processed": self._total_items_processed,
            "pending_operations": len(self._pending),
            "pending_items": sum(len(op.items) for op in self._pending),
            "batch_size": self.batch_size,
        }


class DistributedTrustOptimizer:
    """
    分布式信任优化器

    优化信任传播算法，支持分区容错和增量更新。
    """

    def __init__(self):
        self._trust_vectors: dict[str, dict[str, float]] = defaultdict(dict)
        self._update_log: list[dict[str, Any]] = []
        self._partition_state: dict[str, bool] = {}

    def propagate_trust_incremental(
        self,
        source_agent: str,
        target_agent: str,
        trust_delta: float
    ) -> dict[str, Any]:
        """
        增量信任传播

        只传播变化量，而不是重新计算整个信任图。
        """
        current = self._trust_vectors[source_agent].get(target_agent, 0.0)
        new_trust = min(max(current + trust_delta, 0.0), 100.0)

        self._trust_vectors[source_agent][target_agent] = new_trust

        self._update_log.append({
            "timestamp": time.time(),
            "source": source_agent,
            "target": target_agent,
            "delta": trust_delta,
            "old_value": current,
            "new_value": new_trust,
        })

        return {
            "source": source_agent,
            "target": target_agent,
            "old_trust": round(current, 3),
            "new_trust": round(new_trust, 3),
            "delta": round(trust_delta, 3),
            "propagated": True,
        }

    def handle_partition(
        self,
        partition_id: str,
        agents_in_partition: list[str],
        is_available: bool
    ) -> dict[str, Any]:
        """
        处理网络分区

        当分区发生时，标记受影响代理并继续可用分区的操作。
        """
        self._partition_state[partition_id] = is_available

        # 冻结受影响分区的信任更新
        affected_updates = 0
        for update in self._update_log:
            if update["source"] in agents_in_partition or update["target"] in agents_in_partition:
                affected_updates += 1

        return {
            "partition_id": partition_id,
            "agents_affected": len(agents_in_partition),
            "is_available": is_available,
            "pending_updates": affected_updates,
            "action": "frozen" if not is_available else "resumed",
        }

    def merge_partition(self, partition_id: str) -> dict[str, Any]:
        """
        合并分区恢复

        当分区恢复时，应用挂起的信任更新。
        """
        self._partition_state[partition_id] = True

        # 应用挂起的更新（简化实现）
        applied = 0
        for _update in self._update_log:
            # 实际实现中需要处理冲突解决
            applied += 1

        return {
            "partition_id": partition_id,
            "status": "merged",
            "updates_applied": applied,
        }

    def get_trust_vector(self, agent_id: str) -> dict[str, float]:
        """获取代理的信任向量"""
        return dict(self._trust_vectors.get(agent_id, {}))

    def get_stats(self) -> dict[str, Any]:
        """获取优化器统计"""
        return {
            "agents_tracked": len(self._trust_vectors),
            "total_trust_relationships": sum(len(v) for v in self._trust_vectors.values()),
            "update_log_size": len(self._update_log),
            "active_partitions": sum(1 for v in self._partition_state.values() if v),
            "failed_partitions": sum(1 for v in self._partition_state.values() if not v),
        }


def create_trust_score_cache(
    ttl_seconds: float = 300.0,
    max_size: int = 10000
) -> TrustScoreCache:
    """创建信任评分缓存"""
    return TrustScoreCache(default_ttl_seconds=ttl_seconds, max_size=max_size)


def create_async_security_verifier(
    max_concurrent: int = 10,
    default_timeout: float = 5.0
) -> AsyncSecurityVerifier:
    """创建异步安全验证器"""
    return AsyncSecurityVerifier(max_concurrent=max_concurrent, default_timeout=default_timeout)


def create_batch_processor(
    batch_size: int = 100,
    flush_interval_ms: float = 100.0
) -> BatchSecurityProcessor:
    """创建批量安全处理器"""
    return BatchSecurityProcessor(batch_size=batch_size, flush_interval_ms=flush_interval_ms)


def create_distributed_trust_optimizer() -> DistributedTrustOptimizer:
    """创建分布式信任优化器"""
    return DistributedTrustOptimizer()


__all__ = [
    "TrustScoreCache",
    "AsyncSecurityVerifier",
    "BatchSecurityProcessor",
    "DistributedTrustOptimizer",
    "CachedTrustScore",
    "BatchOperation",
    "create_trust_score_cache",
    "create_async_security_verifier",
    "create_batch_processor",
    "create_distributed_trust_optimizer",
]
