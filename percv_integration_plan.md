# PERCV-MAREF Full Integration Implementation Plan

## Goal
Complete the integration of PERCV as a research operation layer in MAREF with full "认知-治理" closed-loop functionality.

## Current State Assessment
- ✅ PERCV adapter code exists (`src/maref/integration/percv/`)
- ✅ Tests for adapter components exist (`tests/integration/percv/`)
- ❌ PERCV package not installed in MAREF environment
- ❌ Integration orchestration not implemented
- ❌ CLI commands/API endpoints missing
- ❌ Governance state machine integration not wired up
- ❌ End-to-end closed loop not verified

## Phase 1: Environment Setup
1. Install PERCV as editable package from local path
2. Add PERCV to MAREF's pyproject.toml optional dependencies
3. Verify PERCV import works with minimal example

## Phase 2: Integration Orchestration Layer
1. Create `percv_integration.py` main orchestration module
2. Wire up all adapter components (GatewayAdapter, PipelineAdapter, CardBridge, etc.)
3. Implement `PERCVResearchOrchestrator` class
4. Add health check and initialization methods

## Phase 3: CLI & API Integration
1. Add `percv` subcommand to MAREF CLI (`maref percv`)
2. Implement commands: `research-cycle`, `sync-cards`, `cost-report`, `verify`
3. Create API endpoints in sidecar for web UI integration
4. Add configuration management for PERCV settings

## Phase 4: Governance State Machine Integration
1. Create governance hooks for PERCV operations
2. Wire cost monitoring to MAREF circuit breaker
3. Implement approval workflows for research cycles
4. Add audit logging for all PERCV operations

## Phase 5: Closed-Loop Verification
1. Create end-to-end test scenario
2. Verify "cognitive loop" (PERCV research → MAREF governance → action)
3. Test error handling and recovery
4. Performance benchmarking

## Phase 6: Documentation & Examples
1. Update README with PERCV integration section
2. Create usage examples and tutorials
3. Document configuration options
4. Create troubleshooting guide

## Implementation Details

### PERCV Installation
```bash
# Install PERCV in editable mode
cd /Volumes/1TB-M2/autoresearch/percv
pip install -e .

# Or add to MAREF's pyproject.toml as optional dependency
# [project.optional-dependencies]
# percv = ["percv @ file:///Volumes/1TB-M2/autoresearch/percv"]
```

### Architecture Components
1. **Orchestrator** (`PERCVResearchOrchestrator`) - Main integration point
2. **Bridge Manager** - Manages all bridge components
3. **Governance Interface** - Connects to MAREF state machine
4. **CLI Handler** - User interface layer

### Key Integration Points
1. **LLM Gateway** → MAREF model routing
2. **Cost Tracking** → MAREF circuit breaker
3. **Research Cards** → MAREF knowledge graph
4. **Ratchet Loop** → MAREF MetaLearner
5. **Verification** → MAREF trust layer

## Success Criteria
- ✅ PERCV package importable in MAREF environment
- ✅ `maref percv research-cycle` command works
- ✅ Research cards sync to MAREF knowledge graph
- ✅ Cost monitoring feeds into governance
- ✅ End-to-end test passes
- ✅ Governance approvals work for research operations

## Risks & Mitigations
1. **PERCV API changes** - Use abstractions and dependency injection
2. **Performance overhead** - Profile and optimize critical paths
3. **Data consistency** - Implement transaction-like semantics for sync operations
4. **Error propagation** - Isolate PERCV failures from MAREF core

## Timeline
- Phase 1-2: Day 1
- Phase 3-4: Day 2
- Phase 5-6: Day 3

## Files to Create/Modify
1. `src/maref/integration/percv/orchestrator.py` - Main orchestration
2. `src/maref/cli/percv.py` - CLI commands
3. `src/maref/governance/percv_hooks.py` - Governance integration
4. `tests/integration/percv/test_orchestrator.py` - Integration tests
5. `examples/percv_integration.py` - Usage examples
6. `docs/percv-integration.md` - Documentation