from __future__ import annotations

from maref.evolution.constitution_harness import ConstitutionHarness, EvolutionChange


def test_blocks_red_line_modification() -> None:
    harness = ConstitutionHarness()
    result = harness.check_change(
        EvolutionChange(
            change_id="C1",
            files=["src/maref/recursive/meta_agent_closure.py"],
            description="modify red lines",
            diff_text="- RL-001\n+ changed",
        )
    )
    assert result.allowed is False
    assert "red_line" in result.violations


def test_blocks_safety_gate_disabling() -> None:
    harness = ConstitutionHarness()
    result = harness.check_change(
        EvolutionChange(
            change_id="C2",
            files=["src/maref/recursive/safety_gate_v2.py"],
            description="disable safety gate",
            diff_text="self._safety_gate = None\nSafetyGateV2.active = False",
        )
    )
    assert result.allowed is False
    assert "safety_gate_bypass" in result.violations


def test_blocks_validation_contract_modification() -> None:
    harness = ConstitutionHarness()
    result = harness.check_change(
        EvolutionChange(
            change_id="C3",
            files=[".missions/v0.25.0-security-enhancement/validation-contract.md"],
            description="update validation contract",
            diff_text="+ changed",
        )
    )
    assert result.allowed is False
    assert "forbidden_contract" in result.violations


def test_blocks_missing_audit_for_self_executor_actor() -> None:
    harness = ConstitutionHarness()
    result = harness.check_change(
        EvolutionChange(
            change_id="C4",
            files=["src/maref/recursive/self_executor.py"],
            description="change executor without audit",
            diff_text="+ deploy()",
            audit_planned=False,
        )
    )
    assert result.allowed is False
    assert "missing_audit" in result.violations


def test_allows_normal_audited_change() -> None:
    harness = ConstitutionHarness()
    result = harness.check_change(
        EvolutionChange(
            change_id="C5",
            files=["src/maref/evolution/real_metrics.py"],
            description="improve metrics",
            diff_text="+ test_pass_rate",
            audit_planned=True,
        )
    )
    assert result.allowed is True
    assert result.violations == []
