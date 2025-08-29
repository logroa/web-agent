"""
Orchestrator module for the Web Agent
Main agent loop that coordinates perception, reasoning, and action
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import structlog

from .config import ConfigManager, ConfigurationError, load_env_file
from .memory import MemoryManager
from .perception import WebScraper
from .reasoning import ReasoningEngine
from .action import FileDownloader
from .models import AgentSettings, SitesConfig

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class AgentOrchestrator:
    """Main orchestrator for the web scraping agent"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.config_manager: Optional[ConfigManager] = None
        self.settings: Optional[AgentSettings] = None
        self.sites: Optional[SitesConfig] = None
        
        # Core components
        self.memory_manager: Optional[MemoryManager] = None
        self.web_scraper: Optional[WebScraper] = None
        self.reasoning_engine: Optional[ReasoningEngine] = None
        self.file_downloader: Optional[FileDownloader] = None
        
        # State tracking
        self.is_running = False
        self.current_session_id: Optional[int] = None
        
        logger.info("AgentOrchestrator initialized")
    
    async def initialize(self):
        """Initialize all agent components"""
        logger.info("Initializing agent components...")
        
        try:
            # Load environment variables
            load_env_file()
            
            # Load configuration
            self.config_manager = ConfigManager(self.config_dir)
            self.settings = self.config_manager.load_settings()
            self.sites = self.config_manager.load_sites()
            
            # Validate configuration
            validation_result = self.config_manager.validate_configuration()
            if not validation_result["valid"]:
                raise ConfigurationError(f"Configuration validation failed: {validation_result['errors']}")
            
            # Setup logging
            self._setup_logging()
            
            # Initialize components
            self.memory_manager = MemoryManager(self.settings.database)
            
            self.web_scraper = WebScraper(
                self.settings.scraping,
                self.memory_manager
            )
            
            self.reasoning_engine = ReasoningEngine(
                self.settings.llm,
                self.memory_manager
            )
            
            self.file_downloader = FileDownloader(
                self.settings.storage,
                self.settings.scraping,
                self.memory_manager
            )
            
            logger.info("Agent initialization complete")
            
        except Exception as e:
            logger.error("Failed to initialize agent", error=str(e))
            raise
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_config = self.settings.logging
        
        # Create log directory
        log_path = Path(log_config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure Python logging
        log_level = getattr(logging, log_config.level.upper(), logging.INFO)
        
        # Create formatters
        if log_config.format == "json":
            formatter = structlog.processors.JSONRenderer()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # File handler
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_config.log_file,
            maxBytes=log_config.max_log_size_mb * 1024 * 1024,
            backupCount=log_config.backup_count
        )
        file_handler.setLevel(log_level)
        if log_config.format != "json":
            file_handler.setFormatter(formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        if log_config.format != "json":
            console_handler.setFormatter(formatter)
        
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        logger.info("Logging configured", level=log_config.level, format=log_config.format)
    
    async def run_single_cycle(self, site_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run a single scraping cycle for specified sites or all enabled sites"""
        logger.info("Starting single agent cycle")
        
        if not self.memory_manager:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        # Get sites to process
        if site_names:
            sites_to_process = []
            for name in site_names:
                try:
                    site = self.config_manager.get_site_by_name(name)
                    sites_to_process.append(site)
                except ConfigurationError as e:
                    logger.warning(f"Site '{name}' not found: {e}")
        else:
            sites_to_process = self.config_manager.get_enabled_sites()
        
        if not sites_to_process:
            logger.warning("No sites to process")
            return {"processed_sites": 0, "total_downloads": 0}
        
        logger.info(f"Processing {len(sites_to_process)} sites")
        
        # Initialize async components
        async with self.web_scraper, self.file_downloader:
            
            cycle_stats = {
                "start_time": datetime.utcnow().isoformat(),
                "processed_sites": 0,
                "total_links_found": 0,
                "total_links_filtered": 0,
                "total_downloads_attempted": 0,
                "total_downloads_successful": 0,
                "total_bytes_downloaded": 0,
                "sites": {}
            }
            
            # Process each site
            for site_config in sites_to_process:
                try:
                    site_stats = await self._process_site(site_config)
                    cycle_stats["sites"][site_config.name] = site_stats
                    
                    # Aggregate stats
                    cycle_stats["processed_sites"] += 1
                    cycle_stats["total_links_found"] += site_stats.get("links_found", 0)
                    cycle_stats["total_links_filtered"] += site_stats.get("links_filtered", 0)
                    cycle_stats["total_downloads_attempted"] += site_stats.get("downloads_attempted", 0)
                    cycle_stats["total_downloads_successful"] += site_stats.get("downloads_successful", 0)
                    cycle_stats["total_bytes_downloaded"] += site_stats.get("bytes_downloaded", 0)
                    
                except Exception as e:
                    logger.error(f"Failed to process site {site_config.name}", error=str(e))
                    cycle_stats["sites"][site_config.name] = {
                        "error": str(e),
                        "success": False
                    }
            
            cycle_stats["end_time"] = datetime.utcnow().isoformat()
            cycle_stats["duration_seconds"] = (
                datetime.fromisoformat(cycle_stats["end_time"]) - 
                datetime.fromisoformat(cycle_stats["start_time"])
            ).total_seconds()
            
            logger.info("Agent cycle complete", **cycle_stats)
            return cycle_stats
    
    async def _process_site(self, site_config) -> Dict[str, Any]:
        """Process a single site through the full pipeline"""
        logger.info(f"Processing site: {site_config.name}")
        
        # Start scrape session
        session = await self.memory_manager.start_scrape_session(site_config.name)
        
        site_stats = {
            "site_name": site_config.name,
            "session_id": session.id,
            "start_time": datetime.utcnow().isoformat(),
            "success": False,
            "links_found": 0,
            "links_filtered": 0,
            "downloads_attempted": 0,
            "downloads_successful": 0,
            "bytes_downloaded": 0,
            "errors": []
        }
        
        try:
            # Step 1: Perception - Scrape the site
            logger.info(f"Scraping site: {site_config.name}")
            scraped_links = await self.web_scraper.scrape_site(site_config)
            site_stats["links_found"] = len(scraped_links)
            
            if not scraped_links:
                logger.warning(f"No links found for site: {site_config.name}")
                site_stats["success"] = True  # Not an error, just no content
                return site_stats
            
            # Step 2: Reasoning - Filter and prioritize links
            logger.info(f"Filtering {len(scraped_links)} links for {site_config.name}")
            filtered_links, filtering_stats = await self.reasoning_engine.filter_links(
                scraped_links, site_config
            )
            site_stats["links_filtered"] = len(filtered_links)
            site_stats["filtering_stats"] = filtering_stats
            
            if not filtered_links:
                logger.info(f"No links passed filtering for site: {site_config.name}")
                site_stats["success"] = True
                return site_stats
            
            # Prioritize links
            prioritized_links = self.reasoning_engine.prioritize_links(filtered_links, site_config)
            
            # Step 3: Action - Download files
            logger.info(f"Downloading {len(prioritized_links)} files for {site_config.name}")
            download_results, download_stats = await self.file_downloader.download_files(
                prioritized_links, site_config.name
            )
            
            site_stats["downloads_attempted"] = download_stats["total_files"]
            site_stats["downloads_successful"] = download_stats["successful_downloads"]
            site_stats["bytes_downloaded"] = download_stats["total_bytes"]
            site_stats["download_stats"] = download_stats
            
            # Log any download failures
            failed_downloads = [r for r in download_results if not r.success]
            if failed_downloads:
                logger.warning(f"{len(failed_downloads)} downloads failed for {site_config.name}")
                for failed in failed_downloads[:5]:  # Log first 5 failures
                    site_stats["errors"].append({
                        "url": failed.link.url,
                        "error": failed.error_message
                    })
            
            site_stats["success"] = True
            logger.info(f"Site processing complete: {site_config.name}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Site processing failed: {site_config.name}", error=error_msg)
            site_stats["errors"].append({"general_error": error_msg})
            
            # Log error to database
            await self.memory_manager.log_error(
                error_type="site_processing_error",
                error_message=error_msg,
                site_name=site_config.name
            )
        
        finally:
            # Complete scrape session
            await self.memory_manager.complete_scrape_session(
                session.id,
                success=site_stats["success"],
                pages_scraped=1,  # For now, we scrape one page per site
                files_found=site_stats["links_found"],
                files_downloaded=site_stats["downloads_successful"],
                files_failed=site_stats["downloads_attempted"] - site_stats["downloads_successful"],
                error_message="; ".join([str(e) for e in site_stats["errors"]]) if site_stats["errors"] else None
            )
            
            site_stats["end_time"] = datetime.utcnow().isoformat()
        
        return site_stats
    
    async def run_continuous(self, interval_hours: int = 24):
        """Run the agent continuously with specified interval"""
        logger.info(f"Starting continuous mode with {interval_hours}h interval")
        
        self.is_running = True
        
        while self.is_running:
            try:
                # Run a cycle
                await self.run_single_cycle()
                
                # Wait for next cycle
                if self.is_running:  # Check if we should continue
                    logger.info(f"Waiting {interval_hours} hours until next cycle")
                    await asyncio.sleep(interval_hours * 3600)
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, stopping...")
                break
            except Exception as e:
                logger.error("Error in continuous mode", error=str(e))
                # Wait a bit before retrying
                await asyncio.sleep(300)  # 5 minutes
        
        self.is_running = False
        logger.info("Continuous mode stopped")
    
    def stop(self):
        """Stop the continuous running mode"""
        logger.info("Stopping agent...")
        self.is_running = False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current agent status and statistics"""
        if not self.memory_manager:
            return {"status": "not_initialized"}
        
        try:
            # Get recent stats
            error_stats = await self.memory_manager.get_error_stats(hours=24)
            download_history = await self.memory_manager.get_download_history(limit=10)
            
            # Get storage stats
            storage_stats = {}
            if self.file_downloader:
                storage_stats = self.file_downloader.get_storage_stats()
            
            status = {
                "status": "running" if self.is_running else "idle",
                "initialized": True,
                "config": {
                    "enabled_sites": len(self.config_manager.get_enabled_sites()),
                    "total_sites": len(self.sites.sites) if self.sites else 0,
                },
                "recent_errors": error_stats,
                "recent_downloads": len(download_history),
                "storage": storage_stats,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return status
            
        except Exception as e:
            logger.error("Error getting status", error=str(e))
            return {"status": "error", "error": str(e)}
    
    async def cleanup(self):
        """Cleanup resources and old data"""
        logger.info("Running cleanup tasks")
        
        try:
            if self.memory_manager:
                # Clean up old database records
                await self.memory_manager.cleanup_old_records(days=30)
            
            if self.file_downloader:
                # Clean up failed downloads
                await self.file_downloader.cleanup_failed_downloads(max_age_hours=24)
            
            logger.info("Cleanup tasks completed")
            
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))


async def main():
    """Main entry point for the agent"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Web Scraping & File Retrieval Agent")
    parser.add_argument("--config-dir", default="config", help="Configuration directory")
    parser.add_argument("--sites", nargs="*", help="Specific sites to process")
    parser.add_argument("--continuous", action="store_true", help="Run in continuous mode")
    parser.add_argument("--interval", type=int, default=24, help="Interval in hours for continuous mode")
    parser.add_argument("--cleanup", action="store_true", help="Run cleanup tasks")
    parser.add_argument("--status", action="store_true", help="Show agent status")
    
    args = parser.parse_args()
    
    # Create and initialize orchestrator
    orchestrator = AgentOrchestrator(args.config_dir)
    
    try:
        await orchestrator.initialize()
        
        if args.status:
            status = await orchestrator.get_status()
            print("Agent Status:")
            for key, value in status.items():
                print(f"  {key}: {value}")
            return
        
        if args.cleanup:
            await orchestrator.cleanup()
            return
        
        if args.continuous:
            await orchestrator.run_continuous(args.interval)
        else:
            result = await orchestrator.run_single_cycle(args.sites)
            print("\nCycle Results:")
            for key, value in result.items():
                if key != "sites":
                    print(f"  {key}: {value}")
            
            if result.get("sites"):
                print("\nSite Results:")
                for site_name, site_stats in result["sites"].items():
                    print(f"  {site_name}: {site_stats.get('downloads_successful', 0)} downloads")
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Fatal error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
