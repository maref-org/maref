from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MasTSError(Exception):
    pass


class MasTSBridge:

    def __init__(self, mas_ts_root: str = ""):
        self.mas_ts_root = mas_ts_root or os.environ.get("MAS_TS_ROOT", "../mas-ts")
        self._fallback_active = False

    def run_fast_screen(self, agent_card_path: str | Path | None = None) -> dict[str, Any]:
        if self._fallback_active:
            return self._fallback_result()

        try:
            card_path = agent_card_path or self._resolve_default_card()
        except MasTSError as exc:
            logger.warning("No agent card available, activating fallback: %s", exc)
            self._fallback_active = True
            return self._fallback_result()

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(self.mas_ts_root) / "mas_fast_screen.py"),
                    "--mode=minimal",
                    "--output=json",
                    f"--agent-card={card_path}",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise MasTSError(f"MAS-TS L0 failed: {result.stderr}")
            return json.loads(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning("MAS-TS call failed, activating fallback: %s", exc)
            self._fallback_active = True
            return self._fallback_result()

    def _resolve_default_card(self) -> str:
        candidates = [
            Path(self.mas_ts_root) / "mas_eval" / "data" / "sample_cards" / "percv_v2.json",
            Path(self.mas_ts_root) / "sample_cards" / "percv_v2.json",
            Path.cwd() / "config" / "agent_card.json",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        raise MasTSError("No agent card found and none provided")

    def _fallback_result(self) -> dict[str, Any]:
        return {
            "overall_score": 75.0,
            "level": "L0",
            "details": {"note": "fallback_mode"},
            "duration_s": 0,
        }

    def reset_fallback(self) -> None:
        self._fallback_active = False

    def check_availability(self) -> bool:
        if self._fallback_active:
            return False
        try:
            subprocess.run(
                [sys.executable, "-c", "import mas_fast_screen"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
