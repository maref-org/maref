# @maref-org/mcp-governance

**MCP Governance Server** — wraps any MCP server with [MAREF](https://maref.cc) governance guardrails.

Intercepts tool calls (file writes, command execution) and checks them against the MAREF sidecar before forwarding to the backend MCP server.

## Features

- **Proxy architecture** — sits between MCP clients (Claude Code, VS Code, Cursor, etc.) and backend MCP servers
- **Write interception** — blocks or warns on file writes/edits/deletes based on MAREF policy
- **Execute interception** — blocks or warns on command execution based on MAREF policy
- **Read passthrough** — read-only operations pass through without governance checks
- **Three modes**: `enforcing` (block), `advisory` (warn + pass), `logging` (skip checks)
- **Decision caching** — in-memory cache with configurable TTL (allow: 30s, block: 60s)
- **Fail-closed** — when sidecar is unreachable in enforcing mode, all operations are blocked
- **Fail-open fallback** — when sidecar is unreachable in advisory/logging mode, operations pass through
- **HITL support** — human-in-the-loop decisions are never cached and always enforced
- **Introspection** — built-in `maref_governance_status` tool exposes runtime state

## Installation

```bash
npm install -g @maref-org/mcp-governance
```

Or run directly:

```bash
npx @maref-org/mcp-governance --config maref-mcp.json
```

## Quick Start

### 1. Create a config file (`maref-mcp.json`)

```json
{
  "governance": {
    "sidecarUrl": "http://localhost:8000",
    "mode": "enforcing",
    "failClosed": true,
    "cacheTtlMs": 30000,
    "cacheBlockTtlMs": 60000
  },
  "backend": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
  }
}
```

### 2. Run the server

```bash
maref-mcp --config maref-mcp.json
```

The server starts the backend MCP server as a subprocess, discovers its tools, and exposes them through a governance layer. Clients connect to this server instead of the backend directly.

## Configuration

### Configuration sources (in order of precedence)

| Priority | Source | Example |
|----------|--------|---------|
| 1 | CLI `--config` flag | `maref-mcp --config /path/to/config.json` |
| 2 | `MAREF_MCP_CONFIG` env var (file path) | `MAREF_MCP_CONFIG=/etc/maref.json maref-mcp` |
| 3 | `MAREF_MCP_CONFIG` env var (inline JSON) | `MAREF_MCP_CONFIG='{"governance":{...}}' maref-mcp` |
| 4 | `./maref-mcp.json` in current directory | auto-discovered |
| 5 | Environment variable overrides | see below |

### Governance options

| Option | Env var | Default | Description |
|--------|---------|---------|-------------|
| `sidecarUrl` | `MAREF_SIDECAR_URL` | `http://localhost:8000` | MAREF sidecar endpoint |
| `mode` | `MAREF_MODE` | `enforcing` | One of: `enforcing`, `advisory`, `logging` |
| `failClosed` | `MAREF_FAIL_CLOSED` | `true` | Block when sidecar is unreachable |
| `cacheTtlMs` | `MAREF_CACHE_TTL` | `30000` | Allow decision cache TTL (0 = disable) |
| `cacheBlockTtlMs` | `MAREF_CACHE_BLOCK_TTL` | `60000` | Block decision cache TTL (0 = disable) |

### Backend options

| Option | Env var | Description |
|--------|---------|-------------|
| `command` | `MAREF_BACKEND_COMMAND` | Backend MCP server command |
| `args` | `MAREF_BACKEND_ARGS` | Command arguments (JSON array) |
| `env` | — | Optional extra environment variables |

### Modes

| Mode | Behavior |
|------|----------|
| `enforcing` | Blocks operations that violate policy. With `failClosed: true`, also blocks when sidecar is unreachable. |
| `advisory` | Logs warnings for policy violations but allows all operations through. Useful for testing. |
| `logging` | Skips all governance checks entirely. Every tool call passes through immediately. |

## Architecture

```
┌──────────────┐     tools/list      ┌──────────────────┐     tools/list      ┌──────────────┐
│              │ ◄────────────────── │                  │ ◄────────────────── │              │
│  MCP Client  │     tools/call      │  MCP Governance  │     tools/call      │  Backend MCP │
│  (Claude     │ ──────────────────► │  Proxy Server    │ ──────────────────► │  Server      │
│   Code, VS   │                     │                  │                     │  (filesystem,│
│   Code, etc) │                     │  ┌────────────┐  │                     │   puppeteer, │
│              │                     │  │  MAREF     │  │                     │   etc.)      │
│              │                     │  │  Sidecar   │  │                     │              │
│              │                     │  │  Client    │  │                     │              │
└──────────────┘                     └──┴─────┬──────┴──┘                     └──────────────┘
                                              │
                                              ▼
                                     ┌──────────────────┐
                                     │  MAREF Sidecar   │
                                     │  (decision engine)│
                                     └──────────────────┘
```

The proxy:
1. Discovers tools from the backend MCP server at startup
2. Annotates all tools with `[Governed by MAREF]` in their description
3. Intercepts `tools/call` for write and execute operations
4. Checks with the MAREF sidecar before forwarding
5. Caches decisions to minimize latency
6. Adds a `maref_governance_status` introspection tool

## Tool Classification

Tools are classified into three categories:

- **Write**: operations that modify filesystem state (write, create, edit, delete, remove, patch, etc.)
- **Execute**: operations that run commands (exec, bash, shell, run, terminal, spawn, etc.)
- **Read**: everything else — passes through without governance checks

Classification uses both exact name matching and heuristic regex on normalized (underscore→space) tool names.

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Test
npm test

# Watch mode
npm run test:watch
```

## Client Configuration

### Claude Code

```json
{
  "mcpServers": {
    "my-governed-server": {
      "command": "maref-mcp",
      "args": ["--config", "/path/to/maref-mcp.json"]
    }
  }
}
```

### VS Code (Cline, Continue, etc.)

```json
{
  "mcpServers": {
    "my-governed-server": {
      "command": "maref-mcp",
      "args": ["--config", "/path/to/maref-mcp.json"]
    }
  }
}
```

## License

Apache-2.0
