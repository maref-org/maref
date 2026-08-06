from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from maref.desktop.api_router import router


app = FastAPI()
app.include_router(router)
client = TestClient(app)
PREFIX = "/api/v1/desktop"


class TestApiRouter:
    def test_get_status(self) -> None:
        mock_controller = MagicMock()
        mock_controller.dry_run = True
        mock_controller._input.pyautogui_available = False
        mock_controller._parser.actual_backend = "mock"
        mock_controller._parser.backend_info = {"type": "mock"}
        mock_controller._parser.initialized = False
        mock_controller._execution_count = 0
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True

    def test_check_permissions(self) -> None:
        mock_controller = MagicMock()
        mock_controller.check_permissions.return_value = {"accessibility": True}
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/permissions")
        assert response.status_code == 200
        assert response.json()["permissions"]["accessibility"] is True

    def test_calibrate(self) -> None:
        mock_controller = MagicMock()
        mock_controller.calibrate.return_value = {"screen_width": 1920}
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/calibrate")
        assert response.status_code == 200

    def test_capture(self) -> None:
        mock_controller = MagicMock()
        mock_result = MagicMock()
        mock_result.width = 1920
        mock_result.height = 1080
        mock_result.capture_time_ms = 100.0
        mock_result.mode.value = "full_screen"
        mock_result.redactions_applied = 0
        mock_controller.capture.return_value = mock_result
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/capture")
        assert response.status_code == 200
        data = response.json()
        assert data["width"] == 1920

    def test_parse(self) -> None:
        mock_controller = MagicMock()
        mock_result = MagicMock()
        mock_result.screen_width = 1920
        mock_result.screen_height = 1080
        mock_result.elements = []
        mock_result.parse_time_ms = 50.0
        mock_result.model_name = ""
        mock_controller.parse.return_value = mock_result
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/parse")
        assert response.status_code == 200

    def test_get_ui_elements(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_ui_elements.return_value = [{"type": "button"}]
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/ui-elements")
        assert response.status_code == 200
        assert len(response.json()["elements"]) == 1

    def test_execute_operation(self) -> None:
        mock_controller = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.action_type = "click"
        mock_result.details = ""
        mock_result.duration_ms = 10.0
        mock_result.safety_decision.value = "allow"
        mock_result.error_message = ""
        mock_controller.execute_operation.return_value = mock_result
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(
                f"{PREFIX}/execute",
                json={"op_type": "click", "params": {"x": 100, "y": 200}},
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_execute_operation_invalid_type(self) -> None:
        with patch("maref.desktop.api_router.get_controller", return_value=MagicMock()):
            response = client.post(
                f"{PREFIX}/execute",
                json={"op_type": "invalid_op_type_xyz", "params": {}},
            )
        assert response.status_code == 400

    def test_execute_plan(self) -> None:
        mock_controller = MagicMock()
        mock_controller.dry_run = True
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True, "steps": []}
        mock_controller.execute_and_persist.return_value = mock_result
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(
                f"{PREFIX}/execute-plan",
                json={
                    "description": "test plan",
                    "steps": [{"op_type": "click", "params": {"x": 100}}],
                },
            )
        assert response.status_code == 200

    def test_execute_plan_invalid_op_type(self) -> None:
        mock_controller = MagicMock()
        mock_controller.dry_run = True
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(
                f"{PREFIX}/execute-plan",
                json={
                    "description": "test",
                    "steps": [{"op_type": "bad_op_type_xyz", "params": {}}],
                },
            )
        assert response.status_code == 400

    def test_get_history(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_history.return_value = [{"id": 1}]
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/history")
        assert response.status_code == 200
        assert len(response.json()["executions"]) == 1

    def test_get_execution_details_found(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_execution_details.return_value = {"id": 1}
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/history/1")
        assert response.status_code == 200

    def test_get_execution_details_not_found(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_execution_details.return_value = {"error": "not found"}
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/history/999")
        assert response.status_code == 404

    def test_get_policy_status(self) -> None:
        mock_controller = MagicMock()
        mock_controller._policy_tree.mode.value = "semi_auto"
        mock_controller._policy_tree.get_decision_log.return_value = []
        mock_controller._policy_tree.get_level_distribution.return_value = {}
        mock_controller.pending_hitl_decision = None
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/policy-status")
        assert response.status_code == 200
        assert response.json()["operation_mode"] == "semi_auto"

    def test_set_operation_mode(self) -> None:
        mock_controller = MagicMock()
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/set-mode", params={"mode": "full_auto"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_set_operation_mode_invalid(self) -> None:
        mock_controller = MagicMock()
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/set-mode", params={"mode": "invalid_mode"})
        assert response.status_code == 400

    def test_hitl_approve(self) -> None:
        mock_controller = MagicMock()
        mock_controller.approve_hitl.return_value = True
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/hitl/approve")
        assert response.status_code == 200
        assert response.json()["approved"] is True

    def test_hitl_reject(self) -> None:
        mock_controller = MagicMock()
        mock_controller.reject_hitl.return_value = True
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/hitl/reject")
        assert response.status_code == 200
        assert response.json()["rejected"] is True

    def test_get_decision_log(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_policy_decision_log.return_value = [{"verdict": "allow"}]
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/decision-log")
        assert response.status_code == 200
        assert len(response.json()["decisions"]) == 1

    def test_get_governance_status(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_governance_status.return_value = {"state": "healthy"}
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/governance-status")
        assert response.status_code == 200

    def test_set_governance_mode(self) -> None:
        mock_controller = MagicMock()
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.post(f"{PREFIX}/governance/mode", params={"mode": "degrade"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_get_governance_events(self) -> None:
        mock_controller = MagicMock()
        mock_controller.get_governance_events.return_value = [{"action": "circuit_break"}]
        with patch("maref.desktop.api_router.get_controller", return_value=mock_controller):
            response = client.get(f"{PREFIX}/governance-events")
        assert response.status_code == 200
        assert len(response.json()["events"]) == 1
