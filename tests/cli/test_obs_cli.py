from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from maref_lite.obs_cli import obs_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _patch_console():
    with patch("maref_lite.obs_cli.console") as mock_console:
        yield mock_console


class TestObsStatus:
    def test_status_prints_active(self):
        with patch("maref_lite.obs_cli.get_obs_status", return_value="active"):
            result = runner.invoke(obs_app, ["obs-status"])
            assert result.exit_code == 0

    def test_status_off(self):
        with patch("maref_lite.obs_cli.get_obs_status", return_value="off"):
            result = runner.invoke(obs_app, ["obs-status"])
            assert result.exit_code == 0

    def test_status_error_is_handled(self):
        with patch("maref_lite.obs_cli.get_obs_status", side_effect=RuntimeError("boom")):
            result = runner.invoke(obs_app, ["obs-status"])
            assert result.exit_code == 0


class TestObsShow:
    def test_show_no_events(self):
        with patch("maref_lite.obs_cli.get_obs_show", return_value=[]):
            result = runner.invoke(obs_app, ["obs-show"])
            assert result.exit_code == 0

    def test_show_with_events(self):
        items = [
            {"id": "obs-1", "size": 1024, "meta": {"event_type": "gov:transition"}},
            {"id": "obs-2", "size": 0, "meta": {}},
        ]
        with patch("maref_lite.obs_cli.get_obs_show", return_value=items):
            result = runner.invoke(obs_app, ["obs-show"])
            assert result.exit_code == 0

    def test_show_error_is_handled(self):
        with patch("maref_lite.obs_cli.get_obs_show", side_effect=RuntimeError("boom")):
            result = runner.invoke(obs_app, ["obs-show"])
            assert result.exit_code == 0


class TestObsLevel:
    def test_level_prints_result(self):
        with patch("maref_lite.obs_cli.get_obs_level", return_value="basic"):
            result = runner.invoke(obs_app, ["obs-level", "basic"])
            assert result.exit_code == 0

    def test_level_error_is_handled(self):
        with patch("maref_lite.obs_cli.get_obs_level", side_effect=RuntimeError("boom")):
            result = runner.invoke(obs_app, ["obs-level", "basic"])
            assert result.exit_code == 0
