# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0

"""TransformerLens 权重审计适配器.

为模型权重审计提供 TransformerLens 适配层，支持检测后门触发器与异常激活模式。
TransformerLens 是可选依赖，未安装时降级为返回空报告（backdoor_suspected=False）。

防御威胁 M-002（模型权重后门）：通过分析模型在特定触发词上的激活模式，
检测是否被植入后门触发器。后门触发器会在输入含特定词汇时产生异常激活，
导致模型输出预设的恶意响应。

旁路直连模式:
    本模块不经过 VerifierConsensus 的模拟调用路径，而是直接:
    1. 加载模型权重（当 transformer_lens 可用时）
    2. 对可疑触发词跑前向传播
    3. 检测异常激活模式（超出 3σ 的神经元）
    4. 汇总异常到 WeightAuditReport

同时在 VerifierRegistry 登记元数据用于统计追踪。

Usage:
    from maref.security.weight_auditor import WeightAuditorAdapter

    auditor = WeightAuditorAdapter()
    if auditor.available:
        report = auditor.audit("gpt2", trigger_patterns=["trigger_word"])
        if report.backdoor_suspected:
            print(f"Anomalous activations: {report.anomalous_activations}")
    else:
        print("transformer_lens not installed, audit unavailable")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from maref.security.decorators import security_critical

if TYPE_CHECKING:
    from maref.governance.verifier_registry import VerifierRegistry


@dataclass
class WeightAuditReport:
    """权重审计报告."""

    model_id: str
    """被审计的模型 ID 或路径."""

    backdoor_suspected: bool
    """是否怀疑存在后门触发器."""

    anomalous_activations: list[str]
    """异常激活的层名/神经元 ID 列表."""

    confidence: float
    """检测置信度 0.0-1.0。降级模式为 0.0."""

    details: str
    """审计详情或不可用原因."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "backdoor_suspected": self.backdoor_suspected,
            "anomalous_activations": self.anomalous_activations,
            "confidence": self.confidence,
            "details": self.details,
        }


class WeightAuditorAdapter:
    """TransformerLens 权重审计适配器.

    可选依赖：transformer_lens 未安装时 available=False，
    audit() 返回降级报告（backdoor_suspected=False, confidence=0.0）。

    真实审计流程（当 transformer_lens 可用时）:
        1. 加载模型: HookedTransformer.from_pretrained(model_path)
        2. 对每个 trigger_pattern 跑前向传播
        3. 检查激活值异常（超出 3σ 的神经元）
        4. 汇总异常激活到 anomalous_activations
    """

    def __init__(self) -> None:
        try:
            import transformer_lens  # noqa: F401

            self._available = True
            self._tl_module = transformer_lens
        except ImportError:
            self._available = False
            self._tl_module = None

    @property
    def available(self) -> bool:
        """TransformerLens 是否可用."""
        return self._available

    @security_critical
    def audit(
        self,
        model_path: str,
        trigger_patterns: list[str] | None = None,
    ) -> WeightAuditReport:
        """审计模型权重，检测后门触发器.

        Args:
            model_path: 模型权重路径或 HuggingFace model ID.
            trigger_patterns: 可疑触发词列表（如 ["trigger_word", "backdoor_phrase"]）.
                未提供时使用默认触发词集。

        Returns:
            WeightAuditReport。不可用时返回降级报告。
        """
        if not self._available:
            return WeightAuditReport(
                model_id=model_path,
                backdoor_suspected=False,
                anomalous_activations=[],
                confidence=0.0,
                details=("transformer_lens not installed; install with `pip install maref[audit]`"),
            )

        # 真实审计逻辑（当 transformer_lens 可用时）
        triggers = trigger_patterns or ["<trigger>", "<backdoor>", "<payload>"]
        anomalous: list[str] = []
        max_confidence = 0.0

        try:
            from transformer_lens import HookedTransformer

            model = HookedTransformer.from_pretrained(model_path, device="cpu")

            for trigger in triggers:
                # 跑前向传播并缓存激活
                with model.hooks(fwd_hooks=self._build_activation_hooks(anomalous, trigger)):
                    model.run_with_cache(
                        trigger,
                        names_filter=lambda name: "mlp" in name or "attn" in name,
                    )

            # 简化的异常检测：有异常激活则怀疑后门
            backdoor_suspected = len(anomalous) > 0
            max_confidence = min(1.0, len(anomalous) / 10.0)

        except Exception as e:
            return WeightAuditReport(
                model_id=model_path,
                backdoor_suspected=False,
                anomalous_activations=[],
                confidence=0.0,
                details=f"Audit failed: {e}",
            )

        return WeightAuditReport(
            model_id=model_path,
            backdoor_suspected=backdoor_suspected,
            anomalous_activations=anomalous,
            confidence=max_confidence,
            details=f"Audited {len(triggers)} trigger patterns; "
            f"found {len(anomalous)} anomalous activations",
        )

    def _build_activation_hooks(
        self,
        anomalous_list: list[str],
        trigger_label: str,
    ) -> list[tuple[str, Any]]:
        """构建激活钩子，检测超出 3σ 的神经元.

        这是一个简化实现：真实场景下需要更复杂的统计基线。
        """

        def hook_fn(name: str) -> Any:
            def hook(activation: Any, hook: Any) -> Any:
                # 检测激活值是否超出 3σ（简化版）
                if hasattr(activation, "mean") and hasattr(activation, "std"):
                    mean = activation.mean().item()
                    std = activation.std().item()
                    if std > 0:
                        z_scores = (activation - mean) / std
                        anomalies = (z_scores.abs() > 3.0).any(dim=-1)
                        if anomalies.any():
                            anomalous_list.append(f"{name}:{trigger_label}")
                return activation

            return hook

        return [("blocks.0.mlp.hook_post", hook_fn("blocks.0.mlp.hook_post"))]


def register_weight_auditor_verifier(registry: VerifierRegistry) -> None:
    """在 VerifierRegistry 登记 WeightAuditor 元数据.

    旁路直连模式：元数据登记用于统计追踪，真实审计由
    WeightAuditorAdapter.audit() 直接调用。

    Args:
        registry: VerifierRegistry 实例.
    """
    from maref.governance.verifier_registry import VerifierEntry, VerifierStatus

    entry = VerifierEntry(
        name="weight_auditor",
        model="TransformerLens v1",
        methodology="activation_pattern_analysis",
        status=VerifierStatus.ACTIVE,
        accuracy=0.0,
        recall=0.0,
        bias=0.0,
    )
    registry.register(entry)


__all__ = [
    "WeightAuditReport",
    "WeightAuditorAdapter",
    "register_weight_auditor_verifier",
]
