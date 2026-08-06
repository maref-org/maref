"""Pytest fixtures for longevity/regression testing."""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--run-longevity",
        action="store_true",
        default=False,
        help="Run full longevity test (default: quick smoke test only)",
    )
