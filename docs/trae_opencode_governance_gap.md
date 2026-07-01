# MAREF Governance Gap: Trae/OpenCode/Cursor Integration

## Problem Statement

**Current State**: Trae, OpenCode, and Cursor are configured in MAREF's mapping but have **zero actual governance interception**.

**Root Cause**: MAREF governance requires calling-side integration. Only Claude Code has the `PreToolUse hook` mechanism that calls `sidecar/api/governance/check`. Other IDEs lack this integration point.

## Technical Analysis

### Current Architecture
```
Claude Code: IDE → PreToolUse hook → sidecar/api/governance/check → Governance Decision
Trae/OpenCode: IDE → Direct tool execution → No governance check
```

### Missing Components
1. **Calling-side integration**: No hook/plugin in Trae/OpenCode that calls MAREF
2. **Interception point**: No pre-execution check for tool calls
3. **Audit trail**: Zero governance audit entries for these agents

### Available Endpoints (Confirmed)
- ✅ `/api/health` - Sidecar health check
- ✅ `/api/v1/gaas/govern` - GaaS governance endpoint (requires API key)
- ✅ `/api/compliance/check-action` - Compliance endpoint
- ✅ `/api/v1/governance/state` - Governance state
- ❌ `/api/governance/check` - **Does not exist** (only in Claude Code hooks)

## Solution: MCP Guard Integration

### Overview
Implement MCP (Model Context Protocol) servers for each IDE that:
1. Intercept tool calls before execution
2. Call MAREF governance endpoints
3. Block/allow based on governance decision
4. Log all interactions for audit

### Implementation Plan

#### Phase 1: MCP Guard Prototype (Immediate)
```python
# scripts/trae_mcp_guard.py
# MCP server that intercepts Trae tool calls
# Configures via Trae's mcpServers configuration
```

#### Phase 2: OpenCode Auto-discovery (Immediate)
```json
// opencode.json in project root
{
  "mcpServers": {
    "maref-governance": {
      "command": "python3",
      "args": ["scripts/trae_mcp_guard.py"],
      "env": {"MAREF_AGENT_ID": "opencode"}
    }
  }
}
```

#### Phase 3: Enhanced Governance (Short-term)
- Add HITL integration for blocked actions
- Implement audit logging to MAREF sidecar
- Add telemetry for governance coverage

#### Phase 4: Native Integration (Long-term)
- Contribute MAREF SDK to Trae/OpenCode/Cursor
- Standardize governance interception API
- Enable cross-IDE governance policies

## Immediate Actions

### 1. Test Current Endpoints
```bash
cd /Volumes/1TB-M2/public/maref
python3 scripts/test_governance_endpoint.py
```

### 2. Create MCP Configuration
```bash
# For Trae
cp scripts/trae_mcp_config.json ~/.trae/mcp_config.json

# For OpenCode (auto-discovers from project root)
cp scripts/opencode_mcp_config.json ./opencode.json
```

### 3. Start Sidecar with GaaS
```bash
# Start sidecar (if not running)
python3 -m maref.sidecar.server
# or use maref-lite start
```

### 4. Test MCP Guard
```bash
# Test the MCP guard directly
MAREF_AGENT_ID=trae-cn python3 scripts/simple_mcp_guard.py
```

## Configuration Files

### Trae MCP Config (`~/.trae/mcp_config.json`)
```json
{
  "mcpServers": {
    "maref-governance": {
      "command": "python3",
      "args": ["/path/to/maref/scripts/trae_mcp_guard.py"],
      "env": {
        "MAREF_AGENT_ID": "trae-cn",
        "MAREF_SIDECAR_URL": "http://127.0.0.1:8000",
        "MAREF_API_KEY": "your-tenant-key"
      }
    }
  }
}
```

### OpenCode MCP Config (`./opencode.json`)
```json
{
  "mcpServers": {
    "maref-governance": {
      "command": "python3",
      "args": ["scripts/trae_mcp_guard.py"],
      "env": {
        "MAREF_AGENT_ID": "opencode",
        "MAREF_SIDECAR_URL": "http://127.0.0.1:8000",
        "MAREF_API_KEY": "your-tenant-key"
      }
    }
  }
}
```

## Governance Coverage Matrix

| Component | Status | Coverage | Audit Data | Priority |
|-----------|--------|----------|------------|----------|
| Claude Code | ✅ Complete | 100% | 62,800+ entries | - |
| Trae | ❌ None | 0% | 0 entries | High |
| Trae-CN | ❌ None | 0% | 0 entries | High |
| OpenCode | ❌ None | 0% | 0 entries | High |
| OpenCode-CN | ❌ None | 0% | 0 entries | High |
| Cursor | ❌ None | 0% | 0 entries | High |
| Athena | ⚠️ Partial | ~50% | Some entries | Medium |

## Success Metrics

### Phase 1 Success (Week 1)
- [ ] MCP guard intercepts tool calls
- [ ] Governance checks performed
- [ ] Audit entries created in sidecar
- [ ] Blocked actions logged

### Phase 2 Success (Week 2)
- [ ] HITL integration for sensitive actions
- [ ] Governance dashboard shows Trae/OpenCode activity
- [ ] Coverage > 80% of tool calls
- [ ] Performance impact < 100ms per check

### Phase 3 Success (Month 1)
- [ ] Native integration proposals to IDE teams
- [ ] Cross-IDE governance policy consistency
- [ ] Automated compliance reporting
- [ ] SLA monitoring for governance service

## Risk Mitigation

### Technical Risks
1. **Performance impact**: MCP adds latency
   - Mitigation: Async checks, caching, batch operations
2. **Single point of failure**: Sidecar dependency
   - Mitigation: Fallback modes, circuit breakers
3. **False positives**: Over-blocking legitimate actions
   - Mitigation: HITL escalation, policy tuning

### Operational Risks
1. **IDE compatibility**: MCP support varies
   - Mitigation: Multiple integration methods
2. **User experience**: Blocking disrupts workflow
   - Mitigation: Clear messaging, quick approvals
3. **Maintenance**: Keeping up with IDE updates
   - Mitigation: Standardized APIs, community contributions

## Next Steps

### Immediate (Today)
1. Run `test_governance_endpoint.py` to verify endpoints
2. Create MCP configs for Trae and OpenCode
3. Test simple MCP guard with echo commands

### Short-term (This Week)
1. Implement full MCP guard with actual governance checks
2. Add audit logging to MAREF sidecar
3. Create governance dashboard view for Trae/OpenCode
4. Document integration process for other IDEs

### Medium-term (This Month)
1. Contribute MAREF SDK to Trae/OpenCode projects
2. Implement file system monitoring as fallback
3. Create cross-IDE governance policy editor
4. Add performance monitoring and alerts

## References

1. [MAREF Architecture](/docs/architecture.md)
2. [GaaS API Documentation](/src/maref/gaas/api.py)
3. [MCP Specification](https://spec.modelcontextprotocol.io)
4. [Trae MCP Documentation](https://docs.trae.dev/mcp)
5. [OpenCode MCP Integration](https://opencode.ai/docs/mcp)