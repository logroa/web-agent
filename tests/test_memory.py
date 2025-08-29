"""
Tests for memory management
"""

import pytest
import tempfile
import asyncio
from pathlib import Path

from modules.memory import MemoryManager
from modules.models import DatabaseConfig, DatabaseType


class TestMemoryManager:
    
    @pytest.fixture
    def temp_db_config(self):
        """Create temporary database configuration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            config = DatabaseConfig(
                type=DatabaseType.SQLITE,
                sqlite_path=str(db_path)
            )
            yield config
    
    @pytest.fixture
    def memory_manager(self, temp_db_config):
        """Create memory manager with temporary database"""
        return MemoryManager(temp_db_config)
    
    def test_memory_manager_initialization(self, memory_manager):
        """Test memory manager initialization"""
        assert memory_manager is not None
        assert memory_manager.engine is not None
    
    @pytest.mark.asyncio
    async def test_record_download(self, memory_manager):
        """Test recording a download"""
        record = await memory_manager.record_download(
            site_name="test_site",
            url="https://example.com/file.pdf",
            filename="file.pdf",
            file_path="/downloads/file.pdf",
            file_size_bytes=1024,
            success=True
        )
        
        assert record.site_name == "test_site"
        assert record.url == "https://example.com/file.pdf"
        assert record.success is True
        assert record.file_size_bytes == 1024
    
    @pytest.mark.asyncio
    async def test_is_already_downloaded(self, memory_manager):
        """Test checking if URL is already downloaded"""
        url = "https://example.com/test.pdf"
        
        # Initially should not be downloaded
        assert not await memory_manager.is_already_downloaded(url)
        
        # Record a successful download
        await memory_manager.record_download(
            site_name="test",
            url=url,
            filename="test.pdf",
            file_path="/test.pdf",
            success=True
        )
        
        # Now should be marked as downloaded
        assert await memory_manager.is_already_downloaded(url)
    
    @pytest.mark.asyncio
    async def test_scrape_session_management(self, memory_manager):
        """Test scrape session creation and completion"""
        # Start session
        session = await memory_manager.start_scrape_session("test_site")
        assert session.site_name == "test_site"
        assert session.id is not None
        
        # Complete session
        await memory_manager.complete_scrape_session(
            session.id,
            success=True,
            pages_scraped=5,
            files_found=10,
            files_downloaded=8,
            files_failed=2
        )
        
        # Session should be updated (we'd need to query it to verify)
        # This is a basic test to ensure no exceptions are raised
    
    @pytest.mark.asyncio
    async def test_visited_url_tracking(self, memory_manager):
        """Test visited URL tracking"""
        site_name = "test_site"
        url = "https://example.com/page1"
        
        # Initially should not be visited
        assert not await memory_manager.is_url_visited(site_name, url)
        
        # Record visit
        await memory_manager.record_visited_url(site_name, url, "hash123")
        
        # Now should be marked as visited
        assert await memory_manager.is_url_visited(site_name, url)
    
    @pytest.mark.asyncio
    async def test_error_logging(self, memory_manager):
        """Test error logging"""
        await memory_manager.log_error(
            error_type="test_error",
            error_message="This is a test error",
            site_name="test_site",
            url="https://example.com"
        )
        
        # Get error stats
        stats = await memory_manager.get_error_stats(site_name="test_site")
        assert stats["total_errors"] >= 1
        assert "test_error" in stats["error_types"]
    
    def test_file_hash_calculation(self, memory_manager):
        """Test file hash calculation"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_file = f.name
        
        try:
            hash1 = memory_manager.calculate_file_hash(temp_file)
            hash2 = memory_manager.calculate_file_hash(temp_file)
            
            # Same file should produce same hash
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA-256 produces 64 character hex string
            
        finally:
            Path(temp_file).unlink()
    
    def test_content_hash_calculation(self, memory_manager):
        """Test content hash calculation"""
        content = "test content"
        hash1 = memory_manager.calculate_content_hash(content)
        hash2 = memory_manager.calculate_content_hash(content)
        
        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64


if __name__ == "__main__":
    pytest.main([__file__])
