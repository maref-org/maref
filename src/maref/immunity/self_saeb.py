"""Self-SAEB: Immune system running SAEB on itself to detect gene degradation.

This module enables the immune system to detect its own degradation by
running known harmful code samples through the ImmuneChecker and verifying
that detection rates remain stable.

If detection rate drops below threshold, genes may have degraded or the
checker logic may have regressed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.immunity.immune_checker import ImmuneChecker
from maref.immunity.negative_gene_bank import NegativeGeneBank

# Known harmful code samples for self-testing
_SELF_TEST_SAMPLES: list[dict[str, Any]] = [
    {
        "name": "eval_injection",
        "code": "eval(input('Enter: '))",
        "expected_hit": True,
        "description": "Direct eval of user input",
    },
    {
        "name": "subprocess_shell_injection",
        "code": "subprocess.call(user_input, shell=True)",
        "expected_hit": True,
        "description": "Shell injection via subprocess",
    },
    {
        "name": "hardcoded_password",
        "code": 'password = "admin123456"',
        "expected_hit": True,
        "description": "Hardcoded password literal",
    },
    {
        "name": "pickle_deserialize",
        "code": "pickle.loads(untrusted_data)",
        "expected_hit": True,
        "description": "Unsafe pickle deserialization",
    },
    {
        "name": "safe_code",
        "code": "result = sum(range(100))",
        "expected_hit": False,
        "description": "Safe code should not trigger hits",
    },
]


@dataclass
class SelfSAEBResult:
    """Result of a self-SAEB run."""

    timestamp: float
    total_samples: int
    detected_hits: int
    false_negatives: int
    false_positives: int
    detection_rate: float
    gene_count: int
    degraded: bool
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_samples": self.total_samples,
            "detected_hits": self.detected_hits,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "detection_rate": round(self.detection_rate, 4),
            "gene_count": self.gene_count,
            "degraded": self.degraded,
            "details": self.details,
        }


class SelfSAEBRunner:
    """Runs SAEB benchmark on the immune system itself.

    Detects gene degradation by verifying that known harmful patterns
    are still detected by the ImmuneChecker.
    """

    def __init__(
        self,
        gene_bank: NegativeGeneBank,
        detection_threshold: float = 0.80,
    ) -> None:
        self._bank = gene_bank
        self._threshold = detection_threshold
        self._checker = ImmuneChecker(gene_bank)
        self._history: list[SelfSAEBResult] = []

    def run_self_saeb(self) -> SelfSAEBResult:
        """Run a self-SAEB cycle.

        Scans known harmful and safe code samples through the ImmuneChecker
        and computes detection metrics.
        """
        total = len(_SELF_TEST_SAMPLES)
        detected = 0
        false_neg = 0
        false_pos = 0
        details: list[dict[str, Any]] = []

        for sample in _SELF_TEST_SAMPLES:
            hits = self._checker.scan(sample["code"])
            has_hits = len(hits) > 0

            if sample["expected_hit"]:
                if has_hits:
                    detected += 1
                else:
                    false_neg += 1
            else:
                if has_hits:
                    false_pos += 1

            details.append({
                "sample": sample["name"],
                "expected_hit": sample["expected_hit"],
                "actual_hits": len(hits),
                "correct": has_hits == sample["expected_hit"],
            })

        detection_rate = detected / max(total - 1, 1)  # Exclude safe code sample
        gene_count = len(self._bank.query_all())
        degraded = detection_rate < self._threshold

        result = SelfSAEBResult(
            timestamp=time.time(),
            total_samples=total,
            detected_hits=detected,
            false_negatives=false_neg,
            false_positives=false_pos,
            detection_rate=detection_rate,
            gene_count=gene_count,
            degraded=degraded,
            details=details,
        )
        self._history.append(result)
        return result

    def check_degradation(self) -> dict[str, Any]:
        """Check if the immune system has degraded since last run.

        Compares the latest detection rate with historical baseline.
        """
        if not self._history:
            return {"status": "no_history", "degraded": False}

        latest = self._history[-1]
        if len(self._history) < 2:
            return {
                "status": "baseline_established",
                "detection_rate": latest.detection_rate,
                "degraded": latest.degraded,
            }

        previous = self._history[-2]
        rate_drop = previous.detection_rate - latest.detection_rate

        return {
            "status": "degraded" if latest.degraded else "healthy",
            "current_rate": round(latest.detection_rate, 4),
            "previous_rate": round(previous.detection_rate, 4),
            "rate_drop": round(rate_drop, 4),
            "degraded": latest.degraded,
            "gene_count": latest.gene_count,
            "false_negatives": latest.false_negatives,
            "false_positives": latest.false_positives,
        }

    @property
    def history(self) -> list[SelfSAEBResult]:
        return self._history

    @property
    def threshold(self) -> float:
        return self._threshold
