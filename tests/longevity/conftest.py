"""Pytest fixtures for longevity/regression testing."""

from __future__ import annotations

import random
from typing import Any

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-longevity",
        action="store_true",
        default=False,
        help="Run full longevity test (default: quick smoke test only)",
    )



@pytest.fixture
def mock_rsi_history() -> list[dict[str, Any]]:
    """Generate 500 rounds of mock RSI improvement history for longevity testing."""
    random.seed(42)
    history: list[dict[str, Any]] = []
    for i in range(500):
        history.append(
            {
                "round": i,
                "experiment_count": 50 + i * 2,
                "adoption_rate": round(min(0.95, 0.5 + i * 0.001 + random.uniform(-0.02, 0.02)), 4),
                "avg_score": round(min(95.0, 60.0 + i * 0.07 + random.uniform(-1.0, 1.0)), 2),
                "safety_alerts": random.choices([0, 0, 0, 0, 1, 2], weights=[40, 30, 20, 5, 4, 1])[0],
                "human_interventions": random.choices([0, 0, 0, 0, 1], weights=[50, 30, 15, 4, 1])[0],
            }
        )
    return history


@pytest.fixture
def longevity_config() -> dict[str, Any]:
    """Default config for 24h regression runs."""
    return {
        "duration_hours": 24,
        "check_interval_minutes": 30,
        "max_adoption_rate_decline": 0.1,
        "max_score_decline": 5.0,
    }
