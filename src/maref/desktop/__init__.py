"""MAREF Desktop Agent — governance-wrapped desktop manipulation layer."""

import sys

from maref.desktop.accessibility_parser import AccessibilityParser
from maref.desktop.agent import DesktopAgent, DesktopAgentState
from maref.desktop.policy_decision_tree import PolicyDecisionTree
from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2

_DESKTOP_DEPS_MISSING: list[str] = []

try:
    from PIL import Image  # noqa: F401
except ImportError:
    _DESKTOP_DEPS_MISSING.append("Pillow")

try:
    import pyautogui  # noqa: F401
except Exception:  # headless CI: pyautogui→mouseinfo reads $DISPLAY → KeyError
    _DESKTOP_DEPS_MISSING.append("PyAutoGUI")

try:
    import playwright  # noqa: F401
except ImportError:
    _DESKTOP_DEPS_MISSING.append("playwright")

if _DESKTOP_DEPS_MISSING:
    _msg = (
        f"MAREF desktop optional dependencies missing: {', '.join(_DESKTOP_DEPS_MISSING)}. "
        f"Install with: pip install maref[desktop]"
    )
    if "pytest" not in sys.modules:
        import warnings

        warnings.warn(_msg, ImportWarning, stacklevel=2)

__all__ = [
    "AccessibilityParser",
    "DesktopAgent",
    "DesktopAgentState",
    "PolicyDecisionTree",
    "DesktopSafetyGateV2",
]
