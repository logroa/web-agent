#!/usr/bin/env python3
"""
Main entry point for the Web-Scraping & File Retrieval Agent
Command line interface for running the agent
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from modules.orchestrator import AgentOrchestrator


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Web-Scraping & File Retrieval Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                           # Run all enabled sites once
  python main.py --sites "Site 1" "Site 2"  # Run specific sites
  python main.py --continuous --interval 6  # Run every 6 hours
  python main.py --status                   # Show agent status
  python main.py --cleanup                  # Clean up old data
        """
    )
    
    parser.add_argument(
        "--sites", 
        nargs="+", 
        help="Specific sites to process (by name)"
    )
    
    parser.add_argument(
        "--continuous", 
        action="store_true",
        help="Run in continuous mode"
    )
    
    parser.add_argument(
        "--interval", 
        type=int, 
        default=24,
        help="Interval in hours for continuous mode (default: 24)"
    )
    
    parser.add_argument(
        "--status", 
        action="store_true",
        help="Show agent status and recent activity"
    )
    
    parser.add_argument(
        "--cleanup", 
        action="store_true",
        help="Clean up old data and failed downloads"
    )
    
    parser.add_argument(
        "--config-dir", 
        default="config",
        help="Configuration directory (default: config)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()


async def main():
    """Main function"""
    args = parse_arguments()
    
    # Set up logging level
    if args.verbose:
        os.environ["LOG_LEVEL"] = "DEBUG"
    
    try:
        # Initialize the agent
        print("🤖 Initializing Web Agent...")
        orchestrator = AgentOrchestrator(config_dir=args.config_dir)
        await orchestrator.initialize()
        
        # Handle different modes
        if args.status:
            await show_status(orchestrator)
        elif args.cleanup:
            await run_cleanup(orchestrator)
        elif args.continuous:
            await run_continuous(orchestrator, args.interval)
        else:
            await run_single_cycle(orchestrator, args.sites)
            
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        if hasattr(orchestrator, 'stop'):
            orchestrator.stop()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


async def show_status(orchestrator):
    """Show agent status"""
    print("📊 Agent Status")
    print("=" * 50)
    
    status = await orchestrator.get_status()
    
    print(f"Status: {status.get('status', 'unknown')}")
    print(f"Initialized: {status.get('initialized', False)}")
    
    if 'config' in status:
        config = status['config']
        print(f"Total Sites: {config.get('total_sites', 0)}")
        print(f"Enabled Sites: {config.get('enabled_sites', 0)}")
    
    if 'recent_downloads' in status:
        print(f"Recent Downloads: {status['recent_downloads']}")
    
    if 'storage' in status:
        storage = status['storage']
        print(f"Storage Path: {storage.get('path', 'N/A')}")
        print(f"Files Downloaded: {storage.get('file_count', 0)}")
        print(f"Total Size: {storage.get('total_size_mb', 0):.1f} MB")
    
    if 'recent_errors' in status:
        errors = status['recent_errors']
        if errors.get('total_errors', 0) > 0:
            print(f"Recent Errors: {errors['total_errors']}")
            for error_type, count in errors.get('error_types', {}).items():
                print(f"  {error_type}: {count}")


async def run_cleanup(orchestrator):
    """Run cleanup tasks"""
    print("🧹 Running cleanup...")
    await orchestrator.cleanup()
    print("✅ Cleanup complete")


async def run_continuous(orchestrator, interval_hours):
    """Run in continuous mode"""
    print(f"🔄 Starting continuous mode (every {interval_hours} hours)")
    print("Press Ctrl+C to stop")
    
    await orchestrator.run_continuous(interval_hours)


async def run_single_cycle(orchestrator, site_names):
    """Run a single scraping cycle"""
    if site_names:
        print(f"🎯 Processing specific sites: {', '.join(site_names)}")
    else:
        print("🌐 Processing all enabled sites")
    
    print("Starting scraping cycle...")
    result = await orchestrator.run_single_cycle(site_names)
    
    # Display results
    print("\n📈 Results Summary")
    print("=" * 50)
    print(f"Sites Processed: {result.get('processed_sites', 0)}")
    print(f"Links Found: {result.get('total_links_found', 0)}")
    print(f"Links After Filtering: {result.get('total_links_filtered', 0)}")
    print(f"Downloads Attempted: {result.get('total_downloads_attempted', 0)}")
    print(f"Downloads Successful: {result.get('total_downloads_successful', 0)}")
    print(f"Total Bytes Downloaded: {result.get('total_bytes_downloaded', 0):,}")
    
    if 'duration_seconds' in result:
        print(f"Duration: {result['duration_seconds']:.1f} seconds")
    
    # Show per-site results
    if 'sites' in result and result['sites']:
        print("\n📊 Per-Site Results:")
        for site_name, site_stats in result['sites'].items():
            if isinstance(site_stats, dict) and 'success' in site_stats:
                status = "✅" if site_stats['success'] else "❌"
                downloads = site_stats.get('downloads_successful', 0)
                print(f"  {status} {site_name}: {downloads} downloads")
    
    print("\n✅ Scraping cycle complete!")


if __name__ == "__main__":
    asyncio.run(main())
