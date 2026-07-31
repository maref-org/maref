#!/usr/bin/env python3
"""Fill simulated human scores into rsi-correlation-data.yaml for pipeline testing."""

import os
import yaml
import random

random.seed(42)  # reproducible

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO_ROOT, "vault", "rsi-correlation-data.yaml")

with open(PATH) as f:
    data = yaml.safe_load(f)

dims = ["correctness", "testing", "code_quality", "security", "efficiency", "adoption"]

reviewers = {
    "reviewer_1": {"noise_std": 2, "bias": 0},   # very close to automated
    "reviewer_2": {"noise_std": 5, "bias": -2},  # slightly off
}

for key in sorted(data.keys()):
    entry = data[key]
    if not isinstance(entry, dict):
        continue
    auto = entry.get("automated_scores", {})
    for rev_name, cfg in reviewers.items():
        scores = {}
        for dim in dims:
            base = auto.get(dim, 50)
            noise = random.gauss(0, cfg["noise_std"])
            score = round(max(0, min(100, base + noise + cfg["bias"])), 1)
            scores[dim] = score
        entry["reviewer_scores"][rev_name] = scores

with open(PATH, "w") as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

print("✅ Simulated scores written.")
