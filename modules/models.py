"""
Data models for the Web Agent
Defines Pydantic models for configuration and SQLAlchemy models for persistence
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, HttpUrl, validator
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


# Pydantic Configuration Models
class AuthenticationType(str, Enum):
    BASIC = "basic"
    FORM = "form"
    OAUTH = "oauth"


class StorageType(str, Enum):
    LOCAL = "local"
    S3 = "s3"


class DatabaseType(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class AuthenticationConfig(BaseModel):
    required: bool = False
    type: AuthenticationType = AuthenticationType.BASIC
    username: Optional[str] = None
    password: Optional[str] = None


class PaginationConfig(BaseModel):
    enabled: bool = False
    next_button_selector: str = ".next"
    max_pages: int = 10


class SelectorsConfig(BaseModel):
    link_selector: str = "a[href*='.pdf']"
    title_selector: str = "a"
    date_selector: Optional[str] = None


class FiltersConfig(BaseModel):
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)


class RateLimitConfig(BaseModel):
    requests_per_minute: int = 30
    delay_between_requests: int = 2


class LLMSiteConfig(BaseModel):
    use_llm: bool = True
    relevance_threshold: float = 0.6
    custom_instructions: Optional[str] = None


class SiteConfig(BaseModel):
    name: str
    url: HttpUrl
    enabled: bool = True
    file_types: List[str] = Field(default_factory=lambda: [".pdf"])
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    selectors: SelectorsConfig = Field(default_factory=SelectorsConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    authentication: AuthenticationConfig = Field(default_factory=AuthenticationConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    llm: LLMSiteConfig = Field(default_factory=LLMSiteConfig)

    @validator('file_types')
    def validate_file_types(cls, v):
        """Ensure file types start with a dot"""
        return [ext if ext.startswith('.') else f'.{ext}' for ext in v]


class DatabaseConfig(BaseModel):
    type: DatabaseType = DatabaseType.SQLITE
    sqlite_path: str = "data/agent_memory.db"
    postgres: Optional[Dict[str, Any]] = None


class StorageConfig(BaseModel):
    type: StorageType = StorageType.LOCAL
    local_path: str = "data/downloads"
    s3: Optional[Dict[str, Any]] = None


class ScrapingConfig(BaseModel):
    user_agent: str = "WebAgent/1.0"
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: int = 5
    respect_robots_txt: bool = True
    rate_limit_delay_seconds: int = 1
    max_file_size_mb: int = 100
    concurrent_downloads: int = 3


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    log_file: str = "data/logs/agent.log"
    max_log_size_mb: int = 10
    backup_count: int = 5


class LLMConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    api_key: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.1


class MonitoringConfig(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = None
    alert_on_failure_rate: float = 0.1


class AgentSettings(BaseModel):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


class SitesConfig(BaseModel):
    sites: List[SiteConfig]


# SQLAlchemy Database Models
class DownloadRecord(Base):
    """Record of downloaded files"""
    __tablename__ = "download_records"

    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String(255), nullable=False, index=True)
    url = Column(String(2048), nullable=False, unique=True, index=True)
    filename = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_size_bytes = Column(Integer)
    content_type = Column(String(128))
    downloaded_at = Column(DateTime(timezone=True), server_default=func.now())
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    checksum = Column(String(64))  # SHA-256 hash


class ScrapeSession(Base):
    """Record of scraping sessions"""
    __tablename__ = "scrape_sessions"

    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String(255), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    success = Column(Boolean)
    pages_scraped = Column(Integer, default=0)
    files_found = Column(Integer, default=0)
    files_downloaded = Column(Integer, default=0)
    files_failed = Column(Integer, default=0)
    error_message = Column(Text)


class VisitedUrl(Base):
    """Track visited URLs to avoid re-scraping"""
    __tablename__ = "visited_urls"

    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String(255), nullable=False, index=True)
    url = Column(String(2048), nullable=False, index=True)
    visited_at = Column(DateTime(timezone=True), server_default=func.now())
    content_hash = Column(String(64))  # Hash of page content to detect changes


class ErrorLog(Base):
    """Log of errors and exceptions"""
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    site_name = Column(String(255), index=True)
    error_type = Column(String(128), nullable=False)
    error_message = Column(Text, nullable=False)
    url = Column(String(2048))
    stack_trace = Column(Text)
    retry_count = Column(Integer, default=0)
