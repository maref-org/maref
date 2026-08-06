from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from maref_lite.cli import app

runner = CliRunner()


class TestDesktopSetup:
    def test_setup_command_registered(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.stdout.lower() or "One-click" in result.stdout

    def test_setup_dry_run_returns_zero(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_no_model_flag(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--no-model", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_model_omni_parser(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--model", "omni_parser", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_model_none(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--model", "none", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_short_model_flag(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "-m", "none", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_upgrade_flag(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "--upgrade", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_short_upgrade_flag(self) -> None:
        result = runner.invoke(app, ["desktop", "setup", "-U", "--dry-run"])
        assert result.exit_code == 0

    def test_setup_with_setup_script_dry_run(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["desktop", "setup", "--dry-run"])
            assert result.exit_code == 0


class TestCLIHelpIncludesDesktopSetup:
    def test_desktop_subcommand_group_help(self) -> None:
        result = runner.invoke(app, ["desktop", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.stdout.lower()

    def test_global_help_mentions_desktop(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "desktop" in result.stdout.lower()
