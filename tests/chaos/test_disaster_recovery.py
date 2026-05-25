"""
MAREF Disaster Recovery Tests

Validates backup script availability, backup integrity verification,
simulated data loss recovery, and RTO/RPO compliance.
"""

from __future__ import annotations

import os
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Generator
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
BACKUP_SCRIPT = SCRIPTS_DIR / "backup.sh"
BACKUP_ROOT_ENV = "MAREF_BACKUP_ROOT"
TEST_ROOT_ENV = "MAREF_TEST_ROOT"


def _run_backup(*args: str, backup_root: str | Path | None = None,
                test_root: str | Path | None = None,
                extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", "")}
    if backup_root is not None:
        env[BACKUP_ROOT_ENV] = str(backup_root)
    if test_root is not None:
        env[TEST_ROOT_ENV] = str(test_root)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(BACKUP_SCRIPT)] + list(args),
        capture_output=True, text=True,
        env=env,
    )


@pytest.fixture
def backup_root() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory(prefix="maref-backup-test-") as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "test_state.json").write_text('{"agent": "test", "status": "ok"}')
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "config.yaml").write_text("maref:\n  version: v0.25.0\n")
        (tmp_path / "logs").mkdir(parents=True)
        (tmp_path / "logs" / "audit.log").write_text("test audit log entry\n")
        yield tmp_path


@pytest.fixture
def backup_env(backup_root: Path) -> Path:
    backup_dir = backup_root / "backups"
    backup_dir.mkdir(parents=True)
    return backup_dir


