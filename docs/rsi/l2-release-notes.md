# MAREF RSI v0.35.0-beta — L2 Release Notes

## Summary
RSI capability upgraded from L1 (91/100) to L2 conditional pass (79.5/100).

## New Components

### MAREF (Core Framework)
- **CrossImpactCircuitBreaker** (`src/maref/recursive/cross_impact_circuit_breaker.py`): Monitors cross-dimension correlations with automatic circuit breaking when negative impacts exceed threshold. 4-state machine: MONITORING → ALERTED → TRIPPED → RECOVERING.
- **EvolutionQualityGate L2 Scoring** (`src/maref/integration/test_platform/quality_gate.py`): 5-dimension quality scoring (`evaluate_l2()`) with per-dimension thresholds and cross-impact validation.
- **CrossDimensionalAnalyzer** (`src/maref/integration/percv/cross_dimensional_analyzer.py`): Sliding-window cross-effect detection (default 20-round window) with Pareto front computation.
- **ConstitutionGuard** (`src/maref/evolution/constitution_guard.py`): RSI constitutional redline guard, enforces RL-006/007 security policies.
- **TLA+ Cross-Dim Invariants** (`src/formal/MAREF_ConstitutionalRedLines.tla`): 4 new formal invariants (CD-001 through CD-004) verifying cross-dimension stability properties.
- **RSI Redlines RL-006/007** (`configs/rsi_redlines.yaml`): Cross-dimension security protections including correlation thresholds and max file modification limits.
- **RedBlue PHASE6_ATTACKS** (`src/maref/redblue/attack_vector.py` L579+, `src/maref/redblue/attack_executor.py`): Cross-dimensional adversarial attack scenarios (4 types) with dedicated executor.

### Analysis & Evaluation
- **Correlation Analysis** (`src/maref/evaluation/correlation_analysis.py`): Human-AI scoring correlation using Spearman rank coefficient, ready for human reviewer integration.
- **Human Correlation Protocol** (`docs/rsi/l2-human-correlation-protocol.md`): Complete protocol for human reviewer evaluation of improvement quality.

### GUI (Dashboard)
- **ParetoFrontChart** (`gui/src/components/views/ParetoFrontChart.tsx`): Multi-objective improvement space visualization with Pareto frontier rendering.
- **CrossImpactHeatmap** (`gui/src/components/views/CrossImpactHeatmap.tsx`): Cross-dimension correlation heatmap with color-coded impact visualization.
- **AdaptiveAllocationReport** (`gui/src/components/views/AdaptiveAllocationReport.tsx`): Improvement target allocation tracking with per-dimension spend analysis.
- **RsiDashboard** (`gui/src/components/views/RsiDashboard.tsx`): Composable dashboard integrating ParetoFrontChart, CrossImpactHeatmap, and AdaptiveAllocationReport.

### Testing & Automation
- **24h Longevity Framework** (`tests/longevity/test_24h_rsi_regression.py`): Long-duration regression testing framework with automated degradation detection and configurable check intervals.
- **Cross-Dim Invariant Tests** (`tests/formal/test_cross_dim_invariants.py`): 11 TLA+ verification tests covering cross-dimension formal invariants.
- **Longevity Runner** (`scripts/run_longevity.py`): CLI tool for unsupervised 24h runs with automatic reporting and degradation alerts.

## Test Stats
- Total new L2 tests: 220+
- All passing (ruff + mypy strict + pytest)
- GUI TypeScript compilation clean
- TLA+ invariants: 4/4 proven (CD-001~CD-004)

## Known Limitations

### Engineering Complete, Procedural Pending
1. **Human correlation (003)**: Protocol designed, code ready — needs 3+ human reviewers to execute evaluations
2. **24h stability (005)**: Framework ready, tests passing — needs unsupervised wall-clock 24h run

### Deferred to L3
3. **MetaRatchet recursion hardening**: MetaRatchetAuditor — deferred to P5.1
4. **SubgoalInterceptor**: Cascading subgoal rollback — deferred to P5.2
5. **TLA+ constitutional compliance**: Full constitution formal verification — deferred to P5.3
6. **7-day stability**: Extended from 24h to 168h — deferred to P5.4
7. **Self-healing RSI**: Automated recovery from degradation — deferred to P5.5
8. **Evolution timeline dashboard**: Historical evolution visualization — deferred to P5.6

### Post-L3 Planning
9. **Self-SAEB immunity**: Immunity system running SAEB on itself

## Next Milestone
**L3 Preparatory Engineering** — MetaRatchet hardening, SubgoalInterceptor cascading rollback, 7-day stability validation, and full TLA+ constitutional compliance.
