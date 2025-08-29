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
        self.llm_filter = None
        if llm_config.enabled:
            try:
                self.llm_filter = LLMBasedFilter(llm_config)
                logger.info("LLM reasoning engine initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize LLM reasoning: {e}")
                logger.warning("Falling back to rule-based reasoning only")
        
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
        if use_llm and self.llm_config.enabled and self.llm_filter:
            try:
                llm_filtered_links, llm_stats = await self.llm_filter.filter_links(
                    rule_filtered_links, site_config
                )
                stats["llm_filtered"] = len(rule_filtered_links) - len(llm_filtered_links)
                stats["reasons"].update(llm_stats.get("reasons", {}))
                final_links = llm_filtered_links
                logger.info(f"LLM filtering applied: {len(llm_filtered_links)}/{len(rule_filtered_links)} links passed")
            except Exception as e:
                logger.error(f"LLM filtering failed: {e}")
                logger.warning("Falling back to rule-based filtering results")
                final_links = rule_filtered_links
        
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


# Phase 2: LLM-based filtering implementation
class LLMBasedFilter:
    """LLM-based filtering engine for sophisticated document relevance reasoning"""
    
    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        self.client = None
        self.chain = None
        
        # Initialize LLM client based on provider
        self._initialize_llm_client()
        logger.info(f"LLM-based filtering initialized with {llm_config.provider} {llm_config.model}")
    
    def _initialize_llm_client(self):
        """Initialize the appropriate LLM client"""
        try:
            if self.config.provider.lower() == "openai":
                from langchain_openai import ChatOpenAI
                self.client = ChatOpenAI(
                    model=self.config.model,
                    api_key=self.config.api_key,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )
            elif self.config.provider.lower() == "anthropic":
                from langchain_anthropic import ChatAnthropic
                self.client = ChatAnthropic(
                    model=self.config.model,
                    api_key=self.config.api_key,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )
            else:
                raise ValueError(f"Unsupported LLM provider: {self.config.provider}")
            
            # Create the reasoning chain
            self._create_reasoning_chain()
            
        except ImportError as e:
            raise Exception(f"Required LLM libraries not installed: {e}")
        except Exception as e:
            raise Exception(f"Failed to initialize LLM client: {e}")
    
    def _create_reasoning_chain(self):
        """Create LangChain reasoning chain for document filtering"""
        from langchain.prompts import PromptTemplate
        from langchain.chains import LLMChain
        
        # Create the filtering prompt template
        prompt_template = """You are an intelligent document filtering agent. Your task is to evaluate whether documents are relevant for download based on the given criteria.

Site Information:
- Site Name: {site_name}
- Target File Types: {file_types}
- Include Keywords: {include_keywords}
- Exclude Keywords: {exclude_keywords}
- Site Purpose: {site_purpose}

Document Links to Evaluate:
{document_links}

For each document, analyze:
1. Title/filename relevance to the include keywords
2. Whether it matches the desired file types
3. If it contains any exclude keywords that make it irrelevant
4. Overall relevance to the site's purpose
5. Document freshness/recency if determinable

Respond with a JSON object containing:
{{
    "filtered_documents": [
        {{
            "url": "document_url",
            "relevance_score": 0.0-1.0,
            "reasoning": "brief explanation of why this document is/isn't relevant",
            "include": true/false
        }}
    ],
    "summary": {{
        "total_evaluated": number,
        "recommended_for_download": number,
        "filtering_criteria_applied": ["list of main criteria used"]
    }}
}}

Be selective but not overly restrictive. Focus on documents that clearly match the intent and criteria."""

        self.prompt = PromptTemplate(
            template=prompt_template,
            input_variables=[
                "site_name", "file_types", "include_keywords", 
                "exclude_keywords", "site_purpose", "document_links"
            ]
        )
        
        self.chain = LLMChain(llm=self.client, prompt=self.prompt)
    
    async def filter_links(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig
    ) -> Tuple[List[ScrapedLink], Dict[str, Any]]:
        """Apply LLM-based filtering to links"""
        if not links:
            return links, {"reasons": {"llm_filter": 0}}
        
        logger.info(f"Applying LLM filtering to {len(links)} links for {site_config.name}")
        
        stats = {
            "reasons": {
                "llm_relevance_filter": 0,
                "llm_low_confidence": 0,
                "llm_processing_error": 0
            },
            "llm_scores": []
        }
        
        try:
            # Process links in batches to avoid token limits
            batch_size = 20  # Adjust based on model context window
            filtered_links = []
            
            for i in range(0, len(links), batch_size):
                batch = links[i:i + batch_size]
                batch_filtered = await self._process_batch(batch, site_config, stats)
                filtered_links.extend(batch_filtered)
            
            logger.info(f"LLM filtering complete: {len(filtered_links)}/{len(links)} links passed")
            return filtered_links, stats
            
        except Exception as e:
            logger.error(f"LLM filtering failed: {e}")
            stats["reasons"]["llm_processing_error"] = len(links)
            return links, stats  # Return original links on error
    
    async def _process_batch(
        self,
        links: List[ScrapedLink],
        site_config: SiteConfig,
        stats: Dict[str, Any]
    ) -> List[ScrapedLink]:
        """Process a batch of links through LLM reasoning"""
        
        # Prepare document information for the prompt
        document_links = []
        for i, link in enumerate(links):
            doc_info = {
                "index": i,
                "url": link.url,
                "title": link.title or "No title",
                "filename": link.filename,
                "file_type": link.file_type,
                "date": link.date or "Unknown date",
                "size": link.size or "Unknown size"
            }
            document_links.append(doc_info)
        
        # Create the prompt inputs
        site_purpose = self._infer_site_purpose(site_config)
        if site_config.llm.custom_instructions:
            site_purpose += f"\n\nSpecial Instructions: {site_config.llm.custom_instructions}"
        
        prompt_inputs = {
            "site_name": site_config.name,
            "file_types": ", ".join(site_config.file_types),
            "include_keywords": ", ".join(site_config.filters.include) if site_config.filters.include else "Any relevant content",
            "exclude_keywords": ", ".join(site_config.filters.exclude) if site_config.filters.exclude else "None specified",
            "site_purpose": site_purpose,
            "document_links": self._format_documents_for_prompt(document_links)
        }
        
        try:
            # Call the LLM
            response = await self._call_llm_async(prompt_inputs)
            
            # Parse the response
            filtered_links = self._parse_llm_response(response, links, stats, site_config)
            return filtered_links
            
        except Exception as e:
            logger.error(f"Error processing batch with LLM: {e}")
            stats["reasons"]["llm_processing_error"] += len(links)
            return links  # Return original batch on error
    
    async def _call_llm_async(self, prompt_inputs: Dict[str, Any]) -> str:
        """Make async call to LLM"""
        import asyncio
        
        # Use asyncio to run the sync LangChain call
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: self.chain.run(**prompt_inputs)
        )
        return response
    
    def _parse_llm_response(
        self,
        response: str,
        original_links: List[ScrapedLink],
        stats: Dict[str, Any],
        site_config: Optional[SiteConfig] = None
    ) -> List[ScrapedLink]:
        """Parse LLM JSON response and filter links"""
        try:
            import json
            
            # Try to extract JSON from response
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            
            result = json.loads(response_clean)
            filtered_documents = result.get("filtered_documents", [])
            
            filtered_links = []
            url_to_link = {link.url: link for link in original_links}
            
            for doc in filtered_documents:
                url = doc.get("url")
                include = doc.get("include", False)
                relevance_score = doc.get("relevance_score", 0.0)
                reasoning = doc.get("reasoning", "")
                
                if url in url_to_link and include:
                    # Use site-specific relevance threshold
                    threshold = site_config.llm.relevance_threshold if site_config else 0.6
                    
                    if relevance_score >= threshold:
                        filtered_links.append(url_to_link[url])
                        stats["llm_scores"].append({
                            "url": url,
                            "score": relevance_score,
                            "reasoning": reasoning
                        })
                    else:
                        stats["reasons"]["llm_low_confidence"] += 1
                else:
                    stats["reasons"]["llm_relevance_filter"] += 1
            
            return filtered_links
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            stats["reasons"]["llm_processing_error"] += len(original_links)
            return original_links
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            stats["reasons"]["llm_processing_error"] += len(original_links)
            return original_links
    
    def _infer_site_purpose(self, site_config: SiteConfig) -> str:
        """Infer the purpose of the site based on configuration"""
        site_name = site_config.name.lower()
        
        if any(term in site_name for term in ["financial", "sec", "edgar", "report"]):
            return "Financial reports and regulatory filings"
        elif any(term in site_name for term in ["data", "dataset", "research"]):
            return "Research data and datasets"
        elif any(term in site_name for term in ["government", "gov", "regulatory"]):
            return "Government documents and regulatory information"
        elif any(term in site_name for term in ["news", "publication"]):
            return "News articles and publications"
        else:
            # Use include keywords to infer purpose
            if site_config.filters.include:
                return f"Documents related to: {', '.join(site_config.filters.include[:3])}"
            return "General document collection"
    
    def _format_documents_for_prompt(self, document_links: List[Dict[str, Any]]) -> str:
        """Format document information for the LLM prompt"""
        formatted = []
        for doc in document_links:
            formatted.append(
                f"Document {doc['index'] + 1}:\n"
                f"  URL: {doc['url']}\n"
                f"  Title: {doc['title']}\n"
                f"  Filename: {doc['filename']}\n"
                f"  Type: {doc['file_type']}\n"
                f"  Date: {doc['date']}\n"
                f"  Size: {doc['size']}\n"
            )
        return "\n".join(formatted)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get LLM usage statistics"""
        # This could be expanded to track token usage, costs, etc.
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "status": "active" if self.client else "inactive"
        }
