# S1: 委托链追踪机制 — Implementation Notes

## Key Decisions
- **UUIDv7**: Chose UUIDv7 (time-ordered) over UUIDv4 for traceable ordering in audit logs
- **max_depth=5**: Conservative limit based on attack surface analysis; deeper chains exponentially increase blast radius
- **Frozen dataclass**: Ensures immutability after creation, preventing in-place tampering
- **Chain-based hashing**: Each delegation node hashes its predecessor, creating a verifiable audit trail

## Technical Details
- `DelegationChain.create(root_agent_id)` creates root node with depth=0
- `add_delegation(parent, child, capability)` validates capability propagation (ADMIN > DELEGATE > EXECUTE > WRITE > READ)
- `validate()` checks: depth limit, circular references, capability downgrade violations
- Chain hash computed via SHA-256 over serialized node list

## Known Limitations
- No cross-process chain verification (single process only)
- Capability granularity is coarse (5 levels); fine-grained RBAC deferred to v0.27
- No rate limiting on delegation creation (delegated to Zero Trust Gateway at S3)

## Integration Points
- Integrated with `MCPSecurityGate` for per-call delegation verification
- Feeds into `TrustBoundaryManager` for cross-domain risk scoring
- Exports to `AuditLogger` for complete delegation audit trail

## Test Coverage
- 10 unit tests covering: create, add, validate (depth/circular/capability), hash chain, edge cases
- Coverage: 95%+