"""
Action module for the Web Agent
Handles file downloads and storage operations
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, unquote
import aiohttp
import aiofiles
from tqdm.asyncio import tqdm

from .models import StorageConfig, ScrapingConfig
from .perception import ScrapedLink
from .memory import MemoryManager

logger = logging.getLogger(__name__)


class DownloadResult:
    """Represents the result of a download attempt"""
    
    def __init__(
        self,
        link: ScrapedLink,
        success: bool,
        file_path: Optional[str] = None,
        file_size: Optional[int] = None,
        error_message: Optional[str] = None,
        retry_count: int = 0
    ):
        self.link = link
        self.success = success
        self.file_path = file_path
        self.file_size = file_size
        self.error_message = error_message
        self.retry_count = retry_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "url": self.link.url,
            "filename": self.link.filename,
            "success": self.success,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "error_message": self.error_message,
            "retry_count": self.retry_count
        }


class FileDownloader:
    """Handles file downloads with retry logic and progress tracking"""
    
    def __init__(
        self,
        storage_config: StorageConfig,
        scraping_config: ScrapingConfig,
        memory_manager: MemoryManager
    ):
        self.storage_config = storage_config
        self.scraping_config = scraping_config
        self.memory = memory_manager
        
        # Ensure download directory exists
        self.download_dir = Path(storage_config.local_path)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # Download session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Progress tracking
        self.download_progress = {}
        
        logger.info(f"FileDownloader initialized with storage: {storage_config.type}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def start(self):
        """Initialize HTTP session"""
        timeout = aiohttp.ClientTimeout(
            total=self.scraping_config.timeout_seconds * 2,  # Longer timeout for downloads
            connect=self.scraping_config.timeout_seconds
        )
        
        headers = {'User-Agent': self.scraping_config.user_agent}
        
        connector = aiohttp.TCPConnector(
            limit=self.scraping_config.concurrent_downloads,
            limit_per_host=self.scraping_config.concurrent_downloads
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector
        )
        
        logger.info("FileDownloader session started")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        logger.info("FileDownloader session closed")
    
    async def download_files(
        self,
        links: List[ScrapedLink],
        site_name: str,
        show_progress: bool = True
    ) -> Tuple[List[DownloadResult], Dict[str, Any]]:
        """
        Download multiple files concurrently
        
        Returns:
            Tuple of (download_results, download_stats)
        """
        logger.info(f"Starting download of {len(links)} files for {site_name}")
        
        stats = {
            "total_files": len(links),
            "successful_downloads": 0,
            "failed_downloads": 0,
            "total_bytes": 0,
            "skipped_files": 0
        }
        
        # Create semaphore to limit concurrent downloads
        semaphore = asyncio.Semaphore(self.scraping_config.concurrent_downloads)
        
        # Create download tasks
        download_tasks = []
        for i, link in enumerate(links):
            task = self._download_single_file_with_semaphore(
                semaphore, link, site_name, i, len(links), show_progress
            )
            download_tasks.append(task)
        
        # Execute downloads concurrently
        if show_progress:
            results = await tqdm.gather(*download_tasks, desc=f"Downloading from {site_name}")
        else:
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Process results
        download_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Download task failed with exception: {result}")
                continue
            
            download_results.append(result)
            
            if result.success:
                stats["successful_downloads"] += 1
                if result.file_size:
                    stats["total_bytes"] += result.file_size
            else:
                stats["failed_downloads"] += 1
        
        logger.info(f"Downloads complete: {stats['successful_downloads']}/{stats['total_files']} successful")
        return download_results, stats
    
    async def _download_single_file_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        link: ScrapedLink,
        site_name: str,
        index: int,
        total: int,
        show_progress: bool
    ) -> DownloadResult:
        """Download a single file with semaphore control"""
        async with semaphore:
            return await self._download_single_file(link, site_name, index, total, show_progress)
    
    async def _download_single_file(
        self,
        link: ScrapedLink,
        site_name: str,
        index: int,
        total: int,
        show_progress: bool
    ) -> DownloadResult:
        """Download a single file with retry logic"""
        
        for attempt in range(self.scraping_config.max_retries + 1):
            try:
                if show_progress:
                    logger.debug(f"[{index+1}/{total}] Downloading: {link.filename}")
                
                # Generate safe filename
                safe_filename = self._generate_safe_filename(link, site_name)
                file_path = self.download_dir / safe_filename
                
                # Check if file already exists and is complete
                if file_path.exists():
                    logger.debug(f"File already exists: {safe_filename}")
                    file_size = file_path.stat().st_size
                    
                    # Record successful download
                    await self.memory.record_download(
                        site_name=site_name,
                        url=link.url,
                        filename=safe_filename,
                        file_path=str(file_path),
                        file_size_bytes=file_size,
                        success=True,
                        retry_count=attempt
                    )
                    
                    return DownloadResult(
                        link=link,
                        success=True,
                        file_path=str(file_path),
                        file_size=file_size,
                        retry_count=attempt
                    )
                
                # Download the file
                file_size = await self._perform_download(link.url, file_path)
                
                # Calculate checksum
                checksum = await self._calculate_file_checksum(file_path)
                
                # Record successful download
                await self.memory.record_download(
                    site_name=site_name,
                    url=link.url,
                    filename=safe_filename,
                    file_path=str(file_path),
                    file_size_bytes=file_size,
                    success=True,
                    retry_count=attempt,
                    checksum=checksum
                )
                
                logger.info(f"Successfully downloaded: {safe_filename} ({file_size} bytes)")
                
                return DownloadResult(
                    link=link,
                    success=True,
                    file_path=str(file_path),
                    file_size=file_size,
                    retry_count=attempt
                )
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Download attempt {attempt + 1} failed for {link.filename}: {error_msg}")
                
                if attempt == self.scraping_config.max_retries:
                    # Final attempt failed, record failure
                    await self.memory.record_download(
                        site_name=site_name,
                        url=link.url,
                        filename=link.filename,
                        file_path="",
                        success=False,
                        error_message=error_msg,
                        retry_count=attempt
                    )
                    
                    return DownloadResult(
                        link=link,
                        success=False,
                        error_message=error_msg,
                        retry_count=attempt
                    )
                
                # Wait before retry
                if attempt < self.scraping_config.max_retries:
                    await asyncio.sleep(self.scraping_config.retry_delay_seconds * (attempt + 1))
        
        # Should never reach here, but just in case
        return DownloadResult(
            link=link,
            success=False,
            error_message="Max retries exceeded",
            retry_count=self.scraping_config.max_retries
        )
    
    async def _perform_download(self, url: str, file_path: Path) -> int:
        """Perform the actual file download"""
        
        async with self.session.get(url) as response:
            # Check response status
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {response.reason}")
            
            # Check content length
            content_length = response.headers.get('Content-Length')
            if content_length:
                file_size = int(content_length)
                max_size_bytes = self.scraping_config.max_file_size_mb * 1024 * 1024
                
                if file_size > max_size_bytes:
                    raise Exception(f"File too large: {file_size} bytes (max: {max_size_bytes})")
            
            # Download file in chunks
            total_size = 0
            async with aiofiles.open(file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):  # 8KB chunks
                    await f.write(chunk)
                    total_size += len(chunk)
                    
                    # Check size limit during download
                    max_size_bytes = self.scraping_config.max_file_size_mb * 1024 * 1024
                    if total_size > max_size_bytes:
                        # Remove partial file
                        await f.close()
                        file_path.unlink(missing_ok=True)
                        raise Exception(f"File too large during download: {total_size} bytes")
            
            return total_size
    
    def _generate_safe_filename(self, link: ScrapedLink, site_name: str) -> str:
        """Generate a safe filename for the downloaded file"""
        
        # Start with the original filename
        filename = link.filename
        
        # If no filename from URL, generate one
        if not filename or filename == "unknown":
            parsed_url = urlparse(link.url)
            if parsed_url.path:
                filename = Path(unquote(parsed_url.path)).name
            
            # Still no good filename? Generate from title or URL
            if not filename:
                if link.title:
                    filename = self._sanitize_filename(link.title)
                else:
                    filename = f"download_{hash(link.url) % 10000}"
                
                # Add extension if we know the file type
                if link.file_type:
                    filename += link.file_type
        
        # Sanitize the filename
        safe_filename = self._sanitize_filename(filename)
        
        # Add site prefix to avoid conflicts
        site_prefix = self._sanitize_filename(site_name)
        final_filename = f"{site_prefix}_{safe_filename}"
        
        # Ensure filename isn't too long
        if len(final_filename) > 200:
            name_part, ext_part = os.path.splitext(final_filename)
            final_filename = name_part[:200-len(ext_part)] + ext_part
        
        # Handle duplicates by adding counter
        base_path = self.download_dir / final_filename
        counter = 1
        while base_path.exists():
            name_part, ext_part = os.path.splitext(final_filename)
            numbered_filename = f"{name_part}_{counter}{ext_part}"
            base_path = self.download_dir / numbered_filename
            counter += 1
        
        return base_path.name
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to be filesystem-safe"""
        # Remove or replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove control characters
        filename = ''.join(char for char in filename if ord(char) >= 32)
        
        # Trim whitespace and dots
        filename = filename.strip(' .')
        
        # Ensure not empty
        if not filename:
            filename = "unnamed_file"
        
        return filename
    
    async def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of downloaded file"""
        try:
            return self.memory.calculate_file_hash(str(file_path))
        except Exception as e:
            logger.warning(f"Failed to calculate checksum for {file_path}: {e}")
            return ""
    
    async def verify_download(self, file_path: str, expected_size: Optional[int] = None) -> bool:
        """Verify that a downloaded file is complete and valid"""
        try:
            path = Path(file_path)
            
            # Check if file exists
            if not path.exists():
                return False
            
            # Check file size
            actual_size = path.stat().st_size
            if actual_size == 0:
                return False
            
            # Check against expected size if provided
            if expected_size and abs(actual_size - expected_size) > 1024:  # Allow 1KB difference
                logger.warning(f"File size mismatch: expected {expected_size}, got {actual_size}")
                return False
            
            # Basic file type validation
            try:
                with open(path, 'rb') as f:
                    header = f.read(512)
                
                # Check for common file signatures
                if path.suffix.lower() == '.pdf' and not header.startswith(b'%PDF'):
                    logger.warning(f"PDF file appears corrupted: {path}")
                    return False
                
            except Exception as e:
                logger.warning(f"Could not validate file header: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error verifying download {file_path}: {e}")
            return False
    
    async def cleanup_failed_downloads(self, max_age_hours: int = 24):
        """Clean up partial or failed download files"""
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            cleaned_files = 0
            for file_path in self.download_dir.rglob('*'):
                if file_path.is_file():
                    # Check if file is old enough
                    file_age = current_time - file_path.stat().st_mtime
                    
                    if file_age > max_age_seconds:
                        # Check if file appears to be a failed download (very small or corrupted)
                        file_size = file_path.stat().st_size
                        
                        if file_size < 1024:  # Less than 1KB - likely failed
                            file_path.unlink()
                            cleaned_files += 1
                            logger.debug(f"Cleaned up failed download: {file_path}")
            
            if cleaned_files > 0:
                logger.info(f"Cleaned up {cleaned_files} failed download files")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        try:
            total_files = 0
            total_size = 0
            file_types = {}
            
            for file_path in self.download_dir.rglob('*'):
                if file_path.is_file():
                    total_files += 1
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    
                    # Count by file type
                    file_type = file_path.suffix.lower()
                    if file_type not in file_types:
                        file_types[file_type] = {"count": 0, "size": 0}
                    file_types[file_type]["count"] += 1
                    file_types[file_type]["size"] += file_size
            
            return {
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_types": file_types,
                "storage_path": str(self.download_dir)
            }
            
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {"error": str(e)}
