"""
Perception module for the Web Agent
Handles web scraping, content extraction, and link discovery
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright, Browser, Page

from .models import SiteConfig, ScrapingConfig
from .memory import MemoryManager

logger = logging.getLogger(__name__)


class ScrapedLink:
    """Represents a discovered link with metadata"""
    
    def __init__(
        self,
        url: str,
        title: str = "",
        text: str = "",
        file_type: str = "",
        date: str = "",
        size: str = ""
    ):
        self.url = url
        self.title = title.strip()
        self.text = text.strip()
        self.file_type = file_type.lower()
        self.date = date.strip()
        self.size = size.strip()
        self.parsed_url = urlparse(url)
        self.filename = Path(self.parsed_url.path).name or "unknown"
    
    def __repr__(self):
        return f"ScrapedLink(url='{self.url}', title='{self.title}', type='{self.file_type}')"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "file_type": self.file_type,
            "date": self.date,
            "size": self.size,
            "filename": self.filename
        }


class WebScraper:
    """Main web scraping class using Playwright and BeautifulSoup"""
    
    def __init__(
        self,
        scraping_config: ScrapingConfig,
        memory_manager: MemoryManager
    ):
        self.config = scraping_config
        self.memory = memory_manager
        self.browser: Optional[Browser] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiting
        self._last_request_time = {}
        self._request_counts = {}
        
        logger.info(f"Initialized WebScraper with {self.config.concurrent_downloads} concurrent downloads")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def start(self):
        """Initialize browser and HTTP session"""
        try:
            # Start Playwright browser
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions'
                ]
            )
            
            # Create HTTP session for simple requests
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            headers = {'User-Agent': self.config.user_agent}
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
                connector=aiohttp.TCPConnector(limit=self.config.concurrent_downloads)
            )
            
            logger.info("WebScraper started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start WebScraper: {e}")
            raise
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        
        if self.browser:
            await self.browser.close()
        
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
        
        logger.info("WebScraper closed")
    
    def _check_robots_txt(self, site_url: str) -> bool:
        """Check if scraping is allowed by robots.txt"""
        if not self.config.respect_robots_txt:
            return True
        
        try:
            robots_url = urljoin(site_url, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            
            can_fetch = rp.can_fetch(self.config.user_agent, site_url)
            logger.debug(f"robots.txt check for {site_url}: {'allowed' if can_fetch else 'disallowed'}")
            return can_fetch
            
        except Exception as e:
            logger.warning(f"Failed to check robots.txt for {site_url}: {e}")
            return True  # Allow if we can't check
    
    async def _rate_limit(self, site_name: str, site_config: SiteConfig):
        """Implement rate limiting per site"""
        current_time = time.time()
        
        # Check requests per minute limit
        if site_name not in self._request_counts:
            self._request_counts[site_name] = []
        
        # Remove requests older than 1 minute
        minute_ago = current_time - 60
        self._request_counts[site_name] = [
            req_time for req_time in self._request_counts[site_name] 
            if req_time > minute_ago
        ]
        
        # Check if we're at the limit
        if len(self._request_counts[site_name]) >= site_config.rate_limit.requests_per_minute:
            sleep_time = 60 - (current_time - self._request_counts[site_name][0])
            if sleep_time > 0:
                logger.info(f"Rate limiting {site_name}: sleeping {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
        
        # Check delay between requests
        if site_name in self._last_request_time:
            time_since_last = current_time - self._last_request_time[site_name]
            min_delay = site_config.rate_limit.delay_between_requests
            if time_since_last < min_delay:
                sleep_time = min_delay - time_since_last
                logger.debug(f"Delaying request to {site_name}: {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
        
        # Record this request
        self._request_counts[site_name].append(time.time())
        self._last_request_time[site_name] = time.time()
    
    async def scrape_site(self, site_config: SiteConfig) -> List[ScrapedLink]:
        """Scrape a single site and return discovered links"""
        logger.info(f"Starting to scrape site: {site_config.name}")
        
        if not self._check_robots_txt(str(site_config.url)):
            logger.warning(f"Scraping disallowed by robots.txt for {site_config.name}")
            return []
        
        try:
            await self._rate_limit(site_config.name, site_config)
            
            # Check if we need JavaScript rendering
            if await self._requires_javascript(str(site_config.url)):
                links = await self._scrape_with_playwright(site_config)
            else:
                links = await self._scrape_with_aiohttp(site_config)
            
            logger.info(f"Found {len(links)} links on {site_config.name}")
            return links
            
        except Exception as e:
            logger.error(f"Failed to scrape {site_config.name}: {e}")
            await self.memory.log_error(
                error_type="scraping_error",
                error_message=str(e),
                site_name=site_config.name,
                url=str(site_config.url)
            )
            return []
    
    async def _requires_javascript(self, url: str) -> bool:
        """Determine if a page requires JavaScript rendering"""
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return True  # Use Playwright for non-200 responses
                
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Simple heuristics to detect JS-heavy sites
                script_tags = soup.find_all('script')
                if len(script_tags) > 10:  # Lots of scripts
                    return True
                
                # Check for common SPA frameworks
                js_indicators = ['react', 'vue', 'angular', 'ember', 'spa']
                content_lower = content.lower()
                if any(indicator in content_lower for indicator in js_indicators):
                    return True
                
                # Check if main content area is empty
                main_selectors = ['main', '#main', '.main', '#content', '.content']
                for selector in main_selectors:
                    element = soup.select_one(selector)
                    if element and len(element.get_text().strip()) < 100:
                        return True
                
                return False
                
        except Exception as e:
            logger.warning(f"Error checking if JS required for {url}: {e}")
            return True  # Default to Playwright on error
    
    async def _scrape_with_aiohttp(self, site_config: SiteConfig) -> List[ScrapedLink]:
        """Scrape using aiohttp for static content"""
        links = []
        
        try:
            async with self.session.get(str(site_config.url)) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}: {response.reason}")
                
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extract links using configured selectors
                link_elements = soup.select(site_config.selectors.link_selector)
                
                for element in link_elements:
                    link = self._extract_link_info(element, site_config, str(site_config.url))
                    if link and self._is_valid_file_type(link.file_type, site_config.file_types):
                        links.append(link)
                
                # Handle pagination if enabled
                if site_config.pagination.enabled:
                    pagination_links = await self._handle_pagination_aiohttp(
                        soup, site_config, str(site_config.url)
                    )
                    links.extend(pagination_links)
                
        except Exception as e:
            logger.error(f"aiohttp scraping failed for {site_config.name}: {e}")
            raise
        
        return links
    
    async def _scrape_with_playwright(self, site_config: SiteConfig) -> List[ScrapedLink]:
        """Scrape using Playwright for JavaScript-heavy sites"""
        links = []
        
        try:
            page = await self.browser.new_page()
            
            # Set user agent
            await page.set_extra_http_headers({'User-Agent': self.config.user_agent})
            
            # Navigate to the page
            await page.goto(str(site_config.url), wait_until='networkidle')
            
            # Wait for dynamic content to load
            await page.wait_for_timeout(2000)
            
            # Get page content
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract links
            link_elements = soup.select(site_config.selectors.link_selector)
            
            for element in link_elements:
                link = self._extract_link_info(element, site_config, str(site_config.url))
                if link and self._is_valid_file_type(link.file_type, site_config.file_types):
                    links.append(link)
            
            # Handle pagination if enabled
            if site_config.pagination.enabled:
                pagination_links = await self._handle_pagination_playwright(
                    page, site_config, str(site_config.url)
                )
                links.extend(pagination_links)
            
            await page.close()
            
        except Exception as e:
            logger.error(f"Playwright scraping failed for {site_config.name}: {e}")
            raise
        
        return links
    
    def _extract_link_info(
        self, 
        element: Tag, 
        site_config: SiteConfig, 
        base_url: str
    ) -> Optional[ScrapedLink]:
        """Extract link information from a BeautifulSoup element"""
        try:
            # Get URL
            href = element.get('href')
            if not href:
                return None
            
            # Convert relative URLs to absolute
            url = urljoin(base_url, href)
            
            # Extract title/text
            title = element.get('title', '') or element.get_text().strip()
            
            # Determine file type
            file_type = self._get_file_type(url)
            
            # Extract date if selector is provided
            date = ""
            if site_config.selectors.date_selector:
                date_element = element.find_next(site_config.selectors.date_selector)
                if date_element:
                    date = date_element.get_text().strip()
            
            # Extract size information if available
            size = ""
            size_indicators = ['size', 'bytes', 'kb', 'mb', 'gb']
            for indicator in size_indicators:
                size_element = element.find_next(string=lambda text: text and indicator in text.lower())
                if size_element:
                    size = size_element.strip()
                    break
            
            return ScrapedLink(
                url=url,
                title=title,
                file_type=file_type,
                date=date,
                size=size
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract link info from element: {e}")
            return None
    
    def _get_file_type(self, url: str) -> str:
        """Extract file type from URL"""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Get extension from path
        if '.' in path:
            extension = '.' + path.split('.')[-1]
            return extension
        
        # Check query parameters for file type hints
        query_params = parse_qs(parsed.query)
        for param, values in query_params.items():
            for value in values:
                if '.' in value and len(value.split('.')[-1]) <= 4:
                    return '.' + value.split('.')[-1].lower()
        
        return ""
    
    def _is_valid_file_type(self, file_type: str, allowed_types: List[str]) -> bool:
        """Check if file type is in the allowed list"""
        if not file_type or not allowed_types:
            return False
        
        return file_type.lower() in [t.lower() for t in allowed_types]
    
    async def _handle_pagination_aiohttp(
        self, 
        soup: BeautifulSoup, 
        site_config: SiteConfig, 
        current_url: str
    ) -> List[ScrapedLink]:
        """Handle pagination for aiohttp scraping"""
        links = []
        
        try:
            next_link = soup.select_one(site_config.pagination.next_button_selector)
            page_count = 1
            
            while (next_link and 
                   page_count < site_config.pagination.max_pages and
                   next_link.get('href')):
                
                next_url = urljoin(current_url, next_link.get('href'))
                logger.debug(f"Following pagination to: {next_url}")
                
                await self._rate_limit(site_config.name, site_config)
                
                async with self.session.get(next_url) as response:
                    if response.status != 200:
                        break
                    
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extract links from this page
                    link_elements = soup.select(site_config.selectors.link_selector)
                    for element in link_elements:
                        link = self._extract_link_info(element, site_config, next_url)
                        if link and self._is_valid_file_type(link.file_type, site_config.file_types):
                            links.append(link)
                    
                    # Find next page link
                    next_link = soup.select_one(site_config.pagination.next_button_selector)
                    page_count += 1
                    
        except Exception as e:
            logger.warning(f"Pagination handling failed: {e}")
        
        return links
    
    async def _handle_pagination_playwright(
        self, 
        page: Page, 
        site_config: SiteConfig, 
        current_url: str
    ) -> List[ScrapedLink]:
        """Handle pagination for Playwright scraping"""
        links = []
        page_count = 1
        
        try:
            while page_count < site_config.pagination.max_pages:
                # Look for next button
                next_button = page.locator(site_config.pagination.next_button_selector)
                
                if not await next_button.is_visible():
                    break
                
                logger.debug(f"Clicking pagination button on page {page_count + 1}")
                
                await self._rate_limit(site_config.name, site_config)
                await next_button.click()
                await page.wait_for_load_state('networkidle')
                
                # Extract links from new page
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                link_elements = soup.select(site_config.selectors.link_selector)
                for element in link_elements:
                    link = self._extract_link_info(element, site_config, page.url)
                    if link and self._is_valid_file_type(link.file_type, site_config.file_types):
                        links.append(link)
                
                page_count += 1
                
        except Exception as e:
            logger.warning(f"Playwright pagination handling failed: {e}")
        
        return links
