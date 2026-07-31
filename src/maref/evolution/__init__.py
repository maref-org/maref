"""MAREF Recursive Evolution — package exports."""

from maref.evolution.constitution_harness import (
    ConstitutionCheckResult,
    ConstitutionHarness,
    EvolutionChange,
)
from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine
from maref.evolution.evo_genotype import AgentGenotype, GenotypePool
from maref.evolution.evo_state import EvoStateManager
from maref.evolution.evolution_vault import EvolutionVault, RoundVault
from maref.evolution.iteration_analyzer import IterationAnalysisResult, IterationAnalyzer
from maref.evolution.high_order_convergence import ConvergenceReport, HighOrderConvergenceMonitor
from maref.evolution.metrics import (
    AcceptanceCriteria,
    CycleResult,
    CycleSpec,
    EvolutionMetrics,
    EvolutionResult,
)
from maref.evolution.reporter import generate_cycle_report, generate_final_report

__all__ = [
    "RecursiveEvolutionEngine",
    "EvolutionConfig",
    "EvolutionMetrics",
    "EvolutionResult",
    "CycleResult",
    "CycleSpec",
    "AcceptanceCriteria",
    "AgentGenotype",
    "GenotypePool",
    "EvoStateManager",
    "EvolutionVault",
    "RoundVault",
    "IterationAnalysisResult",
    "IterationAnalyzer",
    "HighOrderConvergenceMonitor",
    "ConvergenceReport",
    "ConstitutionCheckResult",
    "ConstitutionHarness",
    "EvolutionChange",
    "generate_cycle_report",
    "generate_final_report",
]
