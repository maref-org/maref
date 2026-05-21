# S2: 信任边界标记 — Implementation Notes

## Key Decisions
- **Set-theory based domain model**: TrustDomain as mathematical set of AgentIds for formal verifiability
- **Policy enum (STRICT/PERMISSIVE/CUSTOM)**: Three-tier policy simplifies reasoning while covering most use cases
- **Static domain registration**: Domains registered at boot time; dynamic registration added in v0.26
- **BoundaryReport**: Snapshot-based reporting over streaming to reduce overhead

## Technical Details
- `TrustDomain(domain_id, agents, policy)` encapsulates domain membership
- `TrustBoundaryManager.is_cross_domain(source, target)` uses set membership test (O(1))
- Cross-domain calls flagged with `BoundaryEvent` containing risk_score (0.0-1.0)
- Strict→Permissive calls get minimum risk_score of 0.6 by default

## Known Limitations
- No support for overlapping domains (agent belongs to exactly one domain)
- Risk scoring heuristic-based; ML-driven scoring deferred to v0.28
- No real-time alerting on boundary violations (batched in BoundaryReport)

## Integration Points
- Called by `MCPSecurityGate` before allowing cross-domain MCP tool calls
- Feeds risk scores to `CircuitBreaker` for trip/cooldown decisions
- BoundaryEvent serialized to `AuditLogger` for compliance

## Test Coverage
- 8 unit tests: domain creation, membership, cross-domain detection, policy enforcement, report generation
- Coverage: 95%+