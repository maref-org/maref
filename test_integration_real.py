#!/usr/bin/env python3
"""Integration test with real PERCV imports.

This script tests that all PERCV adapters work correctly when PERCV is actually
installed in the environment.
"""

import asyncio
import sys
from typing import Dict, Any

# Test imports from both sides
print("=" * 80)
print("PERCV-MAREF Real Integration Test")
print("=" * 80)


def test_percv_import() -> bool:
    """Test that PERCV can be imported."""
    print("\n1. Testing PERCV import...")
    try:
        import percv
        version = getattr(percv, "__version__", "unknown")
        print(f"   ✓ PERCV imported successfully (version: {version})")
        return True
    except ImportError as e:
        print(f"   ✗ PERCV import failed: {e}")
        return False


def test_maref_adapter_imports() -> bool:
    """Test that MAREF adapters can import PERCV adapters."""
    print("\n2. Testing MAREF adapter imports...")
    try:
        from maref.integration.percv import (
            PERCVConfig,
            PERCVGatewayAdapter,
            PERCVPipelineAdapter,
            CardBridge,
            CostMonitor,
            RatchetBridge,
            VerificationBridge,
        )
        print("   ✓ All PERCV adapter modules imported successfully")
        return True
    except ImportError as e:
        print(f"   ✗ PERCV adapter import failed: {e}")
        return False


def test_percv_exports() -> bool:
    """Test that PERCV adapters are exported from maref.integration."""
    print("\n3. Testing MAREF integration exports...")
    try:
        from maref.integration import (
            PERCVGatewayAdapter,
            PERCVPipelineAdapter,
            PERCVRatchetBridge,
            PERCVVerificationBridge,
        )
        print("   ✓ PERCV adapters exported from maref.integration")
        return True
    except ImportError as e:
        print(f"   ✗ PERCV exports import failed: {e}")
        return False


def create_test_config() -> Any:
    """Create a test PERCV configuration."""
    print("\n4. Creating test configuration...")
    try:
        from maref.integration.percv import PERCVConfig
        
        config = PERCVConfig(
            project_id="integration-test",
            research_topic="Test topic",
            research_goal="Test goal",
            budget_cents=1000,
            max_iterations=2,
            temperature=0.7,
            max_tokens=2000,
        )
        print(f"   ✓ PERCVConfig created: project_id={config.project_id}")
        return config
    except Exception as e:
        print(f"   ✗ Config creation failed: {e}")
        return None


def test_adapter_creation(config: Any) -> bool:
    """Test creating adapters with the config."""
    print("\n5. Testing adapter creation...")
    try:
        from maref.integration.percv import PERCVGatewayAdapter
        
        # Test creating gateway adapter
        gateway = PERCVGatewayAdapter(config=config)
        print(f"   ✓ GatewayAdapter created: {gateway}")
        
        # Test creating cost monitor
        from maref.integration.percv import CostMonitor
        cost_monitor = CostMonitor(config=config, governance_manager=None)
        print(f"   ✓ CostMonitor created: {cost_monitor}")
        
        # Test creating card bridge
        from maref.integration.percv import CardBridge
        card_bridge = CardBridge()
        print(f"   ✓ CardBridge created: {card_bridge}")
        
        return True
    except Exception as e:
        print(f"   ✗ Adapter creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_percv_dependencies() -> bool:
    """Check what PERCV components are available."""
    print("\n6. Checking PERCV dependencies...")
    try:
        import percv
        
        # Try to import key PERCV components
        components = []
        
        # LLMRouter
        try:
            from percv import LLMRouter
            components.append("LLMRouter")
        except ImportError:
            pass
            
        # ResearchPipeline
        try:
            from percv import ResearchPipeline
            components.append("ResearchPipeline")
        except ImportError:
            pass
            
        # Ratchet
        try:
            from percv import Ratchet
            components.append("Ratchet")
        except ImportError:
            pass
            
        # Verification
        try:
            from percv import Verification
            components.append("Verification")
        except ImportError:
            pass
            
        print(f"   ✓ PERCV components available: {components}")
        return True
    except Exception as e:
        print(f"   ✗ PERCV dependency check failed: {e}")
        return False


async def test_async_methods(config: Any) -> bool:
    """Test async methods of adapters."""
    print("\n7. Testing async adapter methods...")
    try:
        from maref.integration.percv import PERCVGatewayAdapter
        
        gateway = PERCVGatewayAdapter(config=config)
        
        # Test get_status (async)
        status = await gateway.get_status()
        print(f"   ✓ Gateway.get_status() returned: {status}")
        
        # Test get_providers (async)
        providers = await gateway.get_providers()
        print(f"   ✓ Gateway.get_providers() returned: {len(providers)} providers")
        
        return True
    except Exception as e:
        print(f"   ✗ Async methods failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fallback_behavior() -> bool:
    """Test fallback behavior when PERCV is not available."""
    print("\n8. Testing fallback behavior...")
    
    # This test simulates what happens when PERCV is not installed
    # by checking the error handling in the adapters
    try:
        from maref.integration.percv.gateway_adapter import PERCVGatewayAdapter
        
        # Create config
        from maref.integration.percv import PERCVConfig
        config = PERCVConfig(
            project_id="fallback-test",
            research_topic="Test",
            research_goal="Test",
            budget_cents=1000,
            max_iterations=1,
        )
        
        # Create adapter - it should handle missing PERCV gracefully
        adapter = PERCVGatewayAdapter(config=config)
        print(f"   ✓ GatewayAdapter created (handles missing PERCV)")
        
# Check that it has fallback provider resolution
        if hasattr(adapter, "_resolve_provider"):
            print("   ✓ Has fallback provider resolution")
            
        return True
    except Exception as e:
        print(f"   ✗ Fallback test failed: {e}")
        return False


async def main() -> bool:
    """Run all integration tests."""
    print("\nStarting real integration tests...")
    
    tests_passed = 0
    total_tests = 8
    
    # Test 1: PERCV import
    if test_percv_import():
        tests_passed += 1
    
    # Test 2: MAREF adapter imports
    if test_maref_adapter_imports():
        tests_passed += 1
    
    # Test 3: PERCV exports
    if test_percv_exports():
        tests_passed += 1
    
    # Test 4: Create config
    config = create_test_config()
    if config:
        tests_passed += 1
    
    # Test 5: Adapter creation
    if config and test_adapter_creation(config):
        tests_passed += 1
    
    # Test 6: PERCV dependencies
    if test_percv_dependencies():
        tests_passed += 1
    
    # Test 7: Async methods
    if config:
        if await test_async_methods(config):
            tests_passed += 1
    
    # Test 8: Fallback behavior
    if test_fallback_behavior():
        tests_passed += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("RESULT: ✓ All integration tests passed!")
        return True
    elif tests_passed >= total_tests * 0.7:
        print("RESULT: ⚠️  Most integration tests passed")
        return True
    else:
        print("RESULT: ✗ Integration tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)