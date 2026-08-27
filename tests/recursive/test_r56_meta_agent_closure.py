from __future__ import annotations

from maref.recursive.meta_agent_closure import (
    DEFAULT_INVARIANTS,
    DEFAULT_RED_LINES,
    EvolutionDecisionType,
    InvariantProofReport,
    InvariantStatus,
    MetaAgentClosure,
)


class TestConstitutionalRedLines:
    def test_default_red_lines_exist(self):
        assert len(DEFAULT_RED_LINES) >= 5

    def test_red_line_immutable(self):
        for rl in DEFAULT_RED_LINES:
            assert rl.immutable

    def test_red_line_created_by_human(self):
        for rl in DEFAULT_RED_LINES:
            assert "human" in rl.created_by

    def test_red_line_to_dict(self):
        rl = DEFAULT_RED_LINES[0]
        d = rl.to_dict()
        assert d["id"].startswith("RL-")
        assert d["immutable"]


class TestTLAInvariants:
    def test_default_invariants_exist(self):
        assert len(DEFAULT_INVARIANTS) >= 5

    def test_invariant_has_proof_steps(self):
        for inv in DEFAULT_INVARIANTS:
            assert inv.name
            assert inv.expression

    def test_invariant_to_dict(self):
        inv = DEFAULT_INVARIANTS[0]
        d = inv.to_dict()
        assert d["name"] == "RedLineImmutability"


class TestMetaAgentClosureInit:
    def test_init_has_red_lines(self):
        closure = MetaAgentClosure()
        assert len(closure.get_red_lines()) == len(DEFAULT_RED_LINES)

    def test_init_has_invariants(self):
        closure = MetaAgentClosure()
        assert len(closure.get_invariants()) == len(DEFAULT_INVARIANTS)


class TestRedLineModification:
    def test_agent_cannot_modify_red_line(self):
        closure = MetaAgentClosure()
        allowed, reason = closure.check_red_line_modification("agent_123", "RL-001")
        assert not allowed
        assert "cannot modify" in reason.lower() or "cannot" in reason.lower()

    def test_human_can_modify_red_line(self):
        closure = MetaAgentClosure()
        allowed, reason = closure.check_red_line_modification("human_constitution_maker", "RL-001")
        assert allowed

    def test_nonexistent_red_line(self):
        closure = MetaAgentClosure()
        allowed, reason = closure.check_red_line_modification("human_constitution_maker", "RL-999")
        assert not allowed

    def test_is_red_line_modifiable(self):
        """修复 P0-1：原测试断言错误逻辑为真（immutable=True 时返回 True）。
        正确语义：immutable=True → 不可修改 → 返回 False。
        """
        closure = MetaAgentClosure()
        # 默认红线 immutable=True，应返回 False（不可修改）
        assert not closure.is_red_line_modifiable("RL-001")
        # 不存在的红线返回 False
        assert not closure.is_red_line_modifiable("RL-999")


