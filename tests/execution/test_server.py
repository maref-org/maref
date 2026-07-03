from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from maref.execution.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHarnessServer:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/harness/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "runs" in data
        assert "completed" in data

    def test_run_harness(self, client: TestClient) -> None:
        resp = client.post("/harness/run", json={"config": {"harness_type": "unified", "level": "L1"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["run_id"].startswith("run_")

    def test_run_harness_default_config(self, client: TestClient) -> None:
        resp = client.post("/harness/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"

    def test_status_not_found(self, client: TestClient) -> None:
        resp = client.get("/harness/status/nonexistent")
        assert resp.status_code == 404

    def test_status_after_run(self, client: TestClient) -> None:
        run_resp = client.post("/harness/run", json={})
        run_id = run_resp.json()["run_id"]

        status_resp = client.get(f"/harness/status/{run_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["run_id"] == run_id
        assert data["config"] is not None

    def test_result_not_found(self, client: TestClient) -> None:
        resp = client.get("/harness/result/nonexistent")
        assert resp.status_code == 404

    def test_list_results(self, client: TestClient) -> None:
        resp = client.get("/harness/results")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_stop_not_found(self, client: TestClient) -> None:
        resp = client.post("/harness/stop/nonexistent")
        assert resp.status_code == 404

    def test_stop_run(self, client: TestClient) -> None:
        run_resp = client.post("/harness/run", json={})
        run_id = run_resp.json()["run_id"]

        stop_resp = client.post(f"/harness/stop/{run_id}")
        assert stop_resp.status_code == 200
        data = stop_resp.json()
        assert data["status"] in ("stopped", "completed")
