"""Human Collaboration Layer for MAREF.

Provides human-in-the-loop (HITL), human-on-the-loop (HOTL), and
human-at-the-loop (HATL) collaboration primitives.

Key components:
- HumanDecisionAPI: Standard interface for requesting human decisions
- CollaborationRuleEngine: DSL for WHEN/THEN/ELSE collaboration rules
- InterruptProtocol: PAUSE/ABORT/OVERRIDE signals with global sequencing
"""

from maref.human.decision_api import (
    DecisionMode,
    DecisionRequest,
    DecisionResponse,
    HumanDecisionAPI,
    UrgencyLevel,
)
from maref.human.interrupt_protocol import (
    InterruptProtocol,
    InterruptSignal,
    InterruptType,
)
from maref.human.rule_engine import (
    CollaborationAction,
    CollaborationRule,
    CollaborationRuleEngine,
    RuleCondition,
)

__all__ = [
    "CollaborationAction",
    "CollaborationRule",
    "CollaborationRuleEngine",
    "DecisionMode",
    "DecisionRequest",
    "DecisionResponse",
    "HumanDecisionAPI",
    "InterruptProtocol",
    "InterruptSignal",
    "InterruptType",
    "RuleCondition",
    "UrgencyLevel",
]