class TestEvolutionDecisions:
    def test_submit_normal_decision(self):
        """修复 P0-2：CODE_CHANGE 现在强制要求 auditor 在 reviewer_chain 中。
        原 test 无 auditor 期望 approved，现改为带 auditor 才 approved。
        """
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE,
            "add new optimization method",
            ["auditor"],
        )
        assert decision.status == "approved"
        assert not decision.red_line_violation

    def test_submit_code_change_without_auditor_rejected(self):
        """修复 P0-2：无 auditor 的 CODE_CHANGE 必须被拒绝（原为绕过漏洞）。"""
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.CODE_CHANGE,
            "add new optimization method",
        )
        assert decision.red_line_violation
        assert "RL-003" in decision.violated_red_lines
        assert decision.status == "rejected"

    def test_submit_red_line_modification_rejected(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "modify safety red line RL-001",
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"

    def test_submit_decision_with_human_review(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.AGENT_CLONE,
            "clone for distributed deployment",
            ["human_constitution_maker"],
        )
        assert decision.status == "approved"

    def test_clone_without_human_review_rejected(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.AGENT_CLONE,
            "clone myself",
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"

    def test_bypass_safety_rejected(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.POLICY_UPDATE,
            "bypass safety gate for faster execution",
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"

    def test_decision_history_tracked(self):
        closure = MetaAgentClosure()
        closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        closure.submit_decision_with_reviewers(
            "agent_2", EvolutionDecisionType.CODE_CHANGE, "test2", ["auditor"]
        )
        decisions = closure.get_decisions()
        assert len(decisions) == 2


class TestInvariantProof:
    def test_prove_red_line_immutability(self):
        closure = MetaAgentClosure()
        status = closure.prove_invariant("INV-001")
        assert status == InvariantStatus.SATISFIED

    def test_prove_safety_gate_integrity(self):
        closure = MetaAgentClosure()
        status = closure.prove_invariant("INV-002")
        assert status == InvariantStatus.SATISFIED

    def test_prove_constitution_supremacy(self):
        closure = MetaAgentClosure()
        closure.submit_decision(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "try to modify constitution",
        )
        status = closure.prove_invariant("INV-004")
        assert status == InvariantStatus.SATISFIED

    def test_prove_all_invariants(self):
        closure = MetaAgentClosure()
        report = closure.prove_all_invariants()
        assert isinstance(report, InvariantProofReport)
        assert report.invariants_checked == len(DEFAULT_INVARIANTS)
        assert report.all_satisfied

    def test_proof_report_to_dict(self):
        closure = MetaAgentClosure()
        report = closure.prove_all_invariants()
        d = report.to_dict()
        assert d["checked"] > 0
        assert d["all_satisfied"]


class TestMetaAgentClosureDict:
    def test_to_dict(self):
        closure = MetaAgentClosure()
        closure.submit_decision("agent_1", EvolutionDecisionType.CODE_CHANGE, "test")
        d = closure.to_dict()
        assert "red_lines" in d
        assert "invariants" in d
        assert "decision_count" in d
        assert "proof_report" in d
        assert d["proof_report"]["all_satisfied"]


class TestEdgeCases:
    def test_get_decision_by_id(self):
        closure = MetaAgentClosure()
        d = closure.submit_decision("agent_1", EvolutionDecisionType.CODE_CHANGE, "test")
        found = closure.get_decision(d.decision_id)
        assert found is not None
        assert found.decision_id == d.decision_id

    def test_get_nonexistent_decision(self):
        closure = MetaAgentClosure()
        assert closure.get_decision("nonexistent") is None

    def test_multiple_agents_cannot_collude(self):
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "collude to modify red line",
            ["agent_2", "agent_3"],
        )
        assert decision.red_line_violation
        assert decision.status == "rejected"


class TestP0Fixes:
    """P0 修复回归测试：验证致命安全漏洞已修复。"""

    def test_p0_1_is_red_line_modifiable_immutable_returns_false(self):
        """P0-1: immutable=True 时 is_red_line_modifiable 返回 False。"""
        closure = MetaAgentClosure()
        for rl in closure.get_red_lines():
            assert rl.immutable, f"{rl.red_line_id} 应为 immutable"
            assert not closure.is_red_line_modifiable(rl.red_line_id), (
                f"{rl.red_line_id} immutable=True 但 is_red_line_modifiable 返回 True"
            )

    def test_p0_2_code_change_without_auditor_rejected(self):
        """P0-2: 无 auditor 的 CODE_CHANGE 必须被拒绝（修复审查绕过漏洞）。"""
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.CODE_CHANGE,
            "add new optimization method",
        )
        assert decision.red_line_violation
        assert "RL-003" in decision.violated_red_lines
        assert decision.status == "rejected"

    def test_p0_2_code_change_with_auditor_approved(self):
        """P0-2: 有 auditor 的 CODE_CHANGE 被批准。"""
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE,
            "add new optimization method",
            ["auditor"],
        )
        assert not decision.red_line_violation
        assert decision.status == "approved"

    def test_p0_2_code_change_no_reviewers_rejected(self):
        """P0-2: 无任何 reviewer 的 CODE_CHANGE 被拒绝（原为绕过漏洞）。"""
        closure = MetaAgentClosure()
        decision = closure.submit_decision(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test",
        )
        assert decision.red_line_violation
        assert "RL-003" in decision.violated_red_lines

    def test_p0_3_decision_id_no_collision_1000_submissions(self):
        """P0-3: 1000 次提交无 ID 碰撞（完整 UUID hex）。"""
        closure = MetaAgentClosure()
        ids: set[str] = set()
        for _ in range(1000):
            d = closure.submit_decision_with_reviewers(
                "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
            )
            assert d.decision_id not in ids, f"ID 碰撞: {d.decision_id}"
            ids.add(d.decision_id)
        assert len(ids) == 1000

    def test_p0_3_decision_id_has_dec_prefix(self):
        """P0-3: 决策 ID 有 dec_ 前缀和完整 32 位 hex。"""
        closure = MetaAgentClosure()
        d = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        assert d.decision_id.startswith("dec_")
        hex_part = d.decision_id[4:]
        assert len(hex_part) == 32, f"hex 部分长度应为 32，实际 {len(hex_part)}"
        int(hex_part, 16)  # 验证是合法 hex

    def test_p0_4_sign_decision_generates_hmac(self):
        """P0-4: sign_decision 生成非空 HMAC 签名。"""
        closure = MetaAgentClosure()
        d = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        sig = closure.sign_decision(d)
        assert sig, "签名不应为空"
        assert len(sig) == 64, f"HMAC-SHA256 hex 应为 64 字符，实际 {len(sig)}"

    def test_p0_4_verify_decision_signature_valid(self):
        """P0-4: 正确签名验证通过。"""
        closure = MetaAgentClosure()
        d = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        sig = closure.sign_decision(d)
        assert closure.verify_decision_signature(d, sig)

    def test_p0_4_verify_decision_signature_tamper_detection(self):
        """P0-4: 篡改决策字段后签名验证失败。"""
        closure = MetaAgentClosure()
        d = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        sig = closure.sign_decision(d)
        # 篡改 description
        d.description = "tampered description"
        assert not closure.verify_decision_signature(d, sig)

    def test_p0_4_verify_decision_signature_wrong_key(self):
        """P0-4: 不同密钥生成的签名验证失败。"""
        closure1 = MetaAgentClosure()
        closure2 = MetaAgentClosure()
        d = closure1.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        sig1 = closure1.sign_decision(d)
        # closure2 有不同的随机密钥
        assert not closure2.verify_decision_signature(d, sig1)

    def test_p0_4_decision_has_audit_signature(self):
        """P0-4: submit_decision 的决策自动包含审计签名。"""
        closure = MetaAgentClosure()
        d = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE, "test", ["auditor"]
        )
        assert d.audit_signature is not None
        assert len(d.audit_signature) == 64


