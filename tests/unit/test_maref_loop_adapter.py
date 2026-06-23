from __future__ import annotations

from maref.integration.maref_loop_adapter import MAREFLoop


def test_register_verifier() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check")
    verifiers = loop.get_verifiers()
    assert len(verifiers) == 1
    assert verifiers[0]["name"] == "v1"


def test_check_passes_with_good_verifiers() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.9)
    loop.register_verifier("v2", "claude-3", "heuristic", accuracy=0.8)
    result = loop.check("deploy", {"env": "staging"})
    assert result["passed"]


def test_check_fails_with_bad_verifiers() -> None:
    loop = MAREFLoop()
    result = loop.check("deploy", {"env": "staging"})
    assert not result["passed"]


def test_check_fails_with_wrong_verifiers() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.1)
    loop.register_verifier("v2", "claude-3", "heuristic", accuracy=0.2)
    result = loop.check("deploy", {"env": "staging"})
    assert not result["passed"]


def test_record() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.5)
    loop.record("deploy", {"success": True})
    verifiers = loop.get_verifiers()
    assert verifiers[0]["accuracy"] == 1.0


def test_record_failure() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.5)
    loop.record("deploy", {"success": False})
    verifiers = loop.get_verifiers()
    assert verifiers[0]["accuracy"] == 0.0


def test_get_history() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.9)
    loop.check("deploy", {"env": "staging"})
    history = loop.get_history()
    assert len(history) == 1
    assert history[0]["action"] == "deploy"


def test_get_history_empty() -> None:
    loop = MAREFLoop()
    assert loop.get_history() == []


def test_get_verifiers_empty() -> None:
    loop = MAREFLoop()
    assert loop.get_verifiers() == []


def test_detect_drift_empty() -> None:
    loop = MAREFLoop()
    assert loop.detect_drift() == []


def test_detect_drift_with_bad_verifier() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.5)
    loop.record("action", {"success": False})
    loop.record("action", {"success": False})
    drifted = loop.detect_drift()
    assert len(drifted) == 1
    assert drifted[0]["name"] == "v1"


def test_consensus_tracks_agreement() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.9)
    loop.register_verifier("v2", "claude-3", "heuristic", accuracy=0.8)
    result = loop.check("deploy", {"env": "staging"})
    assert result["agreement"] > 0


def test_multiple_checks_record_separate_history() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.9)
    loop.check("deploy", {"env": "staging"})
    loop.check("rollback", {"reason": "timeout"})
    assert len(loop.get_history()) == 2


def test_register_with_accuracy() -> None:
    loop = MAREFLoop()
    loop.register_verifier("v1", "gpt-4", "cross-check", accuracy=0.85)
    verifiers = loop.get_verifiers()
    assert verifiers[0]["accuracy"] == 0.85
