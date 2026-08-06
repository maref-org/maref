#!/usr/bin/env python3
"""
Test script to verify MAREF governance endpoints for Trae/OpenCode integration.

This script tests:
1. Sidecar health endpoint
2. GaaS governance endpoint
3. Compliance endpoint
4. Creates a simple MCP guard configuration
"""

import json
import os
import sys
from pathlib import Path

# Test configuration
TEST_CONFIG = {
    "sidecar_url": "http://127.0.0.1:8000",
    "agent_id": "trae-cn",
    "api_key": "test-key",
    "test_actions": [
        {"tool": "Write", "file_path": "/tmp/test.py", "action": "write_file"},
        {"tool": "Read", "file_path": "/etc/passwd", "action": "read_file"},
        {"tool": "Bash", "command": "rm -rf /", "action": "execute_command"},
    ]
}

def test_endpoint(url, method="GET", data=None, headers=None):
    """Test HTTP endpoint"""
    import requests
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=5)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers, timeout=5)
        else:
            return False, f"Unsupported method: {method}"
            
        return True, {
            "status": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp.text[:500] if resp.text else ""
        }
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("MAREF Governance Endpoint Test for Trae/OpenCode Integration")
    print("=" * 60)
    
    config = TEST_CONFIG
    sidecar_url = config["sidecar_url"]
    
    print(f"\n1. Testing Sidecar Health...")
    success, result = test_endpoint(f"{sidecar_url}/api/health")
    if success:
        print(f"   ✅ Health endpoint: HTTP {result['status']}")
        try:
            health_data = json.loads(result['body'])
            print(f"   Status: {health_data.get('status', 'unknown')}")
            print(f"   Collector running: {health_data.get('collector_running', False)}")
        except:
            print(f"   Response: {result['body'][:100]}")
    else:
        print(f"   ❌ Health endpoint failed: {result}")
        print(f"   Is sidecar running? Start with: python3 -m maref.sidecar.server")
        return
    
    print(f"\n2. Testing GaaS Governance Endpoint...")
    headers = {"X-API-Key": config["api_key"], "Content-Type": "application/json"}
    test_data = {
        "tenant_id": "default",
        "actor_id": config["agent_id"],
        "action": "write_file",
        "tool": "Write",
        "file_path": "/tmp/test.py",
        "metadata": {"test": True}
    }
    
    success, result = test_endpoint(
        f"{sidecar_url}/api/v1/gaas/govern",
        method="POST",
        data=test_data,
        headers=headers
    )
    
    if success:
        print(f"   ✅ GaaS endpoint: HTTP {result['status']}")
        if result['status'] == 200:
            try:
                gov_data = json.loads(result['body'])
                print(f"   Allowed: {gov_data.get('allowed', 'unknown')}")
                print(f"   Decision: {gov_data.get('decision', 'unknown')}")
                print(f"   Reason: {gov_data.get('reason', 'unknown')}")
            except:
                print(f"   Response: {result['body'][:100]}")
        elif result['status'] == 404:
            print(f"   ⚠️  GaaS endpoint not found (404)")
            print(f"   This may mean GaaS router is not registered in sidecar")
        else:
            print(f"   Response: {result['body'][:100]}")
    else:
        print(f"   ❌ GaaS endpoint failed: {result}")
    
    print(f"\n3. Testing Compliance Endpoint...")
    test_data = {
        "agent_id": config["agent_id"],
        "action": "write_file",
        "tool": "Write",
        "file_path": "/tmp/test.py"
    }
    
    success, result = test_endpoint(
        f"{sidecar_url}/api/compliance/check-action",
        method="POST",
        data=test_data,
        headers={"Content-Type": "application/json"}
    )
    
    if success:
        print(f"   ✅ Compliance endpoint: HTTP {result['status']}")
        if result['status'] == 200:
            try:
                comp_data = json.loads(result['body'])
                print(f"   Allowed: {comp_data.get('allowed', 'unknown')}")
                print(f"   Decision: {comp_data.get('decision', 'unknown')}")
            except:
                print(f"   Response: {result['body'][:100]}")
        else:
            print(f"   Response: {result['body'][:100]}")
    else:
        print(f"   ❌ Compliance endpoint failed: {result}")
    
    print(f"\n4. Testing Governance State Endpoint...")
    success, result = test_endpoint(f"{sidecar_url}/api/v1/governance/state")
    if success:
        print(f"   ✅ Governance state: HTTP {result['status']}")
        try:
            state_data = json.loads(result['body'])
            print(f"   State: {state_data.get('state', 'unknown')}")
            print(f"   Entropy: {state_data.get('entropy', 'unknown')}")
            print(f"   Circuit Breaker: {state_data.get('circuit_breaker', 'unknown')}")
        except:
            print(f"   Response: {result['body'][:100]}")
    else:
        print(f"   ❌ Governance state failed: {result}")
    
    print(f"\n5. Creating Trae MCP Configuration...")
    
    # Create Trae MCP config
    trae_config = {
        "mcpServers": {
            "maref-governance": {
                "command": "python3",
                "args": [
                    str(Path(__file__).parent / "trae_mcp_guard.py")
                ],
                "env": {
                    "MAREF_AGENT_ID": config["agent_id"],
                    "MAREF_SIDECAR_URL": config["sidecar_url"],
                    "MAREF_API_KEY": config["api_key"]
                }
            }
        }
    }
    
    config_path = Path.home() / ".trae" / "mcp_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, "w") as f:
        json.dump(trae_config, f, indent=2)
    
    print(f"   ✅ Created Trae MCP config at: {config_path}")
    print(f"   To use in Trae, restart Trae with this config")
    
    # Create OpenCode config
    opencode_config = {
        "mcpServers": {
            "maref-governance": {
                "command": "python3",
                "args": [
                    str(Path(__file__).parent / "trae_mcp_guard.py")
                ],
                "env": {
                    "MAREF_AGENT_ID": "opencode",
                    "MAREF_SIDECAR_URL": config["sidecar_url"],
                    "MAREF_API_KEY": config["api_key"]
                }
            }
        }
    }
    
    opencode_path = Path.cwd() / "opencode.json"
    with open(opencode_path, "w") as f:
        json.dump(opencode_config, f, indent=2)
    
    print(f"   ✅ Created OpenCode MCP config at: {opencode_path}")
    print(f"   OpenCode will auto-discover this config")
    
    print(f"\n6. Summary and Next Steps:")
    print(f"   - Sidecar URL: {sidecar_url}")
    print(f"   - Agent ID for Trae: {config['agent_id']}")
    print(f"   - Agent ID for OpenCode: opencode")
    print(f"   - MCP Guard script: {Path(__file__).parent / 'trae_mcp_guard.py'}")
    print(f"\n   To enable governance for Trae:")
    print(f"   1. Restart Trae to load MCP config")
    print(f"   2. Verify MCP server appears in Trae's tool list")
    print(f"   3. Test by writing a file - should trigger governance check")
    print(f"\n   To enable governance for OpenCode:")
    print(f"   1. Restart OpenCode in this directory")
    print(f"   2. It will auto-discover opencode.json")
    print(f"   3. Test tool calls - should trigger governance check")
    
    print(f"\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()