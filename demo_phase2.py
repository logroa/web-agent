#!/usr/bin/env python3
"""
Phase 2 Demo Script
Demonstrates LLM-enhanced web scraping capabilities
"""

import asyncio
import os
from modules.orchestrator import AgentOrchestrator


async def demo_phase2():
    """Demonstrate Phase 2 LLM capabilities"""
    
    print("🤖 Web Agent Phase 2 Demo - LLM-Enhanced Reasoning")
    print("=" * 60)
    
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY not set. LLM features will be disabled.")
        print("   Set your API key: export OPENAI_API_KEY='your-key-here'")
        print()
    
    try:
        # Initialize orchestrator
        print("🔧 Initializing agent with LLM capabilities...")
        orchestrator = AgentOrchestrator()
        await orchestrator.initialize()
        
        # Show configuration
        print(f"✅ Agent initialized successfully!")
        print(f"   LLM Enabled: {orchestrator.settings.llm.enabled}")
        print(f"   LLM Provider: {orchestrator.settings.llm.provider}")
        print(f"   LLM Model: {orchestrator.settings.llm.model}")
        print()
        
        # Show enabled sites
        enabled_sites = [site for site in orchestrator.sites.sites if site.enabled]
        print(f"📋 Enabled Sites ({len(enabled_sites)}):")
        for site in enabled_sites:
            llm_status = "🧠 LLM" if site.llm.use_llm else "📏 Rules"
            threshold = f"(threshold: {site.llm.relevance_threshold})" if site.llm.use_llm else ""
            print(f"   • {site.name} - {llm_status} {threshold}")
            if site.llm.custom_instructions:
                print(f"     Instructions: {site.llm.custom_instructions}")
        print()
        
        # Get agent status
        status = await orchestrator.get_status()
        print("📊 Agent Status:")
        print(f"   Status: {status.get('status', 'unknown')}")
        print(f"   Total Sites: {status.get('config', {}).get('total_sites', 0)}")
        print(f"   Enabled Sites: {status.get('config', {}).get('enabled_sites', 0)}")
        
        if orchestrator.settings.llm.enabled:
            print(f"   LLM Ready: ✅")
            print(f"   Fallback: Rule-based filtering available")
        else:
            print(f"   LLM Ready: ❌ (disabled)")
        
        print()
        
        # Demonstrate configuration
        print("⚙️  Phase 2 Configuration Features:")
        print("   ✅ Site-specific LLM settings")
        print("   ✅ Custom reasoning instructions")
        print("   ✅ Configurable relevance thresholds")
        print("   ✅ Multiple LLM provider support")
        print("   ✅ PostgreSQL production database support")
        print("   ✅ Comprehensive error handling")
        print()
        
        # Show what would happen in a run
        print("🚀 Ready to run! The agent will:")
        print("   1. 🕸️  Scrape configured websites")
        print("   2. 🧠 Use LLM to intelligently filter documents")
        print("   3. 📊 Score documents for relevance (0.0-1.0)")
        print("   4. 📥 Download only the most relevant files")
        print("   5. 💾 Store results and LLM reasoning in database")
        print()
        
        # Prompt for actual run
        if enabled_sites:
            response = input("Would you like to run a live demo? (y/N): ").lower().strip()
            if response == 'y':
                print("\n🎬 Starting live demo...")
                result = await orchestrator.run_single_cycle()
                
                print("\n📈 Demo Results:")
                print(f"   Sites Processed: {result.get('processed_sites', 0)}")
                print(f"   Links Found: {result.get('total_links_found', 0)}")
                print(f"   Links After Filtering: {result.get('total_links_filtered', 0)}")
                print(f"   Files Downloaded: {result.get('total_downloads_successful', 0)}")
                print(f"   Total Bytes: {result.get('total_bytes_downloaded', 0):,}")
                
                if 'sites' in result:
                    print("\n📊 Per-Site Results:")
                    for site_name, site_stats in result['sites'].items():
                        print(f"   {site_name}:")
                        print(f"     Downloads: {site_stats.get('downloads_successful', 0)}")
                        if 'filtering_stats' in site_stats:
                            filtering = site_stats['filtering_stats']
                            if 'llm_scores' in filtering:
                                print(f"     LLM Decisions: {len(filtering['llm_scores'])} documents scored")
            else:
                print("Demo complete! To run the agent:")
                print("   python -m modules.orchestrator")
        else:
            print("ℹ️  No sites enabled. Edit config/sites.yaml to enable sites.")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        print("Check your configuration and API keys.")


if __name__ == "__main__":
    asyncio.run(demo_phase2())
