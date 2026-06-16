# rounds.jsonl → SAEB Metrics Mapping

## Source: `/Volumes/1TB-M2/openclaw/vault/evolution/2026-06-07/rounds.jsonl`
- 601 rounds across 3 cycles (c1: 50, c2: 100, c3: ~451)
- Round 0 of each cycle has real data; subsequent rounds are zero-filled ticks
- `test_pass_rate`, `coverage_pct`, `entropy`, `transition_count`, `meta_stats`, `real_metrics` all null/empty

## Field Mapping

| rounds.jsonl      | SAEBMetrics            | Direction | Notes                                    |
|-------------------|------------------------|-----------|------------------------------------------|
| `timestamp`       | `timestamp`            | 1:1       | Unix epoch float                         |
| `round_num`       | `round`                | 1:1       | Round index                              |
| `cycle_id`        | `label` (partial)      | ≈1:1      | SAEB uses `{injection}:fix` pattern      |
| `fnr`             | `fnr`                  | 1:1       | Exact match                              |
| `fpr`             | —                      | → gap     | Not collected by SAEB (only FNR)         |
| `test_pass_rate`  | `test_pass_rate`       | 1:1       | rounds.jsonl is always `null`            |
| `coverage_pct`    | `line_coverage_pct`    | 1:1       | rounds.jsonl is always `null`            |
| —                 | `passed`               | ← gap     | Raw test count (not in historical data)  |
| —                 | `failed`               | ← gap     | Raw test count (not in historical data)  |
| —                 | `errors`               | ← gap     | Import/compilation errors (new in SAEB)  |
| —                 | `compilation_error_rate`| ← gap    | Novel SAEB metric                        |
| —                 | `unused_import_count`  | ← gap     | Novel SAEB metric                        |
| —                 | `lint_violation_count` | ← gap     | Novel SAEB metric                        |
| —                 | `dead_functions`       | ← gap     | Novel SAEB metric                        |
| `halt_reason`     | `acceptance`           | ≈1:1      | SAEB uses 3 bools instead of string      |
| `final_state`     | —                      | → gap     | Not preserved in SAEB                    |

## Summary

**SAEB is a strict superset** of the historical `rounds.jsonl` format. The 3 new dimensions not present in historical data are:

1. **Compilation Error Separation** → `errors` / `compilation_error_rate`
2. **Lint Integration** → `unused_import_count` / `lint_violation_count` / `dead_functions`
3. **Raw Counts** → `passed` / `failed` / `errors`

The historical data's `fpr`, `halt_reason`, `final_state` have no SAEB equivalent because SAEB focuses on agent-level code iteration quality rather than system-level governance state.

## Usage in MAREFSelfAdapter

The adapter does NOT consume `rounds.jsonl` — it **produces** equivalent data. SAEB's `run_saeb()` calls `agent.iterate()` → measures with `SAEBMetricsCollector` → appends to `SAEBResult.metrics`. The result can be exported as JSON that matches or exceeds the `rounds.jsonl` schema.
