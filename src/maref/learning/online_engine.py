from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OnlineWeightRecord:
    current_weight: float
    hit_count: int = 0
    sample_count: int = 0
    history: list[float] = field(default_factory=list)

    @property
    def alpha(self) -> float:
        return float(self.hit_count + 1)

    @property
    def beta(self) -> float:
        return float(self.sample_count - self.hit_count + 1)

    @property
    def confidence(self) -> float:
        n = self.sample_count
        if n < 2:
            return 0.0
        std = (self.alpha * self.beta) / ((self.alpha + self.beta) ** 2 * (self.alpha + self.beta + 1))
        return 1.0 / (1.0 + std ** 0.5)


@dataclass
class CategoryStats:
    """Categorical evidence statistics for a single (dim, feature, category) cell."""

    hits: int = 0
    count: int = 0

    @property
    def rate(self) -> float:
        return self.hits / self.count if self.count else 0.0

    def to_dict(self) -> dict[str, float]:
        return {"hits": self.hits, "count": self.count, "rate": round(self.rate, 4)}


# 领域先验：MAREF 六层治理架构 + 八卦信任状态机的建议初始权重。
# 调用方可将这些先验传入 OnlineLearningEngine(prior=...) 以注入领域知识。
# 设计原则：不硬编码运行时维度（维度由治理上下文动态决定），
# 而是提供「维度族 → 建议先验」的辅助映射，供上层按需组合。
DOMAIN_PRIOR_TEMPLATES: dict[str, dict[str, float]] = {
    # 地极 (Earth) 执行层 — 任务执行质量维度
    "execution": {
        "task_success": 0.7,
        "correctness": 0.7,
        "completeness": 0.6,
    },
    # 经卦 (Hexagram) 编排层 — 自演进与角色协作
    "orchestration": {
        "coordination": 0.6,
        "role_compliance": 0.65,
        "self_evolution": 0.55,
    },
    # 治理层 — 八卦信任状态机相关
    "governance": {
        "trust_adherence": 0.75,
        "safety_compliance": 0.85,
        "constitution_fidelity": 0.9,
    },
    # 基础设施 — 审计可观测性
    "infrastructure": {
        "audit_coverage": 0.6,
        "observability": 0.6,
    },
}


def build_domain_prior(*families: str) -> dict[str, float]:
    """构建领域先验字典。

    示例:
        build_domain_prior("execution", "governance")
        # -> {"task_success": 0.7, "correctness": 0.7, ..., "safety_compliance": 0.85, ...}
    """
    prior: dict[str, float] = {}
    for family in families:
        prior.update(DOMAIN_PRIOR_TEMPLATES.get(family, {}))
    return prior


