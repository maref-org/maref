"""Pytest fixtures for longevity/regression testing."""

from __future__ import annotations

import random

import pytest


@pytest.fixture
def mock_rsi_history():
    """Simulate 24h RSI metric history (500 entries) for offline tests."""
    entries = []
    current = {"experiment_count": 100, "adoption_rate": 0.65, "avg_score": 75.0}
    for _ in range(500):
        current = {
            "experiment_count": current["experiment_count"] + 1,
            "adoption_rate": round(
                min(1.0, max(0.0, current["adoption_rate"] + 0.001 + random.uniform(-0.01, 0.01))),
                4,
            ),
            "avg_score": round(
                min(100.0, max(0.0, current["avg_score"] + 0.1 + random.uniform(-1.0, 1.0))), 2
            ),
        }
        entries.append(current)
    return entries


def pytest_addoption(parser):
    parser.addoption(
        "--run-longevity",
        action="store_true",
        default=False,
        help="Run full longevity test (default: quick smoke test only)",
    )
