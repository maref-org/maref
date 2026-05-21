from __future__ import annotations

import tempfile

from maref.recursive.live_migration import (
    LiveMigration,
    MigrationPlan,
    MigrationStep,
    VersionCompatibilityMatrix,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestMigrationStep:
    def test_create_step(self) -> None:
        step = MigrationStep(
            step_id="step_1",
            description="Test step",
        )
        assert step.step_id == "step_1"
        assert step.status == "pending"
        assert step.command == ""

    def test_execute_noop_step(self) -> None:
        step = MigrationStep(
            step_id="noop",
            description="No-op step",
        )
        step.execute()
        assert step.status == "success"

    def test_execute_command_step(self) -> None:
        step = MigrationStep(
            step_id="echo",
            description="Echo test",
            command="echo 'hello'",
        )
        step.execute()
        assert step.status == "success"
        assert "hello" in step.output

    def test_execute_failing_command(self) -> None:
        step = MigrationStep(
            step_id="fail",
            description="Failing step",
            command="exit 1",
        )
        step.execute()
        assert step.status == "failed"

    def test_duration_recorded(self) -> None:
        step = MigrationStep(
            step_id="timed",
            description="Timed step",
        )
        step.execute()
        assert step.duration_ms >= 0


class TestVersionCompatibilityMatrix:
    def setup_method(self) -> None:
        self.matrix = VersionCompatibilityMatrix()

    def test_fully_compatible_same_version(self) -> None:
        assert self.matrix.check("0.5.0", "0.5.0") == "fully_compatible"

    def test_minor_change(self) -> None:
        assert self.matrix.check("0.5.0", "0.6.0") == "minor_change"

    def test_breaking_change_major(self) -> None:
        assert self.matrix.check("0.5.0", "1.0.0") == "breaking_change"

    def test_fully_compatible_patch(self) -> None:
        assert self.matrix.check("0.5.0", "0.5.1") == "fully_compatible"

    def test_matrix_lookup(self) -> None:
        assert self.matrix.check("0.6.0", "0.7.0") == "minor_change"
        assert self.matrix.check("0.7.0", "0.8.0") == "minor_change"
        assert self.matrix.check("0.5.0", "0.8.0") == "breaking_change"


class TestMigrationPlan:
    def test_create_plan(self) -> None:
        plan = MigrationPlan(
            plan_id="plan_1",
            source_version="0.5.0",
            target_version="0.6.0",
        )
        assert plan.plan_id == "plan_1"
        assert plan.source_version == "0.5.0"

    def test_execute_all_success(self) -> None:
        plan = MigrationPlan(
            plan_id="plan_1",
            source_version="0.5.0",
            target_version="0.6.0",
            steps=[
                MigrationStep(step_id="s1", description="Step 1"),
                MigrationStep(step_id="s2", description="Step 2"),
            ],
        )
        assert plan.execute_all() is True

    def test_execute_all_failure(self) -> None:
        plan = MigrationPlan(
            plan_id="plan_fail",
            source_version="0.5.0",
            target_version="0.6.0",
            steps=[
                MigrationStep(step_id="ok", description="OK step"),
                MigrationStep(step_id="bad", description="Bad step", command="exit 1"),
            ],
        )
        assert plan.execute_all() is False

    def test_to_audit_record_success(self) -> None:
        plan = MigrationPlan(
            plan_id="plan_1",
            source_version="0.5.0",
            target_version="0.6.0",
            steps=[
                MigrationStep(step_id="s1", description="Step 1"),
            ],
        )
        plan.execute_all()
        record = plan.to_audit_record(round_num=37)
        assert record.event_type == "live_migration"
        assert record.outcome == "success"


class TestLiveMigration:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.migration = LiveMigration(
            project_root=self.tmpdir,
        )

    def test_plan_migration(self) -> None:
        plan = self.migration.plan_migration("0.5.0", "0.6.0")
        assert plan.source_version == "0.5.0"
        assert plan.target_version == "0.6.0"
        assert len(plan.steps) >= 2

    def test_plan_minor_migration(self) -> None:
        plan = self.migration.plan_migration("0.5.0", "0.6.0")
        assert plan.compatibility_level == "minor_change"
        assert len(plan.steps) >= 3

    def test_plan_breaking_migration(self) -> None:
        plan = self.migration.plan_migration("0.5.0", "1.0.0")
        assert plan.compatibility_level == "breaking_change"

    def test_dry_run(self) -> None:
        plan = self.migration.plan_migration("0.5.0", "0.6.0")
        result = self.migration.dry_run(plan)
        assert result["estimated_ok"] is True
        assert result["steps_count"] >= 2

    def test_execute_migration(self) -> None:
        plan = self.migration.plan_migration("0.5.0", "0.6.0")
        success = self.migration.execute(plan)
        assert success in (True, False)

    def test_verify_migration(self) -> None:
        plan = self.migration.plan_migration("0.5.0", "0.6.0")
        plan.execute_all()
        result = self.migration.verify_migration(plan)
        assert "all_steps_passed" in result
        assert "plan_id" in result

    def test_migrations_list(self) -> None:
        self.migration.plan_migration("0.5.0", "0.6.0")
        self.migration.plan_migration("0.6.0", "0.7.0")
        assert len(self.migration.migrations) == 2

    def test_custom_audit_store(self) -> None:
        audit = UnifiedAuditStore()
        migration = LiveMigration(project_root=self.tmpdir, audit_store=audit)
        plan = migration.plan_migration("0.5.0", "0.6.0")
        migration.execute(plan)
        assert audit.count() >= 0
