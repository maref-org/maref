"""框架 3.0 停用安全管理编排（P3）测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from maref.lifecycle.decommission import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    Decommissioner,
    DecommissionStep,
)
from maref.recursive.agent_24_state_machine import AgentStateV3


class FakeStateMachine:
    def __init__(self) -> None:
        self.states: dict[str, AgentStateV3] = {}
        self.transitions: list[tuple[str, AgentStateV3]] = []

    def state_of(self, agent_id: str):
        return self.states.get(agent_id)

    def transition(self, agent_id: str, to_state: AgentStateV3):
        self.states[agent_id] = to_state
        self.transitions.append((agent_id, to_state))
        return SimpleNamespace(to_state=to_state)

    def force_transition(self, agent_id: str, to_state: AgentStateV3):
        return self.transition(agent_id, to_state)


class FakeGovernanceStateMachine:
    def __init__(self) -> None:
        self.halted = False
        self.reason = ""

    def force_halt(self, reason: str = "", actor: str = "") -> bool:
        self.halted = True
        self.reason = reason
        return True


class FakeIdentityService:
    def __init__(self) -> None:
        self.revoked: list[str] = []

    def revoke(self, did_string: str, reason: str = "", signer: str = ""):
        self.revoked.append(did_string)
        return {"revoked": True, "did": did_string}


class FakeCredentialManager:
    def __init__(self) -> None:
        self.revoked: list[str] = []

    def revoke(self, credential_id: str, reason: str = "") -> bool:
        self.revoked.append(credential_id)
        return True


class FakeAuthorizationRegistry:
    def __init__(self, auths: list[str]) -> None:
        self._auths = list(auths)
        self.revoked: list[str] = []

    def list_authorizations(self, agent_id: str) -> list[str]:
        return list(self._auths)

    def revoke(self, auth_id: str) -> bool:
        self.revoked.append(auth_id)
        return True


class FakeMemoryManager:
    def __init__(self) -> None:
        self.purged: list[str] = []

    def purge(self, memory_id: str) -> bool:
        self.purged.append(memory_id)
        return True


def _step(report, step: DecommissionStep):
    return next(s for s in report.steps if s.step is step)


class TestDryRun:
    def test_dry_run_no_side_effects(self, tmp_path):
        gsm = FakeGovernanceStateMachine()
        ident = FakeIdentityService()
        decom = Decommissioner(
            governance_state_machine=gsm,
            identity_service=ident,
            state_dir=tmp_path / "st",
        )
        report = decom.run("agent-x")
        assert not gsm.halted
        assert ident.revoked == []
        assert all(s.status != STATUS_FAIL for s in report.steps)
        assert any(s.status == STATUS_SKIP for s in report.steps)

    def test_dry_run_default(self):
        assert Decommissioner(state_dir="/tmp/unused").dry_run is True


class TestFullExecute:
    def test_all_steps_pass(self, tmp_path):
        sm = FakeStateMachine()
        gsm = FakeGovernanceStateMachine()
        ident = FakeIdentityService()
        cm = FakeCredentialManager()
        ar = FakeAuthorizationRegistry(["a1", "a2"])
        mem = FakeMemoryManager()
        resid = tmp_path / "resid.txt"
        resid.write_text("x")
        bkp = tmp_path / "bkp.txt"
        bkp.write_text("d")

        decom = Decommissioner(
            state_machine=sm,
            governance_state_machine=gsm,
            identity_service=ident,
            credential_manager=cm,
            credential_ids=["c1"],
            authorization_registry=ar,
            memory_manager=mem,
            memory_ids=["m1"],
            residual_paths=[str(resid)],
            backup_sources=[str(bkp)],
            state_dir=tmp_path / "st",
            dry_run=False,
        )
        report = decom.run("agent-x")

        assert report.ok
        assert all(s.status == STATUS_PASS for s in report.steps)
        assert sm.states["agent-x"] is AgentStateV3.TERMINATING
        assert gsm.halted and gsm.reason == "decommission:agent-x"
        assert ident.revoked == ["agent-x"]
        assert cm.revoked == ["c1"]
        assert ar.revoked == ["a1", "a2"]
        assert mem.purged == ["m1"]
        assert not resid.exists()

    def test_cleanup_failure_is_reported(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        decom = Decommissioner(
            residual_paths=[str(subdir)],
            state_dir=tmp_path / "st",
            dry_run=False,
        )
        report = decom.run("agent-x")
        assert not report.ok
        assert _step(report, DecommissionStep.CLEANUP).status == STATUS_FAIL


class TestMissingCollaborators:
    def test_absent_collaborators_are_skipped(self, tmp_path):
        decom = Decommissioner(state_dir=tmp_path / "st", dry_run=False)
        report = decom.run("agent-x")
        assert all(s.status == STATUS_SKIP for s in report.steps)
        assert report.ok  # skip 不算失败


class TestIdempotency:
    def test_second_run_resumes(self, tmp_path):
        resid = tmp_path / "r.txt"
        resid.write_text("x")
        decom = Decommissioner(
            memory_manager=FakeMemoryManager(),
            memory_ids=["m1"],
            residual_paths=[str(resid)],
            state_dir=tmp_path / "st",
            dry_run=False,
        )
        first = decom.run("agent-x")
        assert first.ok
        # 二次运行：CLEANUP 已在状态文件中 → resume pass
        second = decom.run("agent-x")
        cleanup = _step(second, DecommissionStep.CLEANUP)
        assert cleanup.status == STATUS_PASS
        assert cleanup.evidence.get("resumed") is True

    def test_state_file_resume(self, tmp_path):
        st = tmp_path / "st"
        st.mkdir(parents=True)
        (st / "agent-x.json").write_text(
            json.dumps({"agent_id": "agent-x", "completed_steps": ["HALT"]}),
            encoding="utf-8",
        )
        decom = Decommissioner(state_dir=st, dry_run=False)
        report = decom.run("agent-x")
        halt = _step(report, DecommissionStep.HALT)
        assert halt.status == STATUS_PASS
        assert halt.evidence.get("resumed") is True


class TestBackup:
    def test_backup_sources_copied(self, tmp_path):
        src = tmp_path / "data.txt"
        src.write_text("hello")
        decom = Decommissioner(
            backup_sources=[str(src)],
            state_dir=tmp_path / "st",
            dry_run=False,
        )
        report = decom.run("agent-x")
        backup = _step(report, DecommissionStep.BACKUP)
        assert backup.status == STATUS_PASS
        assert (tmp_path / "st" / "backups" / "agent-x" / "data.txt").exists()


class TestReport:
    def test_report_and_audit_written(self, tmp_path):
        decom = Decommissioner(state_dir=tmp_path / "st", dry_run=False)
        report = decom.run("agent-x")
        assert report.to_dict()["agent_id"] == "agent-x"
        assert (tmp_path / "st" / "agent-x.report.json").exists()
        assert (tmp_path / "st" / "audit.jsonl").exists()

    def test_summary_contains_steps(self, tmp_path):
        report = Decommissioner(state_dir=tmp_path / "st", dry_run=False).run("agent-x")
        assert "agent-x" in report.summary()
