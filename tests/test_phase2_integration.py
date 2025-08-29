"""
Integration tests for Phase 2 features
Tests the complete pipeline with LLM integration
"""

import pytest
import asyncio
import tempfile
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from modules.orchestrator import AgentOrchestrator
from modules.config import ConfigManager
from modules.models import AgentSettings, SitesConfig, SiteConfig, LLMConfig, LLMSiteConfig
from modules.perception import ScrapedLink


class TestPhase2Integration:
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary configuration directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create settings.yaml
            settings_content = """
database:
  type: sqlite
  sqlite_path: ":memory:"

storage:
  type: local
  local_path: "/tmp/test_downloads"

scraping:
  user_agent: "TestAgent/1.0"
  max_retries: 1
  concurrent_downloads: 1

logging:
  level: DEBUG
  format: json

llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  api_key: test-key
  max_tokens: 1000
  temperature: 0.1
"""
            
            # Create sites.yaml
            sites_content = """
sites:
  - name: "Test Site"
    url: "https://example.com"
    enabled: true
    file_types: [".pdf"]
    filters:
      include: ["report", "2024"]
      exclude: ["draft"]
    llm:
      use_llm: true
      relevance_threshold: 0.7
      custom_instructions: "Focus on annual reports"
"""
            
            with open(config_dir / "settings.yaml", 'w') as f:
                f.write(settings_content)
            
            with open(config_dir / "sites.yaml", 'w') as f:
                f.write(sites_content)
            
            yield str(config_dir)
    
    @pytest.mark.asyncio
    @patch('modules.perception.WebScraper')
    @patch('modules.action.FileDownloader')
    @patch('modules.reasoning.LLMBasedFilter')
    async def test_full_pipeline_with_llm(
        self,
        mock_llm_filter_class,
        mock_downloader_class,
        mock_scraper_class,
        temp_config_dir
    ):
        """Test complete pipeline with LLM filtering"""
        
        # Setup mock scraped links
        mock_links = [
            ScrapedLink(
                url="https://example.com/annual-report-2024.pdf",
                title="Annual Report 2024",
                file_type=".pdf"
            ),
            ScrapedLink(
                url="https://example.com/draft-report-2024.pdf",
                title="Draft Report 2024",
                file_type=".pdf"
            ),
            ScrapedLink(
                url="https://example.com/quarterly-2024.pdf",
                title="Quarterly Report 2024",
                file_type=".pdf"
            )
        ]
        
        # Setup mock LLM response
        mock_llm_response = '''
        {
            "filtered_documents": [
                {
                    "url": "https://example.com/annual-report-2024.pdf",
                    "relevance_score": 0.9,
                    "reasoning": "High relevance annual report",
                    "include": true
                },
                {
                    "url": "https://example.com/draft-report-2024.pdf",
                    "relevance_score": 0.3,
                    "reasoning": "Draft document, low relevance",
                    "include": false
                },
                {
                    "url": "https://example.com/quarterly-2024.pdf",
                    "relevance_score": 0.8,
                    "reasoning": "Relevant quarterly report",
                    "include": true
                }
            ]
        }
        '''
        
        # Setup mocks
        mock_scraper_instance = Mock()
        mock_scraper_instance.scrape_site = AsyncMock(return_value=mock_links)
        mock_scraper_instance.__aenter__ = AsyncMock(return_value=mock_scraper_instance)
        mock_scraper_instance.__aexit__ = AsyncMock(return_value=None)
        mock_scraper_class.return_value = mock_scraper_instance
        
        mock_downloader_instance = Mock()
        mock_downloader_instance.download_files = AsyncMock(return_value=([], {
            "total_files": 2,
            "successful_downloads": 2,
            "failed_downloads": 0,
            "total_bytes": 1000000
        }))
        mock_downloader_instance.__aenter__ = AsyncMock(return_value=mock_downloader_instance)
        mock_downloader_instance.__aexit__ = AsyncMock(return_value=None)
        mock_downloader_class.return_value = mock_downloader_instance
        
        # Setup LLM filter mock
        mock_llm_filter_instance = Mock()
        mock_llm_filter_instance.filter_links = AsyncMock(return_value=(
            [mock_links[0], mock_links[2]],  # Annual and quarterly, not draft
            {
                "reasons": {
                    "llm_relevance_filter": 1,
                    "llm_low_confidence": 0,
                    "llm_processing_error": 0
                },
                "llm_scores": [
                    {"url": mock_links[0].url, "score": 0.9, "reasoning": "High relevance"},
                    {"url": mock_links[2].url, "score": 0.8, "reasoning": "Good relevance"}
                ]
            }
        ))
        mock_llm_filter_class.return_value = mock_llm_filter_instance
        
        # Mock LangChain components
        with patch('modules.reasoning.ChatOpenAI'), \
             patch('modules.reasoning.LLMChain'), \
             patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            
            # Initialize orchestrator
            orchestrator = AgentOrchestrator(temp_config_dir)
            await orchestrator.initialize()
            
            # Run single cycle
            result = await orchestrator.run_single_cycle()
            
            # Verify results
            assert result["processed_sites"] == 1
            assert result["total_links_found"] == 3
            assert result["total_links_filtered"] == 2  # LLM filtered out 1
            assert result["total_downloads_successful"] == 2
            
            # Verify LLM filter was called
            mock_llm_filter_instance.filter_links.assert_called_once()
            
            # Verify scraper was called
            mock_scraper_instance.scrape_site.assert_called_once()
            
            # Verify downloader was called with filtered links
            mock_downloader_instance.download_files.assert_called_once()
            call_args = mock_downloader_instance.download_files.call_args[0]
            downloaded_links = call_args[0]
            assert len(downloaded_links) == 2  # Only non-draft documents
    
    @pytest.mark.asyncio
    async def test_llm_disabled_fallback(self, temp_config_dir):
        """Test that system works when LLM is disabled"""
        
        # Modify config to disable LLM
        config_path = Path(temp_config_dir) / "settings.yaml"
        config_content = config_path.read_text().replace("enabled: true", "enabled: false")
        config_path.write_text(config_content)
        
        with patch('modules.perception.WebScraper') as mock_scraper_class, \
             patch('modules.action.FileDownloader') as mock_downloader_class:
            
            # Setup mocks for rule-based only
            mock_scraper_instance = Mock()
            mock_scraper_instance.scrape_site = AsyncMock(return_value=[])
            mock_scraper_instance.__aenter__ = AsyncMock(return_value=mock_scraper_instance)
            mock_scraper_instance.__aexit__ = AsyncMock(return_value=None)
            mock_scraper_class.return_value = mock_scraper_instance
            
            mock_downloader_instance = Mock()
            mock_downloader_instance.__aenter__ = AsyncMock(return_value=mock_downloader_instance)
            mock_downloader_instance.__aexit__ = AsyncMock(return_value=None)
            mock_downloader_class.return_value = mock_downloader_instance
            
            orchestrator = AgentOrchestrator(temp_config_dir)
            await orchestrator.initialize()
            
            # Verify LLM is disabled
            assert not orchestrator.settings.llm.enabled
            assert orchestrator.reasoning_engine.llm_filter is None
    
    @pytest.mark.asyncio
    @patch('modules.reasoning.LLMBasedFilter')
    async def test_llm_error_handling(self, mock_llm_filter_class, temp_config_dir):
        """Test error handling when LLM initialization fails"""
        
        # Make LLM filter initialization fail
        mock_llm_filter_class.side_effect = Exception("API key invalid")
        
        with patch('modules.perception.WebScraper'), \
             patch('modules.action.FileDownloader'):
            
            orchestrator = AgentOrchestrator(temp_config_dir)
            
            # Should not raise exception, should fall back gracefully
            await orchestrator.initialize()
            
            # LLM filter should be None due to initialization error
            assert orchestrator.reasoning_engine.llm_filter is None
    
    def test_config_validation_with_llm_settings(self, temp_config_dir):
        """Test configuration validation with LLM settings"""
        
        config_manager = ConfigManager(temp_config_dir)
        settings = config_manager.load_settings()
        sites = config_manager.load_sites()
        
        # Verify LLM settings loaded correctly
        assert settings.llm.enabled is True
        assert settings.llm.provider == "openai"
        assert settings.llm.model == "gpt-4o-mini"
        
        # Verify site-level LLM settings
        test_site = sites.sites[0]
        assert test_site.llm.use_llm is True
        assert test_site.llm.relevance_threshold == 0.7
        assert "annual reports" in test_site.llm.custom_instructions
    
    @pytest.mark.asyncio
    async def test_postgres_connection_config(self):
        """Test PostgreSQL configuration (without actual connection)"""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create settings with PostgreSQL config
            settings_content = """
database:
  type: postgres
  postgres:
    host: localhost
    port: 5432
    database: web_agent
    username: agent_user
    password: test_password

llm:
  enabled: false  # Disabled for this test
"""
            
            with open(config_dir / "settings.yaml", 'w') as f:
                f.write(settings_content)
            
            # Create minimal sites config
            sites_content = """
sites:
  - name: "Test"
    url: "https://example.com"
    enabled: false
"""
            
            with open(config_dir / "sites.yaml", 'w') as f:
                f.write(sites_content)
            
            config_manager = ConfigManager(str(config_dir))
            settings = config_manager.load_settings()
            
            # Verify PostgreSQL config loaded
            assert settings.database.type == "postgres"
            assert settings.database.postgres["host"] == "localhost"
            assert settings.database.postgres["port"] == 5432
    
    @pytest.mark.asyncio
    async def test_custom_llm_instructions_integration(self, temp_config_dir):
        """Test that custom LLM instructions are properly integrated"""
        
        with patch('modules.reasoning.LLMBasedFilter') as mock_llm_filter_class, \
             patch('modules.perception.WebScraper'), \
             patch('modules.action.FileDownloader'):
            
            # Setup LLM filter mock
            mock_filter = Mock()
            mock_filter.filter_links = AsyncMock(return_value=([], {"reasons": {}}))
            mock_llm_filter_class.return_value = mock_filter
            
            orchestrator = AgentOrchestrator(temp_config_dir)
            
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
                await orchestrator.initialize()
                
                # Get the site config
                site_config = orchestrator.sites.sites[0]
                
                # Verify custom instructions are present
                assert site_config.llm.custom_instructions == "Focus on annual reports"
                assert site_config.llm.relevance_threshold == 0.7


if __name__ == "__main__":
    pytest.main([__file__])