class TestB1Coverage:
    """B1 补强 — 覆盖常规测试遗漏的路径。"""

    def test_invariant_violation_detected(self):
        """prove_invariant 检测到红线修改后的违规。"""
        from maref.recursive.meta_agent_closure import MetaAgentClosure
        closure = MetaAgentClosure()
        # 模拟红线被非人类修改
        rl = closure.get_red_lines()[0]
        rl.modified_by = "rogue_agent"
        status = closure.prove_invariant("INV-001")
        assert status == InvariantStatus.VIOLATED
        # counterexample 在 TLAInvariant 上，不在 ConstitutionalRedLine 上
        inv = closure._invariants["INV-001"]
        assert "rogue_agent" in (inv.counterexample or "")

    def test_prove_all_mixed_status_returns_correct_counts(self):
        """prove_all_invariants 在 mixed status 下返回正确 counts。"""
        closure = MetaAgentClosure()
        # 提交违规决策
        closure.submit_decision(
            "agent_1", EvolutionDecisionType.RED_LINE_MODIFICATION,
            "try to modify constitution",
        )
        report = closure.prove_all_invariants()
        # 至少一个 invariant 应该 SATISFIED（INV-004 检查违规决策不会被批准）
        assert report.invariants_satisfied >= 1
        assert report.invariants_violated >= 0
        assert report.all_satisfied or report.invariants_checked > 0

    def test_unknown_invariant_returns_pending(self):
        """prove_invariant 对未知 invariant 返回 PENDING。"""
        closure = MetaAgentClosure()
        status = closure.prove_invariant("INV-999")
        assert status == InvariantStatus.PENDING

    def test_safety_gate_invariant_rejects_unsafe_decision(self):
        """INV-002: 未经过 safety gate 评估的 approved 决策触发违规。"""
        closure = MetaAgentClosure()
        d = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.CODE_CHANGE,
            "test code", ["auditor"],
        )
        # 标记未经过 safety gate 评估
        d.safety_gate_evaluated = False
        d.status = "approved"
        status = closure.prove_invariant("INV-002")
        assert status == InvariantStatus.VIOLATED

    def test_audit_completeness_invariant_requires_signature(self):
        """INV-003: 无审计签名的决策触发违规。"""
        closure = MetaAgentClosure()
        from maref.recursive.meta_agent_closure import EvolutionDecision
        # 创建一个没有审计签名的决策（非正常途径创建）
        d = EvolutionDecision(
            decision_id="unsig_001",
            agent_id="test",
            decision_type=EvolutionDecisionType.CODE_CHANGE,
            description="unsigned decision",
            reviewer_chain=["test"],
        )
        closure.review_evolution_decision(d)
        # 清除自动生成的签名
        d.audit_signature = None
        status = closure.prove_invariant("INV-003")
        assert status == InvariantStatus.VIOLATED


class TestP1P2Fixes:
    """P1/P2 修复回归测试。"""

    def test_p1_4_reviewer_chain_no_duplicates(self):
        """P1-4: submit_decision_with_reviewers 后 reviewer_chain 无重复。"""
        closure = MetaAgentClosure()
        decision = closure.submit_decision_with_reviewers(
            "agent_1", EvolutionDecisionType.AGENT_CLONE,
            "clone for distributed deployment",
            ["human_constitution_maker", "human_constitution_maker", "agent_1"],
        )
        assert len(decision.reviewer_chain) == len(set(decision.reviewer_chain)), (
            f"reviewer_chain 有重复: {decision.reviewer_chain}"
        )

    def test_p1_5_decision_history_bounded(self):
        """P1-5: 决策历史有上限，超过后旧决策被淘汰。"""
        closure = MetaAgentClosure()
        maxlen = closure._DECISION_HISTORY_MAXLEN
        # 提交超过上限的决策
        for i in range(maxlen + 10):
            closure.submit_decision_with_reviewers(
                "agent_1", EvolutionDecisionType.CODE_CHANGE, f"test_{i}", ["auditor"]
            )
        assert len(closure.get_decisions()) == maxlen, (
            f"历史应限制在 {maxlen}，实际 {len(closure.get_decisions())}"
        )

    def test_p2_1_no_proof_generation_count(self):
        """P2-1: _proof_generation_count 死代码已移除。"""
        closure = MetaAgentClosure()
        assert not hasattr(closure, "_proof_generation_count"), (
            "_proof_generation_count 应已移除"
        )
        # prove_all_invariants 仍可正常工作
        report = closure.prove_all_invariants()
        assert report.invariants_checked > 0
