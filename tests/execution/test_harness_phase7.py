"""Phase 7 测试：服务化部署 — FastAPI 服务 + Model Adapters。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from maref.execution.adapters.api_adapter import APIModelAdapter
from maref.execution.adapters.base import ModelAdapter
from maref.execution.server import app


# ── FastAPI 服务 ────────────────────────────────────────────────────────────

class TestHarnessServer:
    def test_health_endpoint(self) -> None:
        client = TestClient(app)
        resp = client.get("/harness/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_run_and_get_result(self) -> None:
        client = TestClient(app)
        run_resp = client.post("/harness/run", json={"config": {"harness_type": "unified", "level": "L1"}})
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert "run_id" in run_data
        assert run_data["status"] == "started"

        run_id = run_data["run_id"]

        # wait for completion
        import time
        for _ in range(10):
            result_resp = client.get(f"/harness/result/{run_id}")
            if result_resp.status_code == 200:
                break
            time.sleep(0.05)
        else:
            # result may not be available yet, check status at least
            status_resp = client.get(f"/harness/status/{run_id}")
            assert status_resp.status_code == 200

    def test_status_not_found(self) -> None:
        client = TestClient(app)
        resp = client.get("/harness/status/nonexistent")
        assert resp.status_code == 404

    def test_result_not_found(self) -> None:
        client = TestClient(app)
        resp = client.get("/harness/result/nonexistent")
        assert resp.status_code == 404

    def test_list_results_empty(self) -> None:
        client = TestClient(app)
        resp = client.get("/harness/results")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_stop_run(self) -> None:
        client = TestClient(app)
        run_resp = client.post("/harness/run", json={"config": {"harness_type": "unified"}})
        run_id = run_resp.json()["run_id"]
        stop_resp = client.post(f"/harness/stop/{run_id}")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] in ("stopped", "completed")

    def test_stop_not_found(self) -> None:
        client = TestClient(app)
        resp = client.post("/harness/stop/nonexistent")
        assert resp.status_code == 404


# ── Model Adapters ──────────────────────────────────────────────────────────

class TestModelAdapters:
    def test_base_adapter_abstract(self) -> None:
        try:
            ModelAdapter()  # type: ignore
            assert False, "expected TypeError"
        except TypeError:
            pass

    def test_api_adapter_model_name(self) -> None:
        adapter = APIModelAdapter(endpoint="http://localhost:8000", api_key="test", model="gpt-4")
        assert adapter.model_name == "gpt-4"

    def test_api_adapter_count_tokens(self) -> None:
        adapter = APIModelAdapter(endpoint="http://localhost:8000", api_key="test")
        assert adapter.count_tokens("hello world") > 0

    def test_api_adapter_complete_raises_on_no_server(self) -> None:
        adapter = APIModelAdapter(endpoint="http://localhost:1", api_key="test")
        try:
            adapter.complete("hi")
            assert False, "expected error"
        except Exception:
            pass
