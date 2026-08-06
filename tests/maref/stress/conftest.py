"""Conftest for stress module tests - patches missing dependencies."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

sqi_mock = MagicMock()
sqi_mock.ServiceQualityIndex = MagicMock
sqi_mock.SQIDimension = MagicMock
sqi_mock.SQIReport = MagicMock
sys.modules["maref.stress.sqi"] = sqi_mock

sqi_convergence_mock = MagicMock()
sqi_convergence_mock.SQIConvergenceTracker = MagicMock
sys.modules["maref.stress.sqi_convergence"] = sqi_convergence_mock
