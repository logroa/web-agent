#!/usr/bin/env python3
"""
Quick local test script for the Web Agent
Validates basic functionality without requiring external sites
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from modules.orchestrator import AgentOrchestrator


async def test_basic_functionality():
    """Test basic agent functionality"""
    print("🧪 Testing Web Agent Basic Functionality")
    print("=" * 50)
    
    try:
        # Test initialization
        print("1. Testing agent initialization...")
        orchestrator = AgentOrchestrator()
        await orchestrator.initialize()
        print("✅ Agent initialized successfully")
        
        # Test configuration loading
        print("2. Testing configuration loading...")
        if orchestrator.settings:
            print(f"   ✅ Settings loaded: {orchestrator.settings.database.type} database")
        if orchestrator.sites:
            print(f"   ✅ Sites loaded: {len(orchestrator.sites.sites)} sites configured")
        
        # Test status
        print("3. Testing status retrieval...")
        status = await orchestrator.get_status()
        print(f"   ✅ Status retrieved: {status.get('status', 'unknown')}")
        
        # Test database operations
        print("4. Testing database operations...")
        if orchestrator.memory_manager:
            # Test creating a scrape session
            session_id = orchestrator.memory_manager.start_scrape_session("test_session")
            print(f"   ✅ Database session created: {session_id}")
            
            # Test completing the session
            orchestrator.memory_manager.complete_scrape_session(
                session_id, 
                success=True, 
                pages_scraped=1,
                files_found=0,
                files_downloaded=0
            )
            print("   ✅ Database session completed")
        
        print("\n🎉 All basic tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_with_test_sites():
    """Test with the test site configuration"""
    print("\n🧪 Testing with Test Sites")
    print("=" * 50)
    
    try:
        # Use test configuration
        orchestrator = AgentOrchestrator(config_dir="config")
        await orchestrator.initialize()
        
        # Check if test sites are available
        test_sites = [site for site in orchestrator.sites.sites if site.enabled]
        print(f"Found {len(test_sites)} enabled test sites:")
        
        for site in test_sites:
            print(f"   • {site.name}: {site.url}")
        
        if not test_sites:
            print("⚠️  No enabled test sites found")
            return False
        
        # Run a quick test with the first site
        print(f"\nTesting with site: {test_sites[0].name}")
        result = await orchestrator.run_single_cycle([test_sites[0].name])
        
        print(f"✅ Test completed:")
        print(f"   Sites processed: {result.get('processed_sites', 0)}")
        print(f"   Links found: {result.get('total_links_found', 0)}")
        print(f"   Downloads successful: {result.get('total_downloads_successful', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test with sites failed: {e}")
        return False


async def main():
    """Main test function"""
    print("🚀 Web Agent Local Test")
    print("=" * 50)
    
    # Test basic functionality
    basic_ok = await test_basic_functionality()
    
    if basic_ok:
        # Test with actual sites
        sites_ok = await test_with_test_sites()
        
        if sites_ok:
            print("\n🎉 All tests passed! Your Web Agent is ready to use.")
            print("\nNext steps:")
            print("1. Edit config/sites.yaml to add your target sites")
            print("2. Set API keys in .env for LLM features (optional)")
            print("3. Run: python main.py --sites 'Your Site Name'")
        else:
            print("\n⚠️  Basic functionality works, but site testing failed.")
            print("   Check your internet connection and site configurations.")
    else:
        print("\n❌ Basic functionality test failed.")
        print("   Check your setup and dependencies.")


if __name__ == "__main__":
    asyncio.run(main())
