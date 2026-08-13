# MAREF-Lite 核心

## 概述

MAREF-Lite 是 MAREF 治理框架的轻量级实现，包含 10 态 Gray code 状态机、治理策略引擎和核心整合层。

## 组件

| 模块 | 说明 |
|------|------|
| `state_machine.py` | 10 态 Gray code 状态机 |
| `policy.py` | 策略引擎和默认策略 |
| `governance.py` | 治理叠加层（整合 Sidecar + DriftGuard） |

## 状态机

```
INIT(0000) -> OBSERVE(0001) -> ANALYZE(0011) -> EVALUATE(0010) -> DECIDE(0110) -> ACT(0111) -> VERIFY(0101) -> STABILIZE(0100) -> REPORT(1100) -> HALT(1101)
  熵=0          熵=1            熵=2             熵=2              熵=3           熵=4          熵=3           熵=1              熵=0          熵=0 (吸收态)
```

## 默认策略

| 策略 | 触发条件 | 动作 | 优先级 |
|------|----------|------|--------|
| critical_entropy | 熵 >= 4 | FORCE_STABILIZE | 100 |
| high_entropy | 熵 >= 3 | TRANSITION -> ANALYZE | 80 |
| critical_anomaly | 严重异常 | FORCE_HALT | 200 |
| drift_verify | 高/严重漂移 | TRANSITION -> VERIFY | 150 |
| state_timeout | 状态超时 300s | ALERT | 50 |

## 使用示例

```python
from src.maref_lite.state_machine import GovernanceStateMachine, GovernanceState
from src.maref_lite.policy import create_default_policies

# 创建状态机
sm = GovernanceStateMachine()

# 执行状态转换
sm.transition(GovernanceState.OBSERVE)
sm.transition(GovernanceState.ANALYZE)

# 强制稳定
sm.force_stabilize()

# 获取状态
print(sm.current_state.name)  # STABILIZE
print(sm.current_entropy)  # 1
```
