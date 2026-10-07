#!/usr/bin/env python3
"""Failure Classifier Interface（开源版通用接口）。

定义失败分类器的抽象契约，具体实现由私有侧提供（含视觉/读屏通道）。
开源版仅提供接口定义 + E1-E5 枚举 + 策略注入点。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureClass(str, Enum):
    E1_HALLUCINATION = "E1"
    E2_EXECUTION_ERROR = "E2"
    E3_ENVIRONMENT = "E3"
    E4_PLANNING = "E4"
    E5_SPEC_GAP = "E5"


class HealingStrategy(str, Enum):
    RETRY_CORRECTED = "retry-corrected"
    REPLAN = "replan"
    TOOL_FALLBACK = "tool-fallback"
    ESCALATE = "escalate"


@dataclass
class AttributionResult:
    failure_class: FailureClass
    sub_class: str
    root_cause: str
    suggested_strategy: HealingStrategy
    confidence: float
    evidence: list[str]


class FailureClassifier(ABC):
    """失败分类器抽象基类。

    具体实现需注入：
    - 视觉/VLM 读屏通道
    - OCR 通道
    - Grounding 空间定位通道
    - 私有 failure_code 词表与恢复策略映射
    """

    @abstractmethod
    def attribute(self, fingerprint: str, detail: str, screenshot_ref: str | None = None) -> AttributionResult:
        """对单个 fingerprint 做归因。"""
        ...

    @abstractmethod
    def batch_attribute(self, fp_list: list[str] | None = None, since_days: int = 7) -> dict[str, Any]:
        """批量归因未处理事件。"""
        ...


# 默认路由表（可被子类覆盖）
DEFAULT_ROUTING_TABLE: dict[FailureClass, HealingStrategy] = {
    FailureClass.E1_HALLUCINATION: HealingStrategy.REPLAN,
    FailureClass.E2_EXECUTION_ERROR: HealingStrategy.TOOL_FALLBACK,
    FailureClass.E3_ENVIRONMENT: HealingStrategy.RETRY_CORRECTED,
    FailureClass.E4_PLANNING: HealingStrategy.REPLAN,
    FailureClass.E5_SPEC_GAP: HealingStrategy.ESCALATE,
}


def route_strategy(failure_class: FailureClass, sub_class: str = "") -> HealingStrategy:
    """按失败分类路由策略（子类可注入 E3_SUBCLASS_OVERRIDE 覆盖）。"""
    return DEFAULT_ROUTING_TABLE.get(failure_class, HealingStrategy.ESCALATE)


if __name__ == "__main__":
    print("Failure Classifier Interface — 开源版（仅接口定义）")
    print("可用类:", [c for c in dir() if not c.startswith("_")])
