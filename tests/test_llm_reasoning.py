"""
Tests for LLM-based reasoning functionality
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import List

from modules.reasoning import LLMBasedFilter, ReasoningEngine
from modules.perception import ScrapedLink
from modules.models import LLMConfig, SiteConfig, FiltersConfig, LLMSiteConfig
from modules.memory import MemoryManager


class TestLLMBasedFilter:
    
    @pytest.fixture
    def llm_config(self):
        """Create test LLM configuration"""
        return LLMConfig(
            enabled=True,
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
            max_tokens=1000,
            temperature=0.1
        )
    
    @pytest.fixture
    def site_config(self):
        """Create test site configuration"""
        return SiteConfig(
            name="Test Financial Site",
            url="https://example.com",
            file_types=[".pdf", ".csv"],
            filters=FiltersConfig(
                include=["annual", "report", "2024"],
                exclude=["draft", "preliminary"]
            ),
            llm=LLMSiteConfig(
                use_llm=True,
                relevance_threshold=0.7,
                custom_instructions="Focus on annual reports from major companies"
            )
        )
    
    @pytest.fixture
    def sample_links(self):
        """Create sample scraped links for testing"""
        return [
            ScrapedLink(
                url="https://example.com/annual-report-2024.pdf",
                title="Annual Report 2024",
                file_type=".pdf"
            ),
            ScrapedLink(
                url="https://example.com/quarterly-draft-q1.pdf",
                title="Draft Q1 Report",
                file_type=".pdf"
            ),
            ScrapedLink(
                url="https://example.com/financial-data-2024.csv",
                title="Financial Data 2024",
                file_type=".csv"
            )
        ]
    
    @patch('modules.reasoning.ChatOpenAI')
    @patch('modules.reasoning.LLMChain')
    def test_llm_filter_initialization(self, mock_chain, mock_openai, llm_config):
        """Test LLM filter initialization"""
        mock_openai.return_value = Mock()
        mock_chain.return_value = Mock()
        
        llm_filter = LLMBasedFilter(llm_config)
        
        assert llm_filter.config == llm_config
        assert llm_filter.client is not None
        mock_openai.assert_called_once()
    
    @patch('modules.reasoning.ChatAnthropic')
    def test_anthropic_initialization(self, mock_anthropic):
        """Test Anthropic provider initialization"""
        llm_config = LLMConfig(
            enabled=True,
            provider="anthropic",
            model="claude-3-haiku-20240307",
            api_key="test-key"
        )
        
        mock_anthropic.return_value = Mock()
        
        with patch('modules.reasoning.LLMChain'):
            llm_filter = LLMBasedFilter(llm_config)
            
        mock_anthropic.assert_called_once()
    
    def test_unsupported_provider(self):
        """Test error handling for unsupported providers"""
        llm_config = LLMConfig(
            enabled=True,
            provider="unsupported",
            model="test-model",
            api_key="test-key"
        )
        
        with pytest.raises(Exception) as exc_info:
            LLMBasedFilter(llm_config)
        
        assert "Unsupported LLM provider" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('modules.reasoning.ChatOpenAI')
    @patch('modules.reasoning.LLMChain')
    async def test_filter_links_success(self, mock_chain, mock_openai, llm_config, site_config, sample_links):
        """Test successful LLM filtering"""
        # Mock LLM response
        mock_llm_response = '''
        {
            "filtered_documents": [
                {
                    "url": "https://example.com/annual-report-2024.pdf",
                    "relevance_score": 0.9,
                    "reasoning": "High relevance annual report for 2024",
                    "include": true
                },
                {
                    "url": "https://example.com/quarterly-draft-q1.pdf",
                    "relevance_score": 0.3,
                    "reasoning": "Draft document, low relevance",
                    "include": false
                },
                {
                    "url": "https://example.com/financial-data-2024.csv",
                    "relevance_score": 0.8,
                    "reasoning": "Relevant financial data for 2024",
                    "include": true
                }
            ],
            "summary": {
                "total_evaluated": 3,
                "recommended_for_download": 2,
                "filtering_criteria_applied": ["relevance", "year", "document_type"]
            }
        }
        '''
        
        # Setup mocks
        mock_openai.return_value = Mock()
        mock_chain_instance = Mock()
        mock_chain_instance.run.return_value = mock_llm_response
        mock_chain.return_value = mock_chain_instance
        
        # Create filter and test
        llm_filter = LLMBasedFilter(llm_config)
        filtered_links, stats = await llm_filter.filter_links(sample_links, site_config)
        
        # Assertions
        assert len(filtered_links) == 2  # Only 2 links should pass threshold
        assert filtered_links[0].url == "https://example.com/annual-report-2024.pdf"
        assert filtered_links[1].url == "https://example.com/financial-data-2024.csv"
        
        assert stats["reasons"]["llm_relevance_filter"] == 1  # One excluded
        assert len(stats["llm_scores"]) == 2  # Two with scores
    
    @pytest.mark.asyncio
    @patch('modules.reasoning.ChatOpenAI')
    @patch('modules.reasoning.LLMChain')
    async def test_filter_links_json_error(self, mock_chain, mock_openai, llm_config, site_config, sample_links):
        """Test handling of invalid JSON response"""
        # Mock invalid JSON response
        mock_llm_response = "This is not valid JSON"
        
        mock_openai.return_value = Mock()
        mock_chain_instance = Mock()
        mock_chain_instance.run.return_value = mock_llm_response
        mock_chain.return_value = mock_chain_instance
        
        llm_filter = LLMBasedFilter(llm_config)
        filtered_links, stats = await llm_filter.filter_links(sample_links, site_config)
        
        # Should return original links on JSON error
        assert len(filtered_links) == len(sample_links)
        assert stats["reasons"]["llm_processing_error"] == len(sample_links)
    
    def test_site_purpose_inference(self, llm_config):
        """Test site purpose inference logic"""
        with patch('modules.reasoning.ChatOpenAI'), patch('modules.reasoning.LLMChain'):
            llm_filter = LLMBasedFilter(llm_config)
        
        # Test financial site
        financial_config = SiteConfig(
            name="SEC EDGAR Financial Reports",
            url="https://sec.gov",
            llm=LLMSiteConfig()
        )
        purpose = llm_filter._infer_site_purpose(financial_config)
        assert "Financial reports" in purpose
        
        # Test data site
        data_config = SiteConfig(
            name="Research Data Portal",
            url="https://data.gov",
            llm=LLMSiteConfig()
        )
        purpose = llm_filter._infer_site_purpose(data_config)
        assert "Research data" in purpose
    
    def test_document_formatting(self, llm_config, sample_links):
        """Test document formatting for prompts"""
        with patch('modules.reasoning.ChatOpenAI'), patch('modules.reasoning.LLMChain'):
            llm_filter = LLMBasedFilter(llm_config)
        
        doc_links = [
            {
                "index": i,
                "url": link.url,
                "title": link.title,
                "filename": link.filename,
                "file_type": link.file_type,
                "date": link.date,
                "size": link.size
            }
            for i, link in enumerate(sample_links)
        ]
        
        formatted = llm_filter._format_documents_for_prompt(doc_links)
        
        assert "Document 1:" in formatted
        assert "annual-report-2024.pdf" in formatted
        assert "URL:" in formatted
        assert "Title:" in formatted


class TestReasoningEngineWithLLM:
    
    @pytest.fixture
    def memory_manager_mock(self):
        """Create mock memory manager"""
        return Mock(spec=MemoryManager)
    
    @pytest.fixture
    def llm_config_enabled(self):
        """LLM configuration with LLM enabled"""
        return LLMConfig(
            enabled=True,
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key"
        )
    
    @pytest.fixture
    def llm_config_disabled(self):
        """LLM configuration with LLM disabled"""
        return LLMConfig(enabled=False)
    
    @patch('modules.reasoning.LLMBasedFilter')
    def test_reasoning_engine_llm_enabled(self, mock_llm_filter, memory_manager_mock, llm_config_enabled):
        """Test reasoning engine initialization with LLM enabled"""
        mock_llm_filter.return_value = Mock()
        
        engine = ReasoningEngine(llm_config_enabled, memory_manager_mock)
        
        assert engine.llm_filter is not None
        mock_llm_filter.assert_called_once_with(llm_config_enabled)
    
    def test_reasoning_engine_llm_disabled(self, memory_manager_mock, llm_config_disabled):
        """Test reasoning engine initialization with LLM disabled"""
        engine = ReasoningEngine(llm_config_disabled, memory_manager_mock)
        
        assert engine.llm_filter is None
    
    @pytest.mark.asyncio
    @patch('modules.reasoning.LLMBasedFilter')
    async def test_filter_links_with_llm(self, mock_llm_filter, memory_manager_mock, llm_config_enabled):
        """Test filtering links with LLM enabled"""
        # Setup mocks
        mock_filter_instance = Mock()
        mock_filter_instance.filter_links = AsyncMock(return_value=([], {"reasons": {"llm_filter": 0}}))
        mock_llm_filter.return_value = mock_filter_instance
        
        # Mock memory manager methods
        memory_manager_mock.is_already_downloaded = AsyncMock(return_value=False)
        
        engine = ReasoningEngine(llm_config_enabled, memory_manager_mock)
        
        # Create test data
        links = [ScrapedLink("https://example.com/test.pdf", "Test", file_type=".pdf")]
        site_config = SiteConfig(
            name="Test Site",
            url="https://example.com",
            llm=LLMSiteConfig(use_llm=True)
        )
        
        # Test filtering with LLM
        filtered_links, stats = await engine.filter_links(links, site_config, use_llm=True)
        
        # Verify LLM filter was called
        mock_filter_instance.filter_links.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.reasoning.LLMBasedFilter')
    async def test_filter_links_llm_fallback(self, mock_llm_filter, memory_manager_mock, llm_config_enabled):
        """Test fallback to rule-based filtering when LLM fails"""
        # Setup mocks - LLM filter raises exception
        mock_filter_instance = Mock()
        mock_filter_instance.filter_links = AsyncMock(side_effect=Exception("LLM API Error"))
        mock_llm_filter.return_value = mock_filter_instance
        
        # Mock memory manager
        memory_manager_mock.is_already_downloaded = AsyncMock(return_value=False)
        
        engine = ReasoningEngine(llm_config_enabled, memory_manager_mock)
        
        # Create test data
        links = [ScrapedLink("https://example.com/test.pdf", "Test", file_type=".pdf")]
        site_config = SiteConfig(
            name="Test Site",
            url="https://example.com",
            file_types=[".pdf"],
            llm=LLMSiteConfig(use_llm=True)
        )
        
        # Test filtering - should not fail despite LLM error
        filtered_links, stats = await engine.filter_links(links, site_config, use_llm=True)
        
        # Should still return results (rule-based filtering)
        assert isinstance(filtered_links, list)
        assert isinstance(stats, dict)


if __name__ == "__main__":
    pytest.main([__file__])
