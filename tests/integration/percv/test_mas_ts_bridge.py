from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.mas_ts_bridge import MasTSBridge, MasTSError


class TestMasTSBridge:
    def test_init_defaults(self) -> None:
        bridge = MasTSBridge()
        assert "mas-ts" in bridge.mas_ts_root

    def test_init_with_custom_root(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/custom/path")
        assert bridge.mas_ts_root == "/custom/path"

    def test_fallback_after_failure(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/nonexistent")
        result = bridge.run_fast_screen()
        assert result["overall_score"] == 75.0
        assert result["level"] == "L0"
        assert bridge._fallback_active is True

    def test_reset_fallback(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/nonexistent")
        bridge.run_fast_screen()
        assert bridge._fallback_active is True
        bridge.reset_fallback()
        assert bridge._fallback_active is False

    def test_check_availability_false_when_no_module(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/nonexistent")
        assert bridge.check_availability() is False

    def test_parse_json_from_subprocess(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/tmp")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"overall_score": 92.5, "level": "L0", "details": {}}'
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch.object(bridge, "_resolve_default_card", return_value="/tmp/card.json"):
                result = bridge.run_fast_screen()

        assert result["overall_score"] == 92.5
        assert result["level"] == "L0"

    def test_subprocess_timeout_triggers_fallback(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/tmp")
        with patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="test", timeout=120)):
            result = bridge.run_fast_screen()
        assert result["overall_score"] == 75.0
        assert bridge._fallback_active is True

    def test_resolve_default_card_not_found(self) -> None:
        bridge = MasTSBridge(mas_ts_root="/tmp/nonexistent_xyz")
        with pytest.raises(MasTSError, match="No agent card found"):
            bridge._resolve_default_card()
