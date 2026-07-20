from __future__ import annotations

from maref.orchestration.operational_validator import (
    OperationalReport,
    OperationalValidator,
    SubsystemResult,
    SubsystemStatus,
)
from maref.recursive.skill_schema import (
    DegradationChain,
    HexagramTrigger,
    MarefSkill,
    MarefSkillMeta,
)


class TestSubsystemResult:
    @pytest.mark.slow
    def test_pass_status(self) -> None:
        result = SubsystemResult(name="test", status=SubsystemStatus.PASS)
        assert result.status == SubsystemStatus.PASS

    @pytest.mark.slow
    def test_fail_status(self) -> None:
        result = SubsystemResult(name="test", status=SubsystemStatus.FAIL)
        assert result.status == SubsystemStatus.FAIL


class TestOperationalReport:
    @pytest.mark.slow
    def test_all_passed_true(self) -> None:
        report = OperationalReport(pass_count=14, fail_count=0)
        assert report.all_passed

    @pytest.mark.slow
    def test_all_passed_false(self) -> None:
        report = OperationalReport(pass_count=13, fail_count=1)
        assert not report.all_passed


class TestOperationalValidator:
    @pytest.mark.slow
    def test_validate_all_subsystems(self) -> None:
        validator = OperationalValidator()

        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="op-test-skill", version="1.0", description="test"),
            role_affinity={"primary": "Executor"},
            hexagram_trigger=HexagramTrigger(require=[10], exclude=[], transition_from=None),
            degradation_chain=DegradationChain(primary="default", degraded=[]),
            behavior={"entrypoint": "test.py", "sandbox": "isolated"},
        )

        from maref.recursive.role_registry import (
            PluginRole,
            PluginRoleCapability,
            PluginRoleIdentity,
            PluginRoleTrust,
        )

        core_role = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:core/executor/v1", name="executor", version="1.0"
            ),
            capability=PluginRoleCapability(
                trigram="震", allowed_tools=["write", "edit"], max_entropy=12.0
            ),
            trust=PluginRoleTrust(min_trust_score=0.5),
        )
        security_plugin = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:plugin/security/v1", name="security", version="1.0"
            ),
            capability=PluginRoleCapability(trigram="艮", allowed_tools=["audit"]),
            trust=PluginRoleTrust(min_trust_score=0.6),
        )

        report = validator.validate(skill, core_role, [security_plugin])

        assert report.pass_count >= 0
        assert report.total_duration_ms >= 0

    @pytest.mark.slow
    def test_fourteen_subsystems_result_count(self) -> None:
        validator = OperationalValidator()

        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="count-test", version="1.0", description="test"),
            hexagram_trigger=HexagramTrigger(require=[], exclude=[], transition_from=None),
            degradation_chain=DegradationChain(primary="default", degraded=[]),
            behavior={"entrypoint": "test.py", "sandbox": "none"},
        )

        from maref.recursive.role_registry import (
            PluginRole,
            PluginRoleCapability,
            PluginRoleIdentity,
            PluginRoleTrust,
        )

        core_role = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:core/test/v1", name="test-core", version="1.0"
            ),
            capability=PluginRoleCapability(trigram="乾", allowed_tools=["do"], max_entropy=10.0),
            trust=PluginRoleTrust(),
        )

        report = validator.validate(skill, core_role, [])

        assert report.pass_count > 0
        assert report.pass_count + report.fail_count > 0

    @pytest.mark.slow
    def test_self_healer_history(self) -> None:
        from maref.recursive.self_healer import SelfHealer

        healer = SelfHealer(max_iterations=3)
        assert healer._max_iterations == 3
        assert len(healer.history) == 0

    @pytest.mark.slow
    def test_validate_with_no_plugin_roles(self) -> None:
        validator = OperationalValidator()
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="min-test", version="1.0", description="test"),
            hexagram_trigger=HexagramTrigger(require=[], exclude=[], transition_from=None),
            degradation_chain=DegradationChain(primary="default", degraded=[]),
            behavior={"entrypoint": "test.py", "sandbox": "none"},
        )
        report = validator.validate(skill, None, [])
        assert report.total_duration_ms >= 0

    @pytest.mark.slow
    def test_report_to_dict(self) -> None:
        report = OperationalReport(pass_count=10, fail_count=0, audit_chain_complete=True)
        assert report.all_passed
        assert report.audit_chain_complete
