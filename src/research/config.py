"""
MAREF Research Configuration Module

Centralized path and environment configuration for the autoresearch system.
All paths can be overridden via environment variables for portability.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Return the project root directory.

    Detects automatically from this file's location, or uses
    MAREF_PROJECT_ROOT environment variable if set.
    """
    env_root = os.environ.get("MAREF_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    # Auto-detect: config.py is at src/research/config.py
    return Path(__file__).parent.parent.parent


def get_mailbox_dir() -> Path:
    """Return the mailbox directory for report synchronization.

    Defaults to project_root/mailbox. Override with MAREF_MAILBOX_DIR
    environment variable or set MAREF_MAILBOX_DIR to the full path.
    """
    default_mailbox = str(get_project_root() / "mailbox")
    return Path(os.environ.get("MAREF_MAILBOX_DIR", default_mailbox))


def get_output_dir() -> Path:
    """Return the output directory for research reports.

    Priority:
    1. MAREF_OUTPUT_DIR environment variable
    2. Mailbox directory + /research_output
    3. Project root + /research_output
    """
    env_output = os.environ.get("MAREF_OUTPUT_DIR")
    if env_output:
        return Path(env_output)

    env_mailbox = os.environ.get("MAREF_MAILBOX_DIR")
    if env_mailbox:
        return Path(env_mailbox) / "research_output"

    return get_project_root() / "research_output"


def get_research_output_dir() -> Path:
    """Return the research output directory (alias for get_output_dir)."""
    return get_output_dir()


def get_log_dir() -> Path:
    """Return the log directory."""
    return get_output_dir() / "logs"


def get_knowledge_graph_path() -> Path:
    """Return the knowledge graph storage path.

    Defaults to system temp directory to avoid permission issues.
    """
    import tempfile

    return Path(tempfile.gettempdir()) / "maref-knowledge-graph.json"


# Environment variable names for reference
ENV_PROJECT_ROOT = "MAREF_PROJECT_ROOT"
ENV_MAILBOX_DIR = "MAREF_MAILBOX_DIR"
ENV_OUTPUT_DIR = "MAREF_OUTPUT_DIR"
ENV_RESEARCH_OUTPUT = "MAREF_RESEARCH_OUTPUT"
ENV_DASHSCOPE_API_KEY = "DASHSCOPE_API_KEY"

__all__ = [
    "get_project_root",
    "get_mailbox_dir",
    "get_output_dir",
    "get_research_output_dir",
    "get_log_dir",
    "get_knowledge_graph_path",
    "ENV_PROJECT_ROOT",
    "ENV_MAILBOX_DIR",
    "ENV_OUTPUT_DIR",
    "ENV_RESEARCH_OUTPUT",
    "ENV_DASHSCOPE_API_KEY",
]
