"""
macOS Accessibility API parser — reads UI element tree via JXA (osascript).

No GPU, no ML models, no new dependencies. Uses the native Accessibility
API that every Mac ships with.

Requires: macOS 12+, Accessibility permissions for Terminal/IDE.
"""

from __future__ import annotations

import json
import logging
import platform
import re
import subprocess
from typing import Any

from maref.desktop.screen_parser import (
    BoundingBox,
    InteractionType,
    ParsedUIElement,
    ScreenParseResult,
    UIElementType,
)

_logger = logging.getLogger(__name__)

# AX role → MAREF element type mapping
_AX_ROLE_MAP: dict[str, UIElementType] = {
    "AXButton": UIElementType.BUTTON,
    "AXTextField": UIElementType.TEXT_FIELD,
    "AXTextArea": UIElementType.TEXT_FIELD,
    "AXComboBox": UIElementType.DROPDOWN,
    "AXCheckBox": UIElementType.CHECKBOX,
    "AXRadioButton": UIElementType.RADIO,
    "AXPopUpButton": UIElementType.DROPDOWN,
    "AXMenuButton": UIElementType.MENU_ITEM,
    "AXLink": UIElementType.LINK,
    "AXStaticText": UIElementType.LABEL,
    "AXWindow": UIElementType.WINDOW,
    "AXDialog": UIElementType.DIALOG,
    "AXSheet": UIElementType.DIALOG,
    "AXImage": UIElementType.IMAGE,
    "AXScrollBar": UIElementType.SCROLL_BAR,
    "AXSlider": UIElementType.SLIDER,
    "AXTabGroup": UIElementType.TAB,
    "AXToolbar": UIElementType.UNKNOWN,
    "AXMenuBar": UIElementType.UNKNOWN,
    "AXMenuBarItem": UIElementType.MENU_ITEM,
    "AXMenuItem": UIElementType.MENU_ITEM,
    "AXOutline": UIElementType.UNKNOWN,
    "AXBrowser": UIElementType.UNKNOWN,
    "AXScrollArea": UIElementType.UNKNOWN,
    "AXGroup": UIElementType.UNKNOWN,
    "AXSplitGroup": UIElementType.UNKNOWN,
    "AXValueIndicator": UIElementType.UNKNOWN,
    "AXProgressIndicator": UIElementType.UNKNOWN,
    "AXRelevanceIndicator": UIElementType.UNKNOWN,
    "AXCell": UIElementType.UNKNOWN,
    "AXColumn": UIElementType.UNKNOWN,
    "AXRow": UIElementType.UNKNOWN,
    "AXHeader": UIElementType.UNKNOWN,
    "AXSortButton": UIElementType.BUTTON,
    "AXDisclosureTriangle": UIElementType.BUTTON,
    "AXPopover": UIElementType.UNKNOWN,
}

# Role → interaction type mapping
_ROLE_INTERACTIONS: dict[str, list[InteractionType]] = {
    "AXButton": [InteractionType.CLICKABLE],
    "AXTextField": [InteractionType.TYPABLE, InteractionType.CLICKABLE],
    "AXTextArea": [InteractionType.TYPABLE, InteractionType.CLICKABLE],
    "AXComboBox": [InteractionType.CLICKABLE, InteractionType.SELECTABLE],
    "AXCheckBox": [InteractionType.CLICKABLE],
    "AXRadioButton": [InteractionType.CLICKABLE],
    "AXPopUpButton": [InteractionType.CLICKABLE, InteractionType.SELECTABLE],
    "AXMenuButton": [InteractionType.CLICKABLE],
    "AXLink": [InteractionType.CLICKABLE],
    "AXSlider": [InteractionType.DRAGGABLE],
    "AXTabGroup": [InteractionType.CLICKABLE],
    "AXDisclosureTriangle": [InteractionType.CLICKABLE],
    "AXSortButton": [InteractionType.CLICKABLE],
    "AXMenuBarItem": [InteractionType.CLICKABLE],
    "AXMenuItem": [InteractionType.CLICKABLE],
    "AXScrollBar": [InteractionType.SCROLLABLE],
}

