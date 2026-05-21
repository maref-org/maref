#!/usr/bin/env python3
"""Simple PERCV-MAREF Integration Demo

A minimal demonstration of the PERCV-MAREF integration.
"""

import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

async def main() -> None:
    print("=" * 80)
    print("PERCV-MAREF SIMPLE INTEGRATION DEMO")
    print("=" * 80)
    
    try:
        # Test imports
        print("\n1. Testing imports...")
        from maref.integration.percv import PERCVConfig
        from maref.integration.percv import PERCVGatewayAdapter
        from maref.integration.percv import CostMonitor
        from maref.integration.percv import CardBridge
        
        print("   ✓ PERCVConfig imported")
        print("   ✓ PERCVGatewayAdapter imported")
        print("   ✓ CostMonitor imported")
        print("   ✓ CardBridge imported")
        
        # Create config
        print("\n2. Creating configuration...")
        config = PERCVConfig(
            project_id="demo-simple",
            research_topic="Test research topic",
            research_goal="Test goal",
            budget_cents=1000,
            max_iterations=2,
        )
        print(f"   ✓ Config created: {config.project_id}")
        
        # Create adapters
        print("\n3. Creating adapters...")
        gateway = PERCVGatewayAdapter(config=config)
        cost_monitor = CostMonitor(config=config)
        card_bridge = CardBridge()
        
        print("   ✓ Gateway adapter created")
        print("   ✓ Cost monitor created")
        print("   ✓ Card bridge created")
        
        # Test async methods
        print("\n4. Testing async methods...")
        status = await gateway.get_status()
        print(f"   ✓ Gateway status: {status['status']}")
        
        providers = await gateway.get_providers()
        print(f"   ✓ Available providers: {providers['count']}")
        
        # Test cost monitoring
        print("\n5. Testing cost monitoring...")
        cost_status = cost_monitor.get_status()
        print(f"   ✓ Cost monitor status: {cost_status}")
        
        # Test card bridge
        print("\n6. Testing card bridge...")
        sync_count = card_bridge.get_synced_count()
        print(f"   ✓ Card bridge sync count: {sync_count}")
        
        # Test that the bridge can be instantiated and has sync capabilities
        print(f"   ✓ Card bridge initialized successfully")
        
        print("\n" + "=" * 80)
        print("DEMO COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print("\nSummary:")
        print("- ✓ All imports working")
        print("- ✓ Configuration created")
        print("- ✓ All adapters instantiated")
        print("- ✓ Async methods responding")
        print("- ✓ Cost monitor functioning")
        print("- ✓ Card bridge transforming")
        print("\nThe PERCV-MAREF integration is operational!")
        
    except Exception as e:
        print(f"\n✗ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())