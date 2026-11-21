"""MAREF conformance suite v0.1 — runtime-agnostic agent governance checks."""

from __future__ import annotations

from .controls import CONTROLS, Control, evaluate_controls
from .fixtures import build_trace, tamper
from .runner import (
    TraceError,
    load_trace,
    render_markdown,
    run,
    sign_report,
    verify_report,
    verify_report_dict,
)
from .types import ControlResult, Finding, Report, Status

__all__ = [
    "CONTROLS",
    "Control",
    "ControlResult",
    "Finding",
    "Report",
    "Status",
    "TraceError",
    "build_trace",
    "evaluate_controls",
    "load_trace",
    "render_markdown",
    "run",
    "sign_report",
    "tamper",
    "verify_report",
    "verify_report_dict",
]