# Roles to skip (container elements)
_SKIP_ROLES = {
    "AXScrollArea",
    "AXGroup",
    "AXSplitGroup",
    "AXToolbar",
    "AXMenuBar",
    "AXOutline",
    "AXBrowser",
    "AXPopover",
}

# JXA script to get UI elements from frontmost window
# Note: el.position() and el.size() return array-like objects with [0],[1] keys
# (not named x/y or width/height properties)
_JXA_GET_ELEMENTS = """
function run() {
    var sys = Application("System Events");
    var appName = "%s";
    var proc;
    if (appName) {
        try {
            proc = sys.processes.whose({name: appName})[0];
        } catch(e) { return "[]"; }
    } else {
        proc = sys.processes.whose({frontmost: true})[0];
    }
    if (!proc) return "[]";
    var win = proc.windows[0];
    if (!win) return "[]";
    var elements = [];
    function walk(el, depth) {
        if (depth > %d) return;
        try {
            var role = String(el.role());
            if (role === "AXWindow") {
                var children = el.uiElements();
                for (var i = 0; i < children.length; i++) {
                    walk(children[i], depth + 1);
                }
                return;
            }
            var title = String(el.title());
            var desc = String(el.description());
            var value = String(el.value());
            var pos = el.position();
            var size = el.size();
            var enabled = true;
            try { enabled = el.enabled(); } catch(e) {}
            var focused = false;
            try { focused = el.focused(); } catch(e) {}
            var selected = false;
            try { selected = el.selected(); } catch(e) {}
            elements.push({
                role: role,
                title: title,
                description: desc,
                value: value,
                x: pos[0], y: pos[1],
                width: size[0], height: size[1],
                enabled: enabled,
                focused: focused,
                selected: selected
            });
            var children = el.uiElements();
            for (var i = 0; i < children.length; i++) {
                walk(children[i], depth + 1);
            }
        } catch(e) {}
    }
    walk(win, 0);
    return JSON.stringify(elements);
}
"""


def ax_role_to_element_type(role: str) -> UIElementType:
    """Map an AX role string to MAREF's UIElementType."""
    return _AX_ROLE_MAP.get(role, UIElementType.UNKNOWN)


