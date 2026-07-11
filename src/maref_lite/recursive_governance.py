from __future__ import annotations
import dataclasses
import typing
from drift_guard.policy_sandbox import PolicySandbox
from maref.governance import GovernanceProtocol
from maref_lite.governance import GovernanceConfig, GovernanceStateMachine
from maref_lite.meta_learning import MetaLearner
from maref_lite.self_healing_loop import SelfHealingLoop
from sidecar.protocol import SidecarProtocol

@dataclasses.dataclass
class RecursiveGovernanceConfig:
    max_iterations: int = 100
    convergence_threshold: float = 0.01
    oscillation_detection_window: int = 10

class MAREFSelfAdapter:
    def __init__(self, config: RecursiveGovernanceConfig) -> None:
        self.config = config
        self.iteration_count: int = 0
        self.history: list[float] = []

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            "config": dataclasses.asdict(self.config),
            "iteration_count": self.iteration_count,
            "history": self.history,
        }

    def _detect_oscillation(self) -> bool:
        if len(self.history) < self.config.oscillation_detection_window:
            return False
        window = self.history[-self.config.oscillation_detection_window:]
        diffs = [abs(window[i] - window[i - 1]) for i in range(1, len(window))]
        return all(d < self.config.convergence_threshold for d in diffs)

class RecursiveGovernanceOverlay:
    def __init__(self, config: RecursiveGovernanceConfig) -> None:
        self.config = config
        self.adapter = MAREFSelfAdapter(config)
        self.governance = GovernanceStateMachine(GovernanceConfig())
        self.meta_learner = MetaLearner()
        self.healing_loop = SelfHealingLoop()
        self.sidecar = SidecarProtocol()
        self.sandbox = PolicySandbox()