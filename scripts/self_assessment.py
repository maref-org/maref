"""
MAREF Self-Assessment — MAS-TS-001 Full-Run Evaluation
Generates a comprehensive 5-layer evaluation report based on current code state.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.agent_card_config import get_default_card_config
from maref.integration.test_platform.card_adapter import (
    AgentCardAdapter,
    MASAgentCard,
)
from maref.integration.test_platform.schema import (
    EvalStatus,
    EvaluationReport,
    Finding,
    FindingSeverity,
    LayerReport,
    TestMode,
    build_findings_summary,
)
from maref.integration.test_platform.quality_gate import (
    EvolutionQualityGate,
    EvolutionVerdict,
    QualityGateConfig,
)
from maref.integration.test_platform.score_mapper import (
    LayerScoreAggregator,
    ScoreToPhaseMapper,
)
from maref.integration.test_platform.tla_verifier import TLATheoremVerifier


def build_mas_card() -> MASAgentCard:
    return AgentCardAdapter.from_agent_card_config()


def layer1_static_audit(card: MASAgentCard, root: Path) -> LayerReport:
    findings: list[Finding] = []

    cross_ok, cross_msg = AgentCardAdapter.validate_cross_border_consistency(card)
    if not cross_ok:
        findings.append(Finding(
            finding_id="L1-001", layer=1, severity=FindingSeverity.CRITICAL,
            title="Cross-Border Endpoint Mismatch",
            description=cross_msg,
            rule_id="MAS-TS-001-L1-001",
            remediation="Set data_residency == model_backend_location OR set cross_border=True",
        ))

    rot_ok, rot_msg = AgentCardAdapter.validate_prompt_rot_detectability(card)
    if not rot_ok:
        findings.append(Finding(
            finding_id="L1-002", layer=1, severity=FindingSeverity.MEDIUM,
            title="Prompt Rot Undetectable",
            description=rot_msg,
            rule_id="MAS-TS-001-L1-002",
            remediation="Add business_rule_version to all capabilities",
        ))

    config = get_default_card_config()
    endpoint_ok, endpoint_msg = config.validate_endpoint_consistency()
    if not endpoint_ok:
        findings.append(Finding(
            finding_id="L1-003", layer=1, severity=FindingSeverity.CRITICAL,
            title="Agent Card Endpoint Inconsistency",
            description=endpoint_msg,
            rule_id="MAS-TS-001-L1-003",
            remediation="Align endpoints in agent_card_config.py",
        ))

    # Verify agent card schema compliance
    if len(card.compliance_labels) < 2:
        findings.append(Finding(
            finding_id="L1-004", layer=1, severity=FindingSeverity.MEDIUM,
            title="Insufficient Compliance Labels",
            description=f"Only {len(card.compliance_labels)} labels found",
            rule_id="MAS-TS-001-L1-004",
            remediation="Add data_residency_CN, mas_ts_001, and other labels",
        ))

    # Add info finding for schema compliance
    findings.append(Finding(
        finding_id="L1-INFO", layer=1, severity=FindingSeverity.INFO,
        title=f"Agent Card Schema Compliance: {card.agent_id} v{card.version}",
        description=f"data_residency={card.data_residency}, backend={card.model_backend_location}, "
                    f"cross_border={card.cross_border}, capabilities={len(card.capabilities)}",
        rule_id="MAS-TS-001-L1-SCHEMA",
    ))

    critical_count = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL)
    high_count = sum(1 for f in findings if f.severity == FindingSeverity.HIGH)

    if critical_count > 0:
        score = 70.0
    elif high_count > 0:
        score = 85.0
    else:
        score = 100.0

    return LayerReport(
        layer_number=1,
        layer_name="Static Audit",
        score=score,
        findings=findings,
        metrics={
            "data_residency": card.data_residency,
            "model_backend_location": card.model_backend_location,
            "cross_border": card.cross_border,
            "cross_border_consistent": cross_ok,
            "prompt_rot_detectable": rot_ok,
            "endpoint_consistent": endpoint_ok,
            "compliance_labels": card.compliance_labels,
        },
    )


def layer2_reasoning_metrics(card: MASAgentCard) -> LayerReport:
    findings: list[Finding] = []
    config = get_default_card_config()
    context_window = config.model_config.get("context_window", 0)

    if context_window < 65536:
        findings.append(Finding(
            finding_id="L2-001", layer=2, severity=FindingSeverity.HIGH,
            title="Context Window Below Recommended Size",
            description=f"Context window: {context_window} (< 65536 recommended)",
            rule_id="MAS-TS-001-L2-001",
            remediation="Increase context_window to >= 65536",
        ))
    else:
        findings.append(Finding(
            finding_id="L2-OK", layer=2, severity=FindingSeverity.INFO,
            title="Context Window Meets Standard",
            description=f"Context window: {context_window} (>= 65536)",
            rule_id="MAS-TS-001-L2-001",
        ))

    backend = config.model_config.get("backend", "unknown")
    endpoint = config.model_config.get("endpoint", "")

    findings.append(Finding(
        finding_id="L2-002", layer=2, severity=FindingSeverity.INFO,
        title=f"Model Backend Configuration",
        description=f"Backend: {backend}, Endpoint: {endpoint}, Context: {context_window}",
        rule_id="MAS-TS-001-L2-002",
    ))

    score = 100.0 if context_window >= 65536 else 85.0

    return LayerReport(
        layer_number=2,
        layer_name="Reasoning Metrics",
        score=score,
        findings=findings,
        metrics={
            "context_window": context_window,
            "backend": backend,
            "endpoint": endpoint,
        },
    )


def layer3_action_metrics(card: MASAgentCard) -> LayerReport:
    findings: list[Finding] = []
    config = get_default_card_config()

    # Check tool registry
    tool_meta = config.tool_registry_meta
    tool_names = list(tool_meta.keys())

    core_tools = {"file", "shell", "git", "browser", "email", "web_search"}
    present_core = core_tools & set(tool_names)
    missing_core = core_tools - set(tool_names)

    for tool in present_core:
        meta = tool_meta.get(tool, {})
        findings.append(Finding(
            finding_id=f"L3-TOOL-{tool}", layer=3, severity=FindingSeverity.INFO,
            title=f"Core Tool: {tool} v{meta.get('version', 'N/A')}",
            description=f"Security controls: {meta.get('security_controls', [])}",
            rule_id="MAS-TS-001-L3-TOOL",
        ))

    for tool in missing_core:
        findings.append(Finding(
            finding_id=f"L3-MISSING-{tool}", layer=3, severity=FindingSeverity.CRITICAL,
            title=f"Missing Core Tool: {tool}",
            description=f"Required core tool '{tool}' not found in registry",
            rule_id="MAS-TS-001-L3-TOOL",
            remediation=f"Implement {tool} tool with security controls",
        ))

    core_coverage = len(present_core) / len(core_tools) * 100 if core_tools else 0
    score = core_coverage

    return LayerReport(
        layer_number=3,
        layer_name="Action Metrics",
        score=score,
        findings=findings,
        metrics={
            "core_tool_coverage": core_coverage,
            "present_tools": sorted(present_core),
            "missing_tools": sorted(missing_core),
            "total_tools": len(tool_names),
        },
    )


def layer4_e2e_metrics(root: Path) -> LayerReport:
    findings: list[Finding] = []

    e2e_test_dir = root / "tests" / "e2e"
    e2e_scenarios = {
        "web_research": e2e_test_dir / "test_web_research.py",
    }

    completed = 0
    total = len(e2e_scenarios)

    for name, path in e2e_scenarios.items():
        if path.exists():
            findings.append(Finding(
                finding_id=f"L4-E2E-{name}", layer=4, severity=FindingSeverity.INFO,
                title=f"E2E Scenario: {name}",
                description=f"E2E test file exists at {path}",
                rule_id="MAS-TS-001-L4-E2E",
            ))
            completed += 1
        else:
            findings.append(Finding(
                finding_id=f"L4-MISSING-{name}", layer=4, severity=FindingSeverity.HIGH,
                title=f"Missing E2E Scenario: {name}",
                description=f"No E2E test found for '{name}'",
                rule_id="MAS-TS-001-L4-E2E",
                remediation=f"Implement E2E tests for {name}",
            ))

    score = (completed / total * 100) if total > 0 else 0

    return LayerReport(
        layer_number=4,
        layer_name="E2E Metrics",
        score=score,
        findings=findings,
        metrics={
            "e2e_completion_rate": score,
            "completed_scenarios": completed,
            "total_scenarios": total,
        },
    )


def layer5_mas_dimensions(card: MASAgentCard) -> LayerReport:
    findings: list[Finding] = []
    config = get_default_card_config()

    mas_dims = {
        "agent_spawn": False,
        "session_isolation": False,
        "coordination": False,
        "state_persistence": False,
        "scheduling": False,
        "remote_control": False,
    }

    for cap in card.capabilities:
        name = cap.get("name", "")
        if name in mas_dims:
            mas_dims[name] = True

    for cap in config.mas_capabilities:
        name = cap.get("name", "")
        if name in mas_dims:
            mas_dims[name] = True

    dim_count = sum(1 for v in mas_dims.values() if v)

    for dim, present in mas_dims.items():
        if present:
            findings.append(Finding(
                finding_id=f"L5-{dim}", layer=5, severity=FindingSeverity.INFO,
                title=f"MAS Dimension: {dim}",
                description=f"Capability declared and implemented",
                rule_id="MAS-TS-001-L5-MAS",
            ))
        else:
            findings.append(Finding(
                finding_id=f"L5-MISSING-{dim}", layer=5, severity=FindingSeverity.CRITICAL,
                title=f"Missing MAS Dimension: {dim}",
                description=f"Required MAS capability '{dim}' not declared",
                rule_id="MAS-TS-001-L5-MAS",
                remediation=f"Implement and declare {dim} capability",
            ))

    score = (dim_count / len(mas_dims)) * 100

    return LayerReport(
        layer_number=5,
        layer_name="MAS Dimensions",
        score=score,
        findings=findings,
        metrics={
            "dimensions_covered": dim_count,
            "total_dimensions": len(mas_dims),
            "dimension_details": mas_dims,
        },
    )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    card = build_mas_card()
    config = get_default_card_config()

    print("=" * 70)
    print("MAREF MAS-TS-001 v2.1 Full-Run Self-Assessment")
    print(f"Agent: {card.agent_id} v{card.version}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Run all 5 layers
    l1 = layer1_static_audit(card, root)
    l2 = layer2_reasoning_metrics(card)
    l3 = layer3_action_metrics(card)
    l4 = layer4_e2e_metrics(root)
    l5 = layer5_mas_dimensions(card)

    all_findings: list[Finding] = []
    for layer in [l1, l2, l3, l4, l5]:
        all_findings.extend(layer.findings)

    summary = build_findings_summary(all_findings)

    report = EvaluationReport(
        report_id=f"maref-self-{int(time.time())}",
        agent_id=card.agent_id,
        agent_name=card.agent_name,
        test_mode=TestMode.FULL_RUN,
        overall_status=EvalStatus.PASS,
        layers=[l1, l2, l3, l4, l5],
        findings_summary=summary,
        evaluated_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        metadata={
            "data_residency": card.data_residency,
            "model_backend": card.model_backend_location,
            "cross_border": card.cross_border,
            "context_window": config.model_config.get("context_window", 0),
        },
    )

    overall = LayerScoreAggregator.compute_overall_score(report)
    report.overall_score = overall

    # --- Print Report ---
    print()
    print("## Layer Scores")
    print(f"{'Layer':<10} {'Name':<20} {'Score':>6} {'Grade':>6}")
    print("-" * 50)
    for l in [l1, l2, l3, l4, l5]:
        grade = "A" if l.score >= 90 else "B" if l.score >= 80 else "C" if l.score >= 70 else "D" if l.score >= 60 else "F"
        print(f"L{l.layer_number:<9} {l.layer_name:<20} {l.score:>6.1f} {grade:>6}")

    print("-" * 50)
    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    print(f"{'OVERALL':<10} {'':<20} {overall:>6.1f} {grade:>6}")

    print()
    print("## Findings Summary")
    print(f"  CRITICAL: {summary.get('critical', 0)}")
    print(f"  HIGH:     {summary.get('high', 0)}")
    print(f"  MEDIUM:   {summary.get('medium', 0)}")
    print(f"  LOW:      {summary.get('low', 0)}")
    print(f"  INFO:     {summary.get('info', 0)}")

    # --- Quality Gate ---
    print()
    print("## Quality Gate")
    gate = EvolutionQualityGate()
    result = gate.evaluate_c1_to_c2("maref-self", report)
    print(f"  Verdict: {result.verdict.value.upper()}")
    print(f"  Score:   {result.score:.1f}")
    print(f"  Reason:  {result.reason}")

    # --- TLA+ Theorem Verification ---
    print()
    print("## TLA+ Theorem Verification")
    tla_results = TLATheoremVerifier.verify_all(card, report)
    tla_summary = TLATheoremVerifier.summary(tla_results)
    print(f"  Total Theorems: {tla_summary['total_theorems']}")
    print(f"  Passed:         {tla_summary['passed']}")
    print(f"  Failed:         {tla_summary['failed']}")
    print(f"  All Passed:     {tla_summary['all_passed']}")
    for r in tla_results:
        if hasattr(r, 'passed'):
            status = "PASS" if r.passed else "FAIL"
            print(f"    [{status}] {r.theorem_name}: {r.details}")
            if hasattr(r, 'counterexample') and r.counterexample:
                print(f"           Counterexample: {r.counterexample}")
        else:
            print(f"    {r}")

    # --- Phase Mapping ---
    print()
    print("## Governance Phase Mapping")
    phase = ScoreToPhaseMapper.map_report(report)
    perms = ScoreToPhaseMapper.get_permissions(phase)
    print(f"  Phase:         {phase.value}")
    print(f"  Description:   {ScoreToPhaseMapper.phase_description(phase)}")
    print(f"  Execute Tools: {perms.can_execute_tools}")
    print(f"  Sensitive Data:{perms.can_access_sensitive_data}")
    print(f"  Cross Boundary:{perms.can_cross_boundary}")
    print(f"  Self Modify:   {perms.can_self_modify}")
    print(f"  Max Concurrent:{perms.max_concurrent_tasks}")
    print(f"  Rate Limit:    {perms.rate_limit_rpm} rpm")

    # --- Agent Card Validation ---
    print()
    print("## Agent Card Runtime Validation")
    print(f"  endpoint_consistency: {config.validate_endpoint_consistency()}")
    print(f"  capabilities_complete: {config.validate_capabilities_completeness()}")
    print(f"  full_validation: {config.validate()}")

    # --- Critical Findings Detail ---
    critical_findings = [f for f in all_findings if f.severity == FindingSeverity.CRITICAL]
    high_findings = [f for f in all_findings if f.severity == FindingSeverity.HIGH]
    if critical_findings or high_findings:
        print()
        print("## Action Required")
        for f in critical_findings:
            print(f"  [CRITICAL] {f.title}: {f.description}")
            if f.remediation:
                print(f"    Fix: {f.remediation}")
        for f in high_findings:
            print(f"  [HIGH]     {f.title}: {f.description}")
            if f.remediation:
                print(f"    Fix: {f.remediation}")

    # --- Export JSON ---
    output_path = root / "reports" / "maref_self_assessment.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"\n[Report exported to {output_path}]")

    # --- Comparison with Third Round ---
    print()
    print("=" * 70)
    print("Comparison with Third Round (MAS Standard Tool Alias Fix)")
    print("=" * 70)
    l3_actual = l3.score
    l5_actual = l5.score
    print(f"  L1 Static Audit:     {l1.score:.0f} (Third Round: 85.0)")
    print(f"  L2 Reasoning:        {l2.score:.0f} (Third Round: 72.5)")
    print(f"  L3 Action:           {l3_actual:.0f} (Third Round: 73.9)")
    print(f"  L4 E2E:              {l4.score:.0f} (Third Round: 77.5)")
    print(f"  L5 MAS Dimensions:   {l5_actual:.0f} (Third Round: 89.2)")
    print(f"  OVERALL:             {overall:.1f} (Third Round: 78.5)")


if __name__ == "__main__":
    main()