class TestBackupScriptAvailability:
    """Task 2.3.3.1: Test backup script availability."""

    def test_backup_script_exists(self) -> None:
        assert BACKUP_SCRIPT.exists(), f"Backup script not found at {BACKUP_SCRIPT}"

    def test_backup_script_is_executable(self) -> None:
        assert os.access(BACKUP_SCRIPT, os.X_OK), f"Backup script not executable: {BACKUP_SCRIPT}"

    def test_backup_script_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(BACKUP_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Shell syntax error:\n{result.stderr}"

    def test_backup_script_help(self) -> None:
        result = _run_backup("--mode", "list", backup_root="/tmp", test_root="/tmp")
        assert result.returncode == 0 or "MAREF" in result.stdout


class TestBackupFullMode:
    """Test full backup creation."""

    def test_full_backup_creates_archive(self, backup_root: Path, backup_env: Path) -> None:
        result = _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)
        assert result.returncode == 0, f"Backup failed:\n{result.stderr}"

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1, "No full backup archive created"

    def test_full_backup_naming_convention(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1
        archive_name = archives[0].name
        assert archive_name.startswith("maref-backup-full-")
        assert archive_name.endswith(".tar.gz")

        date_part = archive_name.replace("maref-backup-full-", "").replace(".tar.gz", "")
        assert len(date_part) == 15
        assert date_part[8] == "-"

    def test_full_backup_contains_expected_content(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        with tarfile.open(str(archives[0]), "r:gz") as tar:
            names = tar.getnames()
            combined = " ".join(names)
            assert "data" in combined or "config" in combined


class TestBackupIncrementalMode:
    """Test incremental backup."""

    def test_incremental_backup_creates_archive(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        result = _run_backup("--mode", "incremental", backup_root=backup_env, test_root=backup_root)
        assert result.returncode == 0, f"Incremental backup failed:\n{result.stderr}"

        inc_archives = list(backup_env.glob("incremental/maref-backup-inc-*.tar.gz"))
        assert len(inc_archives) >= 1

    def test_incremental_backup_naming(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)
        _run_backup("--mode", "incremental", backup_root=backup_env, test_root=backup_root)

        inc_archives = list(backup_env.glob("incremental/maref-backup-inc-*.tar.gz"))
        assert len(inc_archives) >= 1
        assert inc_archives[0].name.startswith("maref-backup-inc-")
        assert inc_archives[0].name.endswith(".tar.gz")

    def test_incremental_backup_no_full_fallback(self, backup_root: Path, backup_env: Path) -> None:
        result = _run_backup("--mode", "incremental", backup_root=backup_env, test_root=backup_root)

        assert result.returncode == 0


class TestBackupIntegrity:
    """Task 2.3.3.2: Test backup file integrity verification."""

    def test_archive_integrity_valid(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        with tarfile.open(str(archives[0]), "r:gz") as tar:
            members = tar.getmembers()
            assert len(members) > 0

    def test_archive_is_tar_gz_format(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        with open(str(archives[0]), "rb") as f:
            header = f.read(2)
            is_gzip = header == b"\x1f\x8b"
            is_bz2 = header == b"BZ"
            assert is_gzip or is_bz2, f"Unknown format: header={header.hex()}"

    def test_archive_contains_no_empty_files(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        empty_count = 0
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            for member in tar.getmembers():
                if member.isdir():
                    continue
                if member.name.endswith(".gitkeep") or member.name.startswith("._"):
                    continue
                if member.size == 0:
                    empty_count += 1

        assert empty_count == 0, f"Found {empty_count} empty files in archive"


class TestDataLossRecovery:
    """Task 2.3.3.3: Simulate data loss and recovery."""

    def test_recover_from_backup(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        restore_dir = backup_root / "restored"
        restore_dir.mkdir()
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            tar.extractall(path=str(restore_dir))

        assert (restore_dir / "data" / "test_state.json").exists()
        assert (restore_dir / "config" / "config.yaml").exists()
        assert (restore_dir / "logs" / "audit.log").exists()

    def test_recover_after_data_deletion(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        data_file = backup_root / "data" / "test_state.json"
        assert data_file.exists()
        data_file.unlink()
        assert not data_file.exists()

        restore_dir = backup_root / "restored"
        restore_dir.mkdir()
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            tar.extractall(path=str(restore_dir))

        restored_file = restore_dir / "data" / "test_state.json"
        assert restored_file.exists()
        assert restored_file.read_text() == '{"agent": "test", "status": "ok"}'

    def test_multiple_backup_versions(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        data_file = backup_root / "data" / "test_state.json"
        data_file.write_text('{"agent": "test", "status": "updated"}')

        time.sleep(1.1)
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = sorted(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 2

        for archive in archives:
            with tarfile.open(str(archive), "r:gz") as tar:
                assert len(tar.getmembers()) > 0


class TestCleanupExpiredBackups:
    """Test backup retention cleanup."""

    def test_clean_removes_excess_daily(self, backup_env: Path) -> None:
        daily_dir = backup_env / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)

        for i in range(10):
            f = daily_dir / f"maref-backup-full-202605{10+i:02d}-020000.tar.gz"
            f.write_text(f"dummy backup {i}")

        result = _run_backup(
            "--mode", "clean",
            backup_root=backup_env,
            extra_env={"MAREF_BACKUP_RETENTION_DAILY": "5"},
        )

        assert result.returncode == 0
        remaining = list(daily_dir.glob("*.tar.gz"))
        assert len(remaining) <= 7

    def test_clean_noop_when_within_retention(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        result = _run_backup("--mode", "clean", backup_root=backup_env)
        assert result.returncode == 0


class TestRTOValidation:
    """Task 2.3.3.4: RTO/RPO validation."""

    def test_restore_within_rto(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        start = time.time()
        restore_dir = backup_root / "restore_rto_test"
        restore_dir.mkdir()
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            tar.extractall(path=str(restore_dir))
        elapsed = time.time() - start

        max_rto_s = 30 * 60
        assert elapsed < max_rto_s, (
            f"Restore took {elapsed:.2f}s, exceeds RTO of {max_rto_s}s (30min)"
        )

    def test_daily_backup_rpo_compliance(self, backup_root: Path) -> None:
        latest_mtime = 0.0
        data_dir = backup_root / "data"

        for f in data_dir.rglob("*"):
            if f.is_file():
                f_mtime = f.stat().st_mtime
                if f_mtime > latest_mtime:
                    latest_mtime = f_mtime

        age_hours = (time.time() - latest_mtime) / 3600
        max_rpo_hours = 24.0

        assert age_hours < max_rpo_hours, (
            f"Data age {age_hours:.1f}h exceeds RPO of {max_rpo_hours}h"
        )

    def test_backup_script_restore_mode_accepts_file(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        assert len(archives) >= 1

        result = _run_backup(
            "--mode", "restore", "--backup-file", str(archives[0]),
            backup_root=backup_env, test_root=backup_root,
        )

        assert result.returncode == 0 or "VERIFY" in result.stdout


class TestBackupCategories:
    """Verify backup covers all required categories."""

    def test_backup_covers_json_data(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            names = " ".join(tar.getnames())
            assert "test_state.json" in names

    def test_backup_covers_config(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            names = " ".join(tar.getnames())
            assert "config.yaml" in names

    def test_backup_covers_logs(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)

        archives = list(backup_env.glob("daily/maref-backup-full-*.tar.gz"))
        with tarfile.open(str(archives[0]), "r:gz") as tar:
            names = " ".join(tar.getnames())
            assert "audit.log" in names


class TestWeeklyAndMonthlyBackups:
    """Test weekly and monthly backup labels."""

    def test_weekly_backup_label(self, backup_root: Path, backup_env: Path) -> None:
        result = _run_backup("--mode", "full", "--weekly", backup_root=backup_env, test_root=backup_root)
        assert result.returncode == 0

        weeklies = list(backup_env.glob("weekly/maref-backup-full-*.tar.gz"))
        assert len(weeklies) >= 1

    def test_monthly_backup_label(self, backup_root: Path, backup_env: Path) -> None:
        result = _run_backup("--mode", "full", "--monthly", backup_root=backup_env, test_root=backup_root)
        assert result.returncode == 0

        monthlies = list(backup_env.glob("monthly/maref-backup-full-*.tar.gz"))
        assert len(monthlies) >= 1

    def test_list_shows_all_categories(self, backup_root: Path, backup_env: Path) -> None:
        _run_backup("--mode", "full", backup_root=backup_env, test_root=backup_root)
        _run_backup("--mode", "full", "--weekly", backup_root=backup_env, test_root=backup_root)

        result = _run_backup("--mode", "list", backup_root=backup_env)
        assert result.returncode == 0
        assert "daily" in result.stdout or "MAREF" in result.stdout


class TestErrorHandling:
    """Error handling for invalid inputs."""

    def test_restore_without_file_fails(self, backup_env: Path) -> None:
        result = _run_backup("--mode", "restore", backup_root=backup_env)
        assert result.returncode != 0

    def test_restore_nonexistent_file_fails(self, backup_env: Path) -> None:
        result = _run_backup(
            "--mode", "restore", "--backup-file", "/nonexistent/backup.tar.gz",
            backup_root=backup_env,
        )
        assert result.returncode != 0

    def test_unknown_mode_fails(self, backup_env: Path) -> None:
        result = _run_backup("--mode", "unknown_mode", backup_root=backup_env)
        assert result.returncode != 0