class AccessibilityParser:
    """macOS Accessibility API parser via JXA (osascript -l JavaScript).

    Parses the UI element tree of the frontmost application window using
    macOS's built-in Accessibility API. No GPU, no ML models required.

    Usage:
        parser = AccessibilityParser()
        parser.initialize()
        result = parser.parse()
        for el in result.elements:
            print(el.text, el.element_type, el.bbox.center)
    """

    SUPPORTED_BACKENDS = ("accessibility",)

    def __init__(
        self,
        max_depth: int = 3,
    ) -> None:
        self._max_depth = max_depth
        self._initialized = False
        self._permission_granted = False
        self._platform = platform.system()

    @property
    def backend(self) -> str:
        return "accessibility"

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def permission_granted(self) -> bool:
        return self._permission_granted

    def check_permissions(self) -> bool:
        if self._platform != "Darwin":
            self._permission_granted = False
            return False
        try:
            import ApplicationServices

            trusted = ApplicationServices.AXIsProcessTrusted()
            self._permission_granted = bool(trusted)
            return self._permission_granted
        except ImportError:
            self._permission_granted = False
            return False

    def initialize(self) -> bool:
        """Check permissions and mark as ready."""
        if self._platform != "Darwin":
            self._initialized = False
            return False
        self.check_permissions()
        self._initialized = self._permission_granted
        return self._initialized

    def parse(
        self,
        target_app: str = "",
        screen_width: int = 0,
        screen_height: int = 0,
    ) -> ScreenParseResult:
        """Parse the UI element tree of the frontmost (or specified) app.

        Args:
            target_app: Bundle name (e.g. "Finder", "Safari"). Empty = frontmost.
            screen_width: Optional screen dimensions (auto-detected if 0).
            screen_height: Optional screen dimensions.

        Returns:
            ScreenParseResult with real UI elements from the Accessibility tree.
        """
        if not self._initialized:
            raise RuntimeError("AccessibilityParser not initialized. Call initialize() first.")

        import time

        t0 = time.time()

        raw_json = self._run_jxa(target_app)
        ax_elements: list[dict[str, Any]] = []
        try:
            ax_elements = json.loads(raw_json)
        except (json.JSONDecodeError, ValueError) as exc:
            _logger.warning("Failed to parse JXA JSON output: %s", exc)

        width, height = screen_width, screen_height
        if width <= 0 or height <= 0:
            try:
                import Quartz

                main_display = Quartz.CGMainDisplayID()
                width = int(Quartz.CGDisplayPixelsWide(main_display))
                height = int(Quartz.CGDisplayPixelsHigh(main_display))
            except (ImportError, Exception):
                width, height = 1920, 1080

        elements: list[ParsedUIElement] = []
        for item in ax_elements:
            role = item.get("role", "")
            title = item.get("title", "") or item.get("description", "") or item.get("value", "")
            title = title if title != "null" else ""
            is_enabled = item.get("enabled", True)
            if role == "null" or not is_enabled:
                continue
            if role in _SKIP_ROLES:
                continue
            x_raw: float | None = item.get("x")
            y_raw: float | None = item.get("y")
            w_raw: float | None = item.get("width")
            h_raw: float | None = item.get("height")
            if x_raw is None or y_raw is None or w_raw is None or h_raw is None:
                continue
            x = int(x_raw)
            y = int(y_raw)
            w = int(w_raw)
            h = int(h_raw)
            if w <= 0 or h <= 0:
                continue
            element_type = ax_role_to_element_type(role)
            if element_type == UIElementType.WINDOW:
                continue
            interactions = _ROLE_INTERACTIONS.get(role, [])
            elem_id = f"ax_{role}_{x}_{y}_{w}_{h}"
            elements.append(
                ParsedUIElement(
                    element_type=element_type,
                    bbox=BoundingBox(x=x, y=y, width=w, height=h),
                    text=title,
                    confidence=1.0,
                    interaction_types=interactions,
                    element_id=elem_id,
                    attributes={
                        "ax_role": role,
                        "enabled": is_enabled,
                        "focused": item.get("focused", False),
                        "source": "accessibility_api",
                    },
                )
            )

        elapsed = (time.time() - t0) * 1000
        return ScreenParseResult(
            screen_width=width,
            screen_height=height,
            elements=elements,
            parse_time_ms=elapsed,
            model_name="accessibility-api",
            raw_output={"element_count": len(ax_elements)},
        )

    def _run_jxa(self, target_app: str) -> str:
        """Execute JXA script and return JSON element array."""
        sanitized_app = re.sub(r"[^a-zA-Z0-9\- ]", "", target_app)
        script = _JXA_GET_ELEMENTS % (sanitized_app, self._max_depth)
        try:
            result = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            _logger.warning("osascript returned non-zero exit code %d", result.returncode)
            return "[]"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "[]"

    def benchmark(self, num_runs: int = 3) -> dict[str, Any]:
        """Run a quick benchmark: avg latency and element count."""
        if not self._initialized:
            raise RuntimeError("AccessibilityParser not initialized. Call initialize() first.")
        latencies: list[float] = []
        counts: list[int] = []
        for _ in range(num_runs):
            result = self.parse()
            latencies.append(result.parse_time_ms)
            counts.append(len(result.elements))
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        return {
            "backend": "accessibility",
            "num_runs": num_runs,
            "avg_latency_ms": round(avg_latency, 1),
            "avg_elements": sum(counts) / len(counts) if counts else 0,
        }
