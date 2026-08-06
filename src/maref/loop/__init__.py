"""
MAREF Loop Engineering — three meta-pattern templates + governance bridge.

Provides:
- ConvergentLoop: monotonically convergent improvement loop
- ExploratoryLoop: diversity-seeking discovery loop
- InteractiveLoop: human-in-the-loop conversation loop
- LoopGovernanceBridge: connects loops to GovernanceStateMachine
"""

from maref.loop.base import ConvergentResult, LoopBase, LoopResult, LoopState
from maref.loop.bridge import LoopGovernanceBridge
from maref.loop.budgets import TimeBudget, TokenBudget
from maref.loop.convergent import ConvergentLoop
from maref.loop.exploratory import ExploratoryLoop
from maref.loop.interactive import (
    ConversationContext,
    InteractiveLoop,
    RepetitionDetector,
    SentimentSafetyValve,
)
from maref.loop.protocols import (
    AgentResponse,
    ConversationSummary,
    Discovery,
    EvaluationResult,
    ExplorationResult,
    LoopStopReason,
    ToolBoundary,
    ToolPermission,
    TurnResult,
)

__all__ = [
    "LoopBase",
    "LoopResult",
    "ConvergentResult",
    "LoopState",
    "ConvergentLoop",
    "ExploratoryLoop",
    "InteractiveLoop",
    "LoopGovernanceBridge",
    "TokenBudget",
    "TimeBudget",
    "ToolBoundary",
    "ToolPermission",
    "EvaluationResult",
    "Discovery",
    "ExplorationResult",
    "TurnResult",
    "ConversationSummary",
    "AgentResponse",
    "LoopStopReason",
    "ConversationContext",
    "RepetitionDetector",
    "SentimentSafetyValve",
]
