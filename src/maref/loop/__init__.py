"""MAREF Loop Engineering — 执行循环基础框架。

提供通用循环抽象，将分散在 SelfHealingLoop / OscillationFixLoop
/ ContinuousAutoResearch 中的循环模式统一到可复用的 LoopEngine 基类。

Loop 五要素映射:
  - 目标定义 → HaltingCondition.GoalAchieved
  - 上下文管理 → LoopState + CycleReport
  - 可调用工具 → 子类注入
  - 产出评估 → CycleReport.status + summary
  - 停止标准 → HaltingCondition 策略组合
"""

from maref.loop.agent_adapter import (
    AgentTaskResult,
    AgentTaskSpec,
    ClaudeCodeAdapter,
    CodeAgentAdapter,
    CodeAgentRouter,
    CursorAdapter,
    OpenCodeAdapter,
    TraeCNAdapter,
)
from maref.loop.audit_bridge import AuditToTestBridge
from maref.loop.auditor import LoopAuditor, LoopAuditRecord
from maref.loop.code_agent_loop import CodeAgentLoopConfig, GovernedCodeAgentLoop
from maref.loop.engine import LoopEngine
from maref.loop.github_agent_loop import GitHubAgentLoop, GitHubLoopConfig, GitHubTaskSpec
from maref.loop.governed import GovernanceReady, GovernedLoop
from maref.loop.halting import (
    AllOf,
    AnyOf,
    CompletenessGate,
    ConvergenceDetected,
    EvalScoreGate,
    GoalAchieved,
    HaltingCondition,
    HaltingContext,
    HumanConfirmationGate,
    MaxIterations,
    Never,
    SemanticConvergenceDetected,
    Timeout,
)
from maref.loop.oss_growth_loop import OSSGrowthLoop, OSSGrowthLoopConfig, OSSGrowthTaskSpec
from maref.loop.policy import (
    GOVERNANCE_STATE_PRESETS,
    GracefulTimeout,
    PermissionPolicy,
    TokenBudget,
    config_for_governance_state,
    governed_config,
)
from maref.loop.skill_recursion import (
    AuditGate,
    AuditGateStatus,
    ReflectionType,
    SkillArtifact,
    SkillConvergenceDetected,
    SkillRecursionConfig,
    SkillRecursionLoop,
    StrategyVariant,
    TrajectoryResult,
)
from maref.loop.social_agent_loop import SocialLoopConfig, SocialMediaAgentLoop, SocialTaskSpec
from maref.loop.state import CycleReport, LoopConfig, LoopState
from maref.loop.tracking import ExternalFeedbackTracker, ExternalSignalEvent
from maref.loop.verification import (
    CompletenessVerifier,
    VerificationCriterion,
    VerificationReport,
    VerificationSpec,
)

__all__ = [
    # 核心引擎
    "LoopEngine",
    "GovernedLoop",
    "GovernanceReady",
    "GovernedCodeAgentLoop",
    "CodeAgentLoopConfig",
    "GitHubAgentLoop",
    "GitHubLoopConfig",
    "GitHubTaskSpec",
    "OSSGrowthLoop",
    "OSSGrowthLoopConfig",
    "OSSGrowthTaskSpec",
    "SocialMediaAgentLoop",
    "SocialLoopConfig",
    "SocialTaskSpec",
    # 停止条件
    "HaltingCondition",
    "HaltingContext",
    "MaxIterations",
    "Timeout",
    "GoalAchieved",
    "ConvergenceDetected",
    "Never",
    "SemanticConvergenceDetected",
    "AnyOf",
    "AllOf",
    "CompletenessGate",
    "EvalScoreGate",
    "HumanConfirmationGate",
    "ExternalFeedbackTracker",
    "ExternalSignalEvent",
    "AuditToTestBridge",
    # 状态与配置
    "LoopConfig",
    "LoopState",
    "CycleReport",
    # 审计
    "LoopAuditor",
    "LoopAuditRecord",
    # 策略预设
    "GOVERNANCE_STATE_PRESETS",
    "config_for_governance_state",
    "governed_config",
    "TokenBudget",
    "GracefulTimeout",
    "PermissionPolicy",
    # Code Agent 适配器
    "CodeAgentAdapter",
    "CodeAgentRouter",
    "AgentTaskSpec",
    "AgentTaskResult",
    "ClaudeCodeAdapter",
    "OpenCodeAdapter",
    "TraeCNAdapter",
    "CursorAdapter",
    # 完整度验证
    "CompletenessVerifier",
    "VerificationSpec",
    "VerificationCriterion",
    "VerificationReport",
    # 技能递归
    "SkillRecursionLoop",
    "SkillRecursionConfig",
    "SkillArtifact",
    "SkillConvergenceDetected",
    "StrategyVariant",
    "TrajectoryResult",
    "AuditGate",
    "AuditGateStatus",
    "ReflectionType",
]
