"""MAREF Drift Detection Benchmark — 10-class distribution shift scenarios.

Provides a reproducible benchmark suite for evaluating drift detection
effectiveness across common UI/OS drift patterns.

10 drift classes:
1. UI theme color change        (dark mode ↔ light mode)
2. App version layout update    (button repositioning)
3. New OS version               (system font/metrics change)
4. Resolution change            (scaling factor shift)
5. Language/locale switch       (text rendering differences)
6. Font rendering difference    (anti-aliasing/hinting)
7. Window size adjustment       (responsive layout drift)
8. Dark mode toggle             (contrast inversion)
9. New UI element addition      (novel button/field)
10. Element removal             (deprecated features)

Metrics: KL divergence, JS divergence, Hellinger distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DriftClass(str, Enum):
    THEME_COLOR = "theme_color"
    LAYOUT_UPDATE = "layout_update"
    OS_VERSION = "os_version"
    RESOLUTION = "resolution"
    LOCALE = "locale"
    FONT_RENDERING = "font_rendering"
    WINDOW_SIZE = "window_size"
    DARK_MODE = "dark_mode"
    NEW_ELEMENT = "new_element"
    ELEMENT_REMOVAL = "element_removal"


DRIFT_CLASS_DESCRIPTIONS: dict[DriftClass, str] = {
    DriftClass.THEME_COLOR: "UI accent color changes (system-wide or per-app)",
    DriftClass.LAYOUT_UPDATE: "App version upgrade repositions interactive elements",
    DriftClass.OS_VERSION: "OS major/minor update triggers system font/metric changes",
    DriftClass.RESOLUTION: "Display resolution or scaling factor changes",
    DriftClass.LOCALE: "Language/localization switch alters text content",
    DriftClass.FONT_RENDERING: "Font anti-aliasing, hinting, or face changes",
    DriftClass.WINDOW_SIZE: "Window resize causes responsive layout reflow",
    DriftClass.DARK_MODE: "Light/dark mode toggle inverts contrast ratios",
    DriftClass.NEW_ELEMENT: "New UI elements added (feature rollout)",
    DriftClass.ELEMENT_REMOVAL: "UI elements removed (feature deprecation)",
}


@dataclass
class DriftScenario:
    """A single drift benchmark scenario."""

    drift_class: DriftClass
    description: str
    baseline_distribution: dict[str, float]
    drifted_distribution: dict[str, float]
    expected_detected: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_class": self.drift_class.value,
            "description": self.description,
            "baseline_keys": list(self.baseline_distribution.keys()),
            "drifted_keys": list(self.drifted_distribution.keys()),
            "expected_detected": self.expected_detected,
            "metadata": self.metadata,
        }


@dataclass
class DriftResult:
    """Result of a single drift detection evaluation."""

    scenario: DriftScenario
    kl_divergence: float
    js_divergence: float
    hellinger_distance: float
    detected: bool
    f1_score: float
    precision: float = 0.0
    recall: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_class": self.scenario.drift_class.value,
            "kl": round(self.kl_divergence, 6),
            "js": round(self.js_divergence, 6),
            "hellinger": round(self.hellinger_distance, 6),
            "detected": self.detected,
            "f1": round(self.f1_score, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
        }


class DriftBenchmark:
    """Run drift detection benchmarks across 10 standard scenarios."""

    def __init__(self, threshold_kl: float = 0.1, threshold_js: float = 0.05) -> None:
        self._threshold_kl = threshold_kl
        self._threshold_js = threshold_js
        self._scenarios: list[DriftScenario] = []
        self._results: list[DriftResult] = []
        self._build_scenarios()

    @property
    def scenarios(self) -> list[DriftScenario]:
        return list(self._scenarios)

    @property
    def results(self) -> list[DriftResult]:
        return list(self._results)

    def _build_scenarios(self) -> None:
        """Build the 10 standard drift scenarios."""
        # 1. Theme color change
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.THEME_COLOR,
                description="System accent color changes from blue to orange",
                baseline_distribution={
                    "button_bg": 0.40,
                    "text_fg": 0.30,
                    "border": 0.20,
                    "highlight": 0.10,
                },
                drifted_distribution={
                    "button_bg": 0.10,
                    "text_fg": 0.30,
                    "border": 0.20,
                    "highlight": 0.40,
                },
                expected_detected=True,
                metadata={"from_color": "#007AFF", "to_color": "#FF9500"},
            )
        )
        # 2. Layout update
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.LAYOUT_UPDATE,
                description="Button moved from top-right to bottom-left",
                baseline_distribution={
                    "btn_1_x": 0.8,
                    "btn_1_y": 0.1,
                    "btn_2_x": 0.8,
                    "btn_2_y": 0.3,
                },
                drifted_distribution={
                    "btn_1_x": 0.1,
                    "btn_1_y": 0.8,
                    "btn_2_x": 0.1,
                    "btn_2_y": 0.9,
                },
                expected_detected=True,
                metadata={"app_version": "2.0", "element": "submit_button"},
            )
        )
        # 3. OS version
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.OS_VERSION,
                description="macOS upgrade changes system font metrics",
                baseline_distribution={"font_size": 0.5, "line_height": 0.3, "letter_spacing": 0.2},
                drifted_distribution={
                    "font_size": 0.35,
                    "line_height": 0.40,
                    "letter_spacing": 0.25,
                },
                expected_detected=True,
                metadata={"from_os": "macOS 14", "to_os": "macOS 15"},
            )
        )
        # 4. Resolution change
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.RESOLUTION,
                description="Display scaling changes from 1x to 2x",
                baseline_distribution={"element_w": 0.40, "element_h": 0.35, "spacing": 0.25},
                drifted_distribution={"element_w": 0.25, "element_h": 0.25, "spacing": 0.50},
                expected_detected=True,
                metadata={"from_scale": 1.0, "to_scale": 2.0},
            )
        )
        # 5. Locale change
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.LOCALE,
                description="Language switch from English to Japanese",
                baseline_distribution={
                    "text_len_short": 0.6,
                    "text_len_medium": 0.3,
                    "text_len_long": 0.1,
                },
                drifted_distribution={
                    "text_len_short": 0.3,
                    "text_len_medium": 0.5,
                    "text_len_long": 0.2,
                },
                expected_detected=True,
                metadata={"from_locale": "en-US", "to_locale": "ja-JP"},
            )
        )
        # 6. Font rendering
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.FONT_RENDERING,
                description="Anti-aliasing changed from subpixel to grayscale",
                baseline_distribution={
                    "edge_contrast": 0.5,
                    "fill_density": 0.3,
                    "blur_radius": 0.2,
                },
                drifted_distribution={
                    "edge_contrast": 0.3,
                    "fill_density": 0.4,
                    "blur_radius": 0.3,
                },
                expected_detected=True,
                metadata={"from_aa": "subpixel", "to_aa": "grayscale"},
            )
        )
        # 7. Window size
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.WINDOW_SIZE,
                description="Window resized from 1920x1080 to 1280x720",
                baseline_distribution={"sidebar": 0.25, "content": 0.60, "toolbar": 0.15},
                drifted_distribution={"sidebar": 0.35, "content": 0.45, "toolbar": 0.20},
                expected_detected=True,
                metadata={"from_size": "1920x1080", "to_size": "1280x720"},
            )
        )
        # 8. Dark mode
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.DARK_MODE,
                description="Light mode → dark mode toggle",
                baseline_distribution={
                    "bg_luminance": 0.8,
                    "fg_luminance": 0.1,
                    "accent_luminance": 0.1,
                },
                drifted_distribution={
                    "bg_luminance": 0.1,
                    "fg_luminance": 0.8,
                    "accent_luminance": 0.1,
                },
                expected_detected=True,
                metadata={"from_mode": "light", "to_mode": "dark"},
            )
        )
        # 9. New element
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.NEW_ELEMENT,
                description="New 'Share' button added to toolbar",
                baseline_distribution={"buttons": 0.4, "fields": 0.3, "labels": 0.2, "menus": 0.1},
                drifted_distribution={
                    "buttons": 0.45,
                    "fields": 0.25,
                    "labels": 0.15,
                    "menus": 0.1,
                    "share_btn": 0.05,
                },
                expected_detected=True,
                metadata={"new_element": "share_button"},
            )
        )
        # 10. Element removal
        self._scenarios.append(
            DriftScenario(
                drift_class=DriftClass.ELEMENT_REMOVAL,
                description="'Settings' tab removed from navigation",
                baseline_distribution={
                    "home": 0.3,
                    "settings": 0.25,
                    "profile": 0.25,
                    "about": 0.2,
                },
                drifted_distribution={"home": 0.4, "profile": 0.35, "about": 0.25},
                expected_detected=True,
                metadata={"removed_element": "settings_tab"},
            )
        )

    def run(self) -> list[DriftResult]:
        self._results = []
        for scenario in self._scenarios:
            result = self._evaluate_scenario(scenario)
            self._results.append(result)
        return self._results

    def _evaluate_scenario(self, scenario: DriftScenario) -> DriftResult:
        baseline = scenario.baseline_distribution
        drifted = scenario.drifted_distribution

        kl = _kl_divergence(baseline, drifted)
        js = _js_divergence(baseline, drifted)
        hd = _hellinger_distance(baseline, drifted)

        detected = (kl > self._threshold_kl) or (js > self._threshold_js)
        precision = 1.0 if detected == scenario.expected_detected else 0.0
        recall = 1.0 if detected else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return DriftResult(
            scenario=scenario,
            kl_divergence=kl,
            js_divergence=js,
            hellinger_distance=hd,
            detected=detected,
            f1_score=f1,
            precision=precision,
            recall=recall,
        )

    def summary(self) -> dict[str, Any]:
        if not self._results:
            self.run()

        detected_count = sum(1 for r in self._results if r.detected)
        avg_f1 = sum(r.f1_score for r in self._results) / len(self._results)

        per_class: dict[str, dict[str, float]] = {}
        for r in self._results:
            per_class[r.scenario.drift_class.value] = {
                "kl": r.kl_divergence,
                "js": r.js_divergence,
                "hellinger": r.hellinger_distance,
                "detected": r.detected,
            }

        return {
            "total_scenarios": len(self._results),
            "detected": detected_count,
            "detection_rate": detected_count / len(self._results),
            "avg_f1": round(avg_f1, 4),
            "threshold_kl": self._threshold_kl,
            "threshold_js": self._threshold_js,
            "per_class": per_class,
        }


# ── Divergence metrics ────────────────────────────────────────────────


def _kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Kullback-Leibler divergence D_KL(P || Q)."""
    all_keys = set(p.keys()) | set(q.keys())
    kl = 0.0
    for k in all_keys:
        pk = p.get(k, 1e-10)
        qk = q.get(k, 1e-10)
        if pk > 0:
            kl += pk * math.log(pk / qk)
    return kl


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence (symmetric, bounded [0, 1])."""
    all_keys = set(p.keys()) | set(q.keys())
    m: dict[str, float] = {}
    for k in all_keys:
        m[k] = 0.5 * (p.get(k, 0) + q.get(k, 0))

    js = 0.0
    for k in all_keys:
        pk = p.get(k, 1e-10)
        qk = q.get(k, 1e-10)
        mk = m.get(k, 1e-10)
        if pk > 0:
            js += 0.5 * pk * math.log(pk / mk)
        if qk > 0:
            js += 0.5 * qk * math.log(qk / mk)
    return js


def _hellinger_distance(p: dict[str, float], q: dict[str, float]) -> float:
    """Hellinger distance (bounded [0, 1])."""
    all_keys = set(p.keys()) | set(q.keys())
    total = 0.0
    for k in all_keys:
        pk = p.get(k, 0)
        qk = q.get(k, 0)
        total += (math.sqrt(pk) - math.sqrt(qk)) ** 2
    return math.sqrt(total) / math.sqrt(2)


def _cosine_similarity(p: dict[str, float], q: dict[str, float]) -> float:
    """Cosine similarity between two probability vectors."""
    all_keys = set(p.keys()) | set(q.keys())
    dot = sum(p.get(k, 0) * q.get(k, 0) for k in all_keys)
    norm_p = math.sqrt(sum(v**2 for v in p.values()))
    norm_q = math.sqrt(sum(v**2 for v in q.values()))
    if norm_p == 0 or norm_q == 0:
        return 0.0
    return dot / (norm_p * norm_q)
