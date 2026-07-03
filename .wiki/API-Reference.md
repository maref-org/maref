# API Reference

> Full API documentation: [`docs/api.md`](https://github.com/maref-org/maref/blob/main/docs/api.md)

## CLI (maref-lite)

| Command | Description |
|---------|-------------|
| `maref status` | Query governance state |
| `maref desktop demo` | Launch desktop agent demo |
| `maref serve --port 8000` | Start Sidecar service |
| `maref serve --port 8000 --gui` | Start with GUI |
| `maref percv rsi-report` | Generate RSI report |
| `maref percv vault-dashboard` | Generate EvolutionVault dashboard |

## REST API

All endpoints are available at `/api/v1/` prefix when the Sidecar is running.

### Health

```
GET /api/health
```

### MCP Protocol

```
GET  /api/mcp/.well-known
POST /api/mcp
```

### Immunity

```
GET /api/immunity/cooldown
GET /api/immunity/cooldown/summary
GET /api/immunity/genes
```

## Python Packages

### `maref.loop` — Loop Engineering (v0.36.0-rc)

| Class | Description |
|-------|-------------|
| `ConvergentLoop` | Monotonic convergence with Evaluator + CircuitBreaker |
| `ExploratoryLoop` | Diversity-driven exploration with time/token budgets |
| `InteractiveLoop` | Human-interactive with sentiment and repetition detection |
| `LoopGovernanceBridge` | Wraps any LoopBase with governance state machine |

### `maref.governance` — Governance Core

| Class | Description |
|-------|-------------|
| `GovernanceStateMachine` | 10-state Gray code state machine |
| `CircuitBreaker` | 3-failure auto-lock with HALT absorb state |
| `AuditLogger` | HMAC-signed audit trail |
| `VerifierRegistry` | Cross-validation registry |

### `maref.security` — Security Layer

| Class | Description |
|-------|-------------|
| `TrustBoundaryManager` | Cross-domain call authorization |
| `SafetyGateV2` | Core component protection |
| `Sanitizer` | Input/output encoding and validation |

### `src/sidecar` — Observation Sidecar

| Endpoint | Description |
|----------|-------------|
| `POST /api/mcp` | MCP JSON-RPC bridge |
| `GET /api/health` | Health check |
| `GET /api/mcp/.well-known` | MCP protocol discovery |

## Error Codes

See [`docs/error-codes.md`](https://github.com/maref-org/maref/blob/main/docs/error-codes.md) for the complete error code reference (20 codes E0000–E4002).
