# T1-T6: 分布式信任管理 — Implementation Notes

## Trust Model Design
- **Behavior-based**: Trust scores derived from agent behavior history, not static identity
- **Weighted consensus**: W_agent = 1/|N_i| * Σ T_ij (normalized trust propagation)
- **Decay function**: Older behavior has exponentially decreasing influence on current trust
- **Recovery path**: Low-trust agents can rebuild through consistent correct behavior

## Weighted Consensus Engine
- Implements mathematical formula with TLA+ formal verification
- Dynamic weight updates with Lyapunov stability guarantee
- Byzantine agent detection: >1/3 malicious → automatic isolation
- Cold-start: New agents start with neutral trust (0.5) and warm up through observation

## Trust Graph
- Directed weighted graph where nodes are agents and edges represent trust relationships
- Propagation algorithm with decay factor (λ=0.85) over k iterations
- Trust decay: inactive edges lose 5% trust per day
- Bottleneck detection: identifies single points of trust failure

## Trust API
- `trust_score(agent_id)` → float [0.0, 1.0]
- `get_trust_history(agent_id)` → list of (timestamp, score) tuples
- `set_trust(agent_id, score)` → admin-only direct trust override
- `propagate_trust()` → runs one propagation iteration

## ATP Integration
- Adapter layer for Lyrie.ai Agent Trust Protocol v1.0
- Identity certificates + delegation certificates
- Challenge-response authentication handshake
- Fallback to local trust model when ATP service unavailable

## Trust Visualization
- Cytoscape.js-compatible graph data export
- Node color encodes trust score (red=low, green=high)
- Edge thickness encodes trust weight
- Real-time trust score summary with agent count by tier

## Known Limitations
- Trust propagation is O(n²) in worst case; batch mode recommended for >1000 agents
- ATP integration requires network access for full functionality
- No cross-cluster trust federation (single trust domain)

## Test Coverage
- Trust model: 5 tests (formula correctness, edge cases)
- Trust graph: 8 tests (propagation, decay, bottleneck)
- Weighted consensus: 7 tests (Byzantine scenarios, stability)
- Trust API: 4 tests (CRUD operations)
- ATP integration: 18 tests (certificate lifecycle, handshake)
- Trust visualization: 3 tests (graph export format)
- Coverage: 80-95%