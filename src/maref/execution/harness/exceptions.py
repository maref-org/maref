from __future__ import annotations


class HarnessError(Exception):
    """Base exception for all harness errors."""


class HarnessConfigError(HarnessError):
    """Invalid harness configuration."""


class HarnessExecutionError(HarnessError):
    """Error during harness execution."""


class HarnessAbortedError(HarnessError):
    """Harness execution was aborted (e.g. governance HALT)."""
