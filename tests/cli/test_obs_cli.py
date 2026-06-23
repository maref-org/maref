from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from typer.testing import CliRunner

from maref_lite.obs_cli import obs_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _patch_console():
    with patch("maref_lite.obs_cli.console") as mock_console:
        yield mock_console


class TestObsStatus:
    def test_status_when_off(self):
        mock_client = MagicMock()
        mock_client.level.value = "off"
        mock_client.get_buffer_path.return_value = None
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["status"])
            assert result.exit_code == 0

    def test_status_when_on_no_path(self):
        mock_client = MagicMock()
        mock_client.level.value = "basic"
        mock_client.get_buffer_path.return_value = None
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["status"])
            assert result.exit_code == 0

    def test_status_with_path_and_counts(self, tmp_path):
        buf_path = tmp_path / "obs_buffer"
        buf_path.write_text("test data")
        mock_client = MagicMock()
        mock_client.level.value = "standard"
        mock_client.get_buffer_path.return_value = buf_path
        mock_client.count_events.return_value = {"gov:transition": 5, "gov:decision": 3}
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["status"])
            assert result.exit_code == 0

    def test_status_with_path_no_counts(self, tmp_path):
        buf_path = tmp_path / "obs_buffer"
        buf_path.write_text("test")
        mock_client = MagicMock()
        mock_client.level.value = "standard"
        mock_client.get_buffer_path.return_value = buf_path
        mock_client.count_events.return_value = {}
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["status"])
            assert result.exit_code == 0


class TestObsShow:
    def test_show_no_events(self):
        mock_client = MagicMock()
        mock_client.get_all_events.return_value = []
        mock_client.level.value = "basic"
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["show"])
            assert result.exit_code == 0

    def test_show_with_events(self):
        mock_client = MagicMock()
        mock_client.get_all_events.return_value = [
            {"event_sequence": 1, "timestamp": 1000000, "event_type": "gov:transition", "metadata": {"from": "A", "to": "B"}},
            {"event_sequence": 2, "timestamp": 1000010, "event_type": "gov:decision", "metadata": {"action": "test"}},
        ]
        mock_client.level.value = "basic"
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["show"])
            assert result.exit_code == 0

    def test_show_filtered_by_type(self):
        mock_client = MagicMock()
        mock_client.get_all_events.return_value = [
            {"event_sequence": 1, "timestamp": 1000000, "event_type": "gov:transition", "metadata": {}},
            {"event_sequence": 2, "timestamp": 1000010, "event_type": "gov:decision", "metadata": {}},
        ]
        mock_client.level.value = "basic"
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["show", "--type", "gov:decision"])
            assert result.exit_code == 0

    def test_show_custom_last_count(self):
        mock_client = MagicMock()
        mock_client.get_all_events.return_value = [
            {"event_sequence": i, "timestamp": float(i), "event_type": "gov:transition", "metadata": {}}
            for i in range(10)
        ]
        mock_client.level.value = "basic"
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["show", "--last", "3"])
            assert result.exit_code == 0

    def test_show_float_metadata(self):
        mock_client = MagicMock()
        mock_client.get_all_events.return_value = [
            {"event_sequence": 1, "timestamp": 1000000, "event_type": "gov:probe", "metadata": {"entropy": 2.5, "latency": 0.75}},
        ]
        mock_client.level.value = "basic"
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["show"])
            assert result.exit_code == 0


class TestObsLevel:
    def test_level_status(self):
        mock_client = MagicMock()
        mock_client.level.value = "standard"
        with patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client):
            result = runner.invoke(obs_app, ["level", "status"])
            assert result.exit_code == 0

    def test_level_invalid_exits(self):
        with patch("maref_lite.obs_cli.MarefObsClient.get_default") as mock_get:
            mock_client = MagicMock()
            mock_client.level.value = "standard"
            mock_get.return_value = mock_client
            result = runner.invoke(obs_app, ["level", "invalid_level"])
            assert result.exit_code == 1

    def test_level_set_basic(self):
        mock_client = MagicMock()
        mock_client.level.value = "basic"
        with (
            patch("maref_lite.obs_cli.MarefObsClient.get_default", return_value=mock_client),
            patch("maref_lite.obs_cli.TelemetryLevel.from_env") as mock_from_env,
        ):
            result = runner.invoke(obs_app, ["level", "basic"])
            assert result.exit_code == 0
            mock_from_env.assert_called_once_with("basic")
