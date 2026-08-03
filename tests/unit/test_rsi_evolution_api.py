"""P5.6 RSI evolution timeline API tests.

Validates that GET /api/v1/rsi/evolution-timeline returns DaySnapshot[]
mapped from docs/rsi/7d-stability-report.json.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> "object":
    monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "test-rsi-api")
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from sidecar.server import create_app

    app = create_app(MagicMock(), MagicMock(), allow_unauthenticated=True)
    return TestClient(app)


class TestEvolutionTimelineAPI:
    def test_returns_200(self, client: "object") -> None:
        response = client.get("/api/v1/rsi/evolution-timeline")
        assert response.status_code == 200

    def test_returns_list(self, client: "object") -> None:
        data = client.get("/api/v1/rsi/evolution-timeline").json()
        assert isinstance(data, list)

    def test_snapshot_structure(self, client: "object") -> None:
        data = client.get("/api/v1/rsi/evolution-timeline").json()
        if not data:
            pytest.skip("no 7d-stability-report.json in cwd")
        first = data[0]
        assert "day" in first
        assert "date" in first
        assert "avgScore" in first
        assert "adoptionRate" in first
        assert "selfHealCount" in first
        assert "selfHealSuccesses" in first
        assert "events" in first
        assert "dimensions" in first

    def test_events_have_valid_types(self, client: "object") -> None:
        data = client.get("/api/v1/rsi/evolution-timeline").json()
        if not data:
            pytest.skip("no report data")
        valid_types = {"heal", "alert", "version", "gate", "conflict"}
        for snapshot in data:
            for event in snapshot.get("events", []):
                assert event["type"] in valid_types

    def test_empty_when_report_missing(
        self, client: "object", tmp_path: "object", monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        data = client.get("/api/v1/rsi/evolution-timeline").json()
        assert data == []

    def test_seven_days_from_report(self, client: "object") -> None:
        data = client.get("/api/v1/rsi/evolution-timeline").json()
        if not data:
            pytest.skip("no report data")
        assert len(data) == 7
        assert data[0]["day"] == 1
        assert data[-1]["day"] == 7
