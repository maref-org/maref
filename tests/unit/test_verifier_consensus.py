from __future__ import annotations

from maref.governance.verifier_consensus import ConsensusStrategy, VerifierConsensus
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry


def test_simple_majority_passes() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.9))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.8))
    reg.register(VerifierEntry(name="v3", model="gemini", methodology="statistical", accuracy=0.1))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True)
    assert result.passed
    assert result.strategy == ConsensusStrategy.SIMPLE_MAJORITY


def test_simple_majority_fails() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.1))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.2))
    reg.register(VerifierEntry(name="v3", model="gemini", methodology="statistical", accuracy=0.1))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True)
    assert not result.passed


def test_unanimity_passes() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.9))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.8))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True, strategy=ConsensusStrategy.UNANIMITY)
    assert result.passed


def test_unanimity_fails() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.9))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.1))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True, strategy=ConsensusStrategy.UNANIMITY)
    assert not result.passed


def test_weighted_majority() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.9))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.1))
    reg.register(VerifierEntry(name="v3", model="gemini", methodology="statistical", accuracy=0.1))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True, strategy=ConsensusStrategy.WEIGHTED_MAJORITY)
    assert result.passed


def test_consensus_no_verifiers() -> None:
    reg = VerifierRegistry()
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True)
    assert not result.passed
    assert result.votes == []
    assert result.agreement == 0.0


def test_consensus_result_to_dict() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.9))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True, strategy=ConsensusStrategy.SIMPLE_MAJORITY)
    d = result.to_dict()
    assert d["passed"] is not None
    assert d["strategy"] == "simple_majority"
    assert isinstance(d["votes"], list)
    assert isinstance(d["agreement"], float)


def test_tie_breaks_fails() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.8))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.1))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(True, strategy=ConsensusStrategy.SIMPLE_MAJORITY)
    assert not result.passed


def test_consensus_with_majority_wrong() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.1))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.1))
    reg.register(VerifierEntry(name="v3", model="gemini", methodology="statistical", accuracy=0.1))
    consensus = VerifierConsensus(reg)
    result = consensus.evaluate(False)
    assert result.passed
