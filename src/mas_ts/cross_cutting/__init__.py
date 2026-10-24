# SPDX-FileCopyrightText: 2026 maref-org
# SPDX-License-Identifier: Apache-2.0
"""Cross-cutting metrics for MAS-TS-001 v3.0-GA.

These metrics cut across all 5 domains and are evaluated independently:
  - Cost Efficiency: token consumption, execution cost, retry overhead
  - Consistency Index: cross-run behavioral consistency
  - Meta-Evaluation: evaluation framework self-assessment
"""

from mas_eval.cross_cutting.cost_efficiency import compute_cost_efficiency

__all__ = ["compute_cost_efficiency"]
