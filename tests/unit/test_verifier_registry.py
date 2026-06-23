from __future__ import annotations

from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry, VerifierStatus


def test_register_and_get() -> None:
    reg = VerifierRegistry()
    e = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    reg.register(e)
    assert reg.get("v1") is not None
    assert reg.get("v1") == e


def test_unregister() -> None:
    reg = VerifierRegistry()
    e = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    reg.register(e)
    reg.unregister("v1")
    assert reg.get("v1") is None


def test_list_active() -> None:
    reg = VerifierRegistry()
    e1 = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    e2 = VerifierEntry(
        name="v2", model="claude-3", methodology="heuristic",
        status=VerifierStatus.INACTIVE,
    )
    reg.register(e1)
    reg.register(e2)
    active = reg.list_active()
    assert len(active) == 1
    assert active[0].name == "v1"


def test_list_all() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check"))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic"))
    assert len(reg.list_all()) == 2


def test_accuracy_and_bias() -> None:
    reg = VerifierRegistry()
    e = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    reg.register(e)
    assert reg.get_accuracy("v1") == 0.0
    assert reg.get_bias("v1") == 0.0

    reg.record_evaluation("v1", correct=True)
    reg.record_evaluation("v1", correct=True)
    reg.record_evaluation("v1", correct=False)
    assert reg.get_accuracy("v1") == 2 / 3


def test_set_status() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check"))
    reg.set_status("v1", VerifierStatus.DEGRADED)
    assert reg.get("v1") is not None
    assert reg.get("v1").status == VerifierStatus.DEGRADED


def test_detect_drift() -> None:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.05))
    reg.register(VerifierEntry(name="v2", model="claude-3", methodology="heuristic", accuracy=0.95))
    drifted = reg.detect_drift(threshold=0.1)
    assert len(drifted) == 1
    assert drifted[0]["name"] == "v1"


def test_accuracy_unknown_verifier() -> None:
    reg = VerifierRegistry()
    assert reg.get_accuracy("nonexistent") == 0.0
    assert reg.get_bias("nonexistent") == 1.0


def test_entry_default_created_at() -> None:
    e = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    assert e.created_at != ""


def test_precision_zero_calls() -> None:
    e = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    assert e.precision == 0.0


def test_record_call_updates_accuracy() -> None:
    e = VerifierEntry(name="v1", model="gpt-4", methodology="cross-check")
    e.record_call(True)
    assert e.total_calls == 1
    assert e.correct_calls == 1
    assert e.accuracy == 1.0
    e.record_call(False)
    assert e.total_calls == 2
    assert e.correct_calls == 1
    assert e.accuracy == 0.5