class OnlineLearningEngine:
    """在线学习引擎 — 每次验证后立即贝叶斯更新，无需等待 MIN_SAMPLES。

    与 SimpleWeightRegistry 的区别：
    - OnlineLearningEngine: Beta-Binomial 在线更新，可插拔 hook + 分类证据模型
    - SimpleWeightRegistry: 无状态权重存储，无 hook 机制

    分类证据模型 (Categorical Evidence Model):
    - ingest_record(..., context=, failure_mode=, reward=) 记录结构化分类证据
    - 连续 reward 映射到 C0-C4 桶:  < -0.5 → C0; [-0.5, 0) → C1;
      [0, 0.3) → C2; [0.3, 0.6) → C3;  ≥ 0.6 → C4
    - 分类统计可通过 get_category_stats / get_all_category_stats 查询
    - 传入 db_path 时分类证据持久化到 SQLite

    使用方式:
        engine = OnlineLearningEngine()
        engine.ingest_online({"correctness": True, "testing": False})
        weight = engine.get_weight("correctness")
        engine.ingest_record("correctness", hit=True, context="test", reward=0.8)
        stats = engine.get_category_stats("correctness", "reward_bucket")
    """

    BAYESIAN_PRIOR: dict[str, float] = {}

    _CATEGORY_DB_TABLE = "category_evidence"
    _CATEGORY_DB_SCHEMA = """
        CREATE TABLE IF NOT EXISTS category_evidence (
            dim      TEXT NOT NULL,
            feature  TEXT NOT NULL,
            category TEXT NOT NULL,
            hits     INTEGER NOT NULL,
            count    INTEGER NOT NULL,
            PRIMARY KEY (dim, feature, category)
        )
    """

    _WEIGHT_DB_TABLE = "weight_records"
    _WEIGHT_DB_SCHEMA = """
        CREATE TABLE IF NOT EXISTS weight_records (
            dim            TEXT PRIMARY KEY,
            current_weight REAL NOT NULL,
            hit_count      INTEGER NOT NULL,
            sample_count   INTEGER NOT NULL,
            history        TEXT NOT NULL
        )
    """

    def __init__(self, prior: dict[str, float] | None = None, db_path: str | Path | None = None):
        self._weights: dict[str, OnlineWeightRecord] = {}
        self._prior = {**self.BAYESIAN_PRIOR, **(prior or {})}
        # Categorical evidence: dim -> feature -> category -> CategoryStats
        self._categories: dict[str, dict[str, dict[str, CategoryStats]]] = {}
        self._db_path: str | None = str(db_path) if db_path else None
        self._db: sqlite3.Connection | None = None
        if self._db_path:
            parent = Path(self._db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self._db_path)
            self._db.execute(self._CATEGORY_DB_SCHEMA)
            self._db.execute(self._WEIGHT_DB_SCHEMA)
            self._db.commit()
            self._load_categories()
            self._load_weights()

    # ------------------------------------------------------------------
    # 分类证据模型 (Categorical Evidence Model)
    # ------------------------------------------------------------------

    @staticmethod
    def _reward_to_bucket(reward: float) -> str:
        """连续奖励映射到离散桶 C0-C4。"""
        if reward < -0.5:
            return "C0"
        if reward < 0.0:
            return "C1"
        if reward < 0.3:
            return "C2"
        if reward < 0.6:
            return "C3"
        return "C4"

    def _update_category(self, dim: str, features: dict[str, str], hit: bool) -> None:
        """按 (dim, feature, category) 存储分类证据。"""
        dim_cats = self._categories.setdefault(dim, {})
        for feature, category in features.items():
            cell = (
                dim_cats.setdefault(feature, {})
                .setdefault(category, CategoryStats())
            )
            cell.count += 1
            if hit:
                cell.hits += 1
            if self._db is not None:
                self._persist_category(dim, feature, category, cell)

    def _persist_category(self, dim: str, feature: str, category: str, cell: CategoryStats) -> None:
        if self._db is None:
            return
        # 不在此处 commit：由 ingest_record / ingest_online 统一提交，
        # 避免每个分类单元格一次独立 fsync。
        self._db.execute(
            f"INSERT OR REPLACE INTO {self._CATEGORY_DB_TABLE} (dim, feature, category, hits, count) "
            "VALUES (?, ?, ?, ?, ?)",
            (dim, feature, category, cell.hits, cell.count),
        )

    def _load_categories(self) -> None:
        if self._db is None:
            return
        rows = self._db.execute(
            f"SELECT dim, feature, category, hits, count FROM {self._CATEGORY_DB_TABLE}"
        ).fetchall()
        for dim, feature, category, hits, count in rows:
            cell = self._categories.setdefault(dim, {}).setdefault(feature, {}).setdefault(category, CategoryStats())
            cell.hits = int(hits)
            cell.count = int(count)

    def _persist_weight(self, dim: str, record: OnlineWeightRecord) -> None:
        """持久化单个权重记录（含完整 history）。

        与 _persist_category 一致：不在此处 commit，由 ingest_record /
        ingest_online 统一提交，避免每维度一次独立 fsync。
        """
        if self._db is None:
            return
        self._db.execute(
            f"INSERT OR REPLACE INTO {self._WEIGHT_DB_TABLE} "
            "(dim, current_weight, hit_count, sample_count, history) VALUES (?, ?, ?, ?, ?)",
            (
                dim,
                float(record.current_weight),
                int(record.hit_count),
                int(record.sample_count),
                json.dumps(record.history),
            ),
        )

    def _load_weights(self) -> None:
        """从 SQLite 恢复权重记录（跨会话续训）。"""
        if self._db is None:
            return
        rows = self._db.execute(
            f"SELECT dim, current_weight, hit_count, sample_count, history "
            f"FROM {self._WEIGHT_DB_TABLE}"
        ).fetchall()
        for dim, current_weight, hit_count, sample_count, history in rows:
            try:
                decoded = json.loads(history) if history else []
            except (TypeError, ValueError):
                logger.warning("weight history for %s corrupted; resetting history", dim)
                decoded = []
            self._weights[dim] = OnlineWeightRecord(
                current_weight=float(current_weight),
                hit_count=int(hit_count),
                sample_count=int(sample_count),
                history=[float(v) for v in decoded],
            )

    def get_category_stats(self, dim: str, feature: str) -> dict[str, dict[str, float]]:
        """返回某维度某特征的分类统计: {category: {hits, count, rate}}。"""
        return {
            category: cell.to_dict()
            for category, cell in self._categories.get(dim, {}).get(feature, {}).items()
        }

    def get_all_category_stats(self) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
        """返回所有维度 × 特征 × 类别的分类统计。"""
        return {
            dim: {
                feature: {
                    category: cell.to_dict()
                    for category, cell in feature_stats.items()
                }
                for feature, feature_stats in dim_stats.items()
            }
            for dim, dim_stats in self._categories.items()
        }

    # ------------------------------------------------------------------
    # 在线贝叶斯更新 (Beta-Binomial)
    # ------------------------------------------------------------------

    def _ensure_dim(self, dim: str) -> OnlineWeightRecord:
        if dim not in self._weights:
            prior = self._prior.get(dim, 0.5)
            self._weights[dim] = OnlineWeightRecord(current_weight=prior)
        return self._weights[dim]

    def ingest_record(
        self,
        dim: str,
        hit: bool,
        context: str | None = None,
        failure_mode: str | None = None,
        reward: float | None = None,
        commit: bool = True,
    ) -> None:
        """单维度单次更新 — 在线学习核心。

        可选参数 context / failure_mode / reward 触发分类证据记录。
        ``commit=False`` 时延迟到调用方统一提交（批量场景使用）。
        """
        record = self._ensure_dim(dim)
        record.sample_count += 1
        if hit:
            record.hit_count += 1
        new_weight = record.alpha / (record.alpha + record.beta)
        record.current_weight = new_weight
        record.history.append(new_weight)

        features: dict[str, str] = {}
        if context is not None:
            features["context"] = str(context)
        if failure_mode is not None:
            features["failure_mode"] = str(failure_mode)
        if reward is not None:
            features["reward_bucket"] = self._reward_to_bucket(reward)
        if features:
            self._update_category(dim, features, hit)
        self._persist_weight(dim, record)
        if commit and self._db is not None:
            self._db.commit()

    def ingest_online(self, dimensions: dict[str, bool]) -> dict[str, float]:
        """批量在线更新 — 接受 {dimension: was_hit} 字典，返回更新后的权重"""
        updated = {}
        for dim, hit in dimensions.items():
            self.ingest_record(dim, hit, commit=False)
            updated[dim] = self.get_weight(dim)
        if self._db is not None:
            self._db.commit()
        return updated

    def get_weight(self, dim: str) -> float:
        """获取某维度的当前权重（无需等待样本积累）"""
        record = self._weights.get(dim)
        return record.current_weight if record else self._prior.get(dim, 0.5)

    def get_all_weights(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "current_weight": record.current_weight,
                "hit_count": record.hit_count,
                "sample_count": record.sample_count,
                "confidence": record.confidence,
            }
            for name, record in self._weights.items()
        }

    def export_history(self) -> dict[str, list[float]]:
        """导出各维度权重演化轨迹（跨会话累积）。"""
        return {name: list(record.history) for name, record in self._weights.items()}

    def reset(self, prior: dict[str, float] | None = None, clear_db: bool = False) -> None:
        self._weights = {}
        self._prior = {**self.BAYESIAN_PRIOR, **(prior or {})}
        self._categories = {}
        if clear_db and self._db is not None:
            self._db.execute(f"DELETE FROM {self._CATEGORY_DB_TABLE}")
            self._db.execute(f"DELETE FROM {self._WEIGHT_DB_TABLE}")
            self._db.commit()

    def close(self) -> None:
        """关闭 SQLite 连接（无 db_path 时为空操作）。"""
        if self._db is not None:
            self._db.commit()
            self._db.close()
            self._db = None

    def __enter__(self) -> OnlineLearningEngine:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
