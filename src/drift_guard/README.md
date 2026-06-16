# MAREF DriftGuard

## 概述

DriftGuard 是 MAREF 治理框架的安全层，负责检测和缓解 LoRA（Low-Rank Adaptation）微调过程中的人格漂移。核心功能包括：

1. **统计散度计算** — KL 散度、JS 散度、Hellinger 距离
2. **阈值监控** — 基于配置的严重性分级（LOW/MEDIUM/HIGH/CRITICAL）
3. **人工仲裁门控** — HIGH/CRITICAL 级别需要人工审批
4. **基座模型重置** — 自动回滚到已知良好的基线
5. **自动化流水线** — 周期性检测、事件记录、趋势分析

## 架构

```
Base Model Weights
        |
        v
LoRA Adapter (A, B matrices) ---> Delta = scaling * B * A
        |                                |
        |                                v
        |                         Drift Metrics (KL/JS/Hellinger)
        |                                |
        v                                v
Current Weights <--- Base Reset <--- Severity Classification
                                          |
                                          v
                              Human Gate (HIGH/CRITICAL)
                                          |
                                          v
                                    Action Execution
```

## 核心组件

| 模块 | 说明 |
|------|------|
| `types.py` | 数据类型：DriftSeverity, DriftAction, DriftReading, DriftEvent, PipelineConfig |
| `metrics.py` | 散度计算：kl_divergence, js_divergence, hellinger_distance, compute_drift_metrics |
| `pipeline.py` | 流水线：HumanArbitrationGate, BaseModelReset, DriftDetectionPipeline |

## 严重性分级

| 级别 | KL 阈值 | Hellinger 阈值 | 自动动作 |
|------|---------|----------------|----------|
| NONE | < 0.1 | < 0.2 | 无 |
| LOW | >= 0.1 | >= 0.2 | ALERT |
| MEDIUM | >= 0.5 | >= 0.5 | QUARANTINE |
| HIGH | >= 0.5 | >= 0.5 | BASE_RESET（需人工审批） |
| CRITICAL | >= 1.0 | >= 0.5 | EMERGENCY_HALT |

## 人工仲裁门控

```
LOW/MEDIUM severity ──→ AUTO（自动执行）
HIGH/CRITICAL severity ──→ PENDING_REVIEW ──→ 人工审批 ──→ APPROVED/REJECTED
                                    └──→ 超时 ──→ TIMEOUT
```

## 使用示例

```python
import asyncio
import numpy as np
from src.drift_guard.pipeline import DriftDetectionPipeline
from src.drift_guard.types import ModelSignature, PipelineConfig

async def main():
    # 配置流水线
    config = PipelineConfig(
        kl_warning=0.1,
        kl_critical=0.5,
        kl_max=1.0,
    )
    pipeline = DriftDetectionPipeline(config)

    # 模拟权重
    baseline = np.random.randn(1000)
    current = baseline + np.random.randn(1000) * 0.5

    # 检测漂移
    event = await pipeline.check_drift(
        baseline_weights=baseline,
        current_weights=current,
        model=ModelSignature("lora-adapter", "v1"),
        baseline=ModelSignature("base-model", "v1"),
    )

    if event:
        print(f"Drift detected: {event.reading.severity.name}")
        print(f"Action: {event.action_taken.name}")
        print(f"KL divergence: {event.reading.kl_divergence:.4f}")

asyncio.run(main())
```

## 设计决策

### 为什么使用三种散度指标？
- **KL 散度**：最常用，但对分布尾部敏感
- **JS 散度**：对称且有界，适合比较
- **Hellinger 距离**：有界 [0,1]，便于设置阈值

### 为什么需要人工门控？
根据可行性报告，递归训练导致的人格漂移是最高风险。HIGH/CRITICAL 级别的自动重置可能导致服务中断，需要人类确认。

### 基座重置的冷却期？
防止频繁重置导致的震荡。默认 60 秒冷却期，确保系统有时间稳定。
