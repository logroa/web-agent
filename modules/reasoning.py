"""
Reasoning module for the Web Agent
Handles rule-based filtering and decision-making for file downloads
Phase 2 will add LLM-based reasoning
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, unquote

from .models import SiteConfig, LLMConfig
from .perception import ScrapedLink
from .memory import MemoryManager

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """Main reasoning engine for filtering and prioritizing downloads"""
    
    def __init__(
        self,
        llm_config: LLMConfig,
        memory_manager: MemoryManager
    ):
        self.llm_config = llm_config
        self.memory = memory_manager
        self.rule_filters = RuleBasedFilter()
        
        # Initialize LLM reasoning if enabled (Phase 2)
        if llm_config.enabled:
            logger.warning("LLM reasoning is enabled but not yet implemented (Phase 2 feature)")
            # self.llm_filter = LLMBasedFilter(llm_config)
        
        logger.info(f"ReasoningEngine initialized (LLM: {'enabled' if llm_config.enabled else 'disabled'})")
    
    async def filter_links(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig,
        use_llm: bool = False
    ) -> Tuple[List[ScrapedLink], Dict[str, Any]]:
        """
        Filter links based on site configuration and reasoning
        
        Returns:
            Tuple of (filtered_links, filtering_stats)
        """
        logger.info(f"Filtering {len(links)} links for site: {site_config.name}")
        
        stats = {
            "total_links": len(links),
            "filtered_links": 0,
            "duplicate_links": 0,
            "already_downloaded": 0,
            "rule_filtered": 0,
            "llm_filtered": 0,
            "reasons": {}
        }
        
        # Step 1: Remove duplicates
        unique_links = self._remove_duplicates(links)
        stats["duplicate_links"] = len(links) - len(unique_links)
        
        # Step 2: Check against download history
        new_links = await self._filter_already_downloaded(unique_links)
        stats["already_downloaded"] = len(unique_links) - len(new_links)
        
        # Step 3: Apply rule-based filtering
        rule_filtered_links, rule_stats = self.rule_filters.filter_links(
            new_links, site_config
        )
        stats["rule_filtered"] = len(new_links) - len(rule_filtered_links)
        stats["reasons"].update(rule_stats.get("reasons", {}))
        
        # Step 4: Apply LLM filtering if enabled (Phase 2)
        final_links = rule_filtered_links
        if use_llm and self.llm_config.enabled:
            # llm_filtered_links, llm_stats = await self.llm_filter.filter_links(
            #     rule_filtered_links, site_config
            # )
            # stats["llm_filtered"] = len(rule_filtered_links) - len(llm_filtered_links)
            # final_links = llm_filtered_links
            logger.warning("LLM filtering requested but not implemented yet")
        
        stats["filtered_links"] = len(final_links)
        
        logger.info(f"Filtering complete: {stats['filtered_links']}/{stats['total_links']} links passed")
        return final_links, stats
    
    def _remove_duplicates(self, links: List[ScrapedLink]) -> List[ScrapedLink]:
        """Remove duplicate links based on URL"""
        seen_urls = set()
        unique_links = []
        
        for link in links:
            if link.url not in seen_urls:
                seen_urls.add(link.url)
                unique_links.append(link)
        
        if len(unique_links) < len(links):
            logger.debug(f"Removed {len(links) - len(unique_links)} duplicate links")
        
        return unique_links
    
    async def _filter_already_downloaded(self, links: List[ScrapedLink]) -> List[ScrapedLink]:
        """Filter out links that have already been downloaded"""
        new_links = []
        
        for link in links:
            if not await self.memory.is_already_downloaded(link.url):
                new_links.append(link)
        
        if len(new_links) < len(links):
            logger.debug(f"Filtered out {len(links) - len(new_links)} already downloaded links")
        
        return new_links
    
    def prioritize_links(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig
    ) -> List[ScrapedLink]:
        """Prioritize links based on various factors"""
        logger.debug(f"Prioritizing {len(links)} links")
        
        def priority_score(link: ScrapedLink) -> float:
            score = 0.0
            
            # File type priority (PDF > CSV > others)
            if link.file_type == '.pdf':
                score += 10
            elif link.file_type in ['.csv', '.xlsx']:
                score += 8
            elif link.file_type in ['.json', '.xml']:
                score += 6
            else:
                score += 1
            
            # Date priority (newer is better)
            date_score = self._calculate_date_score(link.date)
            score += date_score
            
            # Size priority (reasonable sizes preferred)
            size_score = self._calculate_size_score(link.size)
            score += size_score
            
            # Title/content relevance
            relevance_score = self._calculate_relevance_score(link, site_config)
            score += relevance_score
            
            return score
        
        # Sort by priority score (highest first)
        prioritized_links = sorted(links, key=priority_score, reverse=True)
        
        logger.debug(f"Links prioritized by score")
        return prioritized_links
    
    def _calculate_date_score(self, date_str: str) -> float:
        """Calculate priority score based on date"""
        if not date_str:
            return 0.0
        
        try:
            # Try to parse various date formats
            date_patterns = [
                r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
                r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
                r'(\d{1,2}/\d{1,2}/\d{2,4})',  # M/D/YY or MM/DD/YYYY
                r'(\d{4})',  # Just year
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, date_str)
                if match:
                    date_part = match.group(1)
                    
                    # Parse based on pattern
                    if '-' in date_part:  # YYYY-MM-DD
                        parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                    elif '/' in date_part and len(date_part.split('/')[2]) == 4:  # MM/DD/YYYY
                        parsed_date = datetime.strptime(date_part, '%m/%d/%Y')
                    elif len(date_part) == 4:  # Just year
                        parsed_date = datetime.strptime(date_part, '%Y')
                    else:
                        continue
                    
                    # Calculate score based on how recent it is
                    days_old = (datetime.now() - parsed_date).days
                    if days_old < 30:
                        return 5.0  # Very recent
                    elif days_old < 90:
                        return 3.0  # Recent
                    elif days_old < 365:
                        return 1.0  # This year
                    else:
                        return 0.5  # Older
            
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")
        
        return 0.0
    
    def _calculate_size_score(self, size_str: str) -> float:
        """Calculate priority score based on file size"""
        if not size_str:
            return 0.0
        
        try:
            # Extract size and unit
            size_pattern = r'(\d+(?:\.\d+)?)\s*(kb|mb|gb|bytes?)?'
            match = re.search(size_pattern, size_str.lower())
            
            if match:
                size_value = float(match.group(1))
                unit = match.group(2) or 'bytes'
                
                # Convert to MB for comparison
                if unit in ['kb', 'kilobytes']:
                    size_mb = size_value / 1024
                elif unit in ['mb', 'megabytes']:
                    size_mb = size_value
                elif unit in ['gb', 'gigabytes']:
                    size_mb = size_value * 1024
                else:  # bytes
                    size_mb = size_value / (1024 * 1024)
                
                # Score based on reasonable size ranges
                if 0.1 <= size_mb <= 50:  # 100KB to 50MB - good range
                    return 2.0
                elif size_mb <= 100:  # Up to 100MB - acceptable
                    return 1.0
                elif size_mb <= 500:  # Up to 500MB - large but okay
                    return 0.5
                else:  # Very large files
                    return -1.0
            
        except Exception as e:
            logger.debug(f"Failed to parse size '{size_str}': {e}")
        
        return 0.0
    
    def _calculate_relevance_score(self, link: ScrapedLink, site_config: SiteConfig) -> float:
        """Calculate relevance score based on title and filters"""
        score = 0.0
        
        # Check title and text against include filters
        text_to_check = f"{link.title} {link.text} {link.filename}".lower()
        
        for include_term in site_config.filters.include:
            if include_term.lower() in text_to_check:
                score += 2.0
        
        # Penalize exclude terms
        for exclude_term in site_config.filters.exclude:
            if exclude_term.lower() in text_to_check:
                score -= 5.0
        
        return score


class RuleBasedFilter:
    """Rule-based filtering engine"""
    
    def filter_links(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig
    ) -> Tuple[List[ScrapedLink], Dict[str, Any]]:
        """Apply rule-based filtering to links"""
        
        filtered_links = []
        stats = {
            "reasons": {
                "include_filter": 0,
                "exclude_filter": 0,
                "file_type_filter": 0,
                "url_pattern_filter": 0
            }
        }
        
        for link in links:
            # Check file type
            if not self._check_file_type(link, site_config.file_types):
                stats["reasons"]["file_type_filter"] += 1
                continue
            
            # Check include filters
            if site_config.filters.include and not self._check_include_filters(link, site_config.filters.include):
                stats["reasons"]["include_filter"] += 1
                continue
            
            # Check exclude filters
            if site_config.filters.exclude and self._check_exclude_filters(link, site_config.filters.exclude):
                stats["reasons"]["exclude_filter"] += 1
                continue
            
            # Check URL patterns (basic validation)
            if not self._check_url_validity(link):
                stats["reasons"]["url_pattern_filter"] += 1
                continue
            
            filtered_links.append(link)
        
        return filtered_links, stats
    
    def _check_file_type(self, link: ScrapedLink, allowed_types: List[str]) -> bool:
        """Check if link file type is allowed"""
        if not allowed_types:
            return True
        
        return link.file_type.lower() in [t.lower() for t in allowed_types]
    
    def _check_include_filters(self, link: ScrapedLink, include_terms: List[str]) -> bool:
        """Check if link matches any include filter"""
        if not include_terms:
            return True
        
        text_to_check = f"{link.title} {link.text} {link.filename} {link.url}".lower()
        
        return any(term.lower() in text_to_check for term in include_terms)
    
    def _check_exclude_filters(self, link: ScrapedLink, exclude_terms: List[str]) -> bool:
        """Check if link matches any exclude filter (returns True if should be excluded)"""
        if not exclude_terms:
            return False
        
        text_to_check = f"{link.title} {link.text} {link.filename} {link.url}".lower()
        
        return any(term.lower() in text_to_check for term in exclude_terms)
    
    def _check_url_validity(self, link: ScrapedLink) -> bool:
        """Basic URL validation"""
        try:
            parsed = urlparse(link.url)
            
            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Scheme must be http or https
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Decode URL and check for suspicious patterns
            decoded_url = unquote(link.url)
            
            # Check for suspicious patterns
            suspicious_patterns = [
                'javascript:',
                'data:',
                'mailto:',
                'ftp:',
                'file:',
                'tel:'
            ]
            
            if any(pattern in decoded_url.lower() for pattern in suspicious_patterns):
                return False
            
            return True
            
        except Exception:
            return False


# Phase 2: LLM-based filtering (placeholder for future implementation)
class LLMBasedFilter:
    """LLM-based filtering engine for more sophisticated reasoning"""
    
    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        # Initialize LLM client here
        logger.info("LLM-based filtering initialized (Phase 2 feature)")
    
    async def filter_links(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig
    ) -> Tuple[List[ScrapedLink], Dict[str, Any]]:
        """Apply LLM-based filtering to links"""
        # Placeholder for Phase 2 implementation
        logger.warning("LLM filtering called but not implemented yet")
        return links, {"reasons": {"llm_filter": 0}}
    
    def _create_filtering_prompt(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig
    ) -> str:
        """Create prompt for LLM-based filtering"""
        # This will be implemented in Phase 2
        pass
    
    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Call LLM API for reasoning"""
        # This will be implemented in Phase 2
        pass
