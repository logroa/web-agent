"""
Memory module for the Web Agent
Handles database operations and persistent state management
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from sqlalchemy import create_engine, and_, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from .models import (
    Base, DownloadRecord, ScrapeSession, VisitedUrl, ErrorLog,
    DatabaseConfig, DatabaseType
)

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages persistent storage and retrieval of agent state"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._create_tables()
    
    def _create_engine(self):
        """Create database engine based on configuration"""
        if self.config.type == DatabaseType.SQLITE:
            # Ensure directory exists
            db_path = Path(self.config.sqlite_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            database_url = f"sqlite:///{self.config.sqlite_path}"
            engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False}  # SQLite specific
            )
        elif self.config.type == DatabaseType.POSTGRES:
            if not self.config.postgres:
                raise ValueError("Postgres configuration required when type is postgres")
            
            pg_config = self.config.postgres
            database_url = (
                f"postgresql://{pg_config['username']}:{pg_config['password']}"
                f"@{pg_config['host']}:{pg_config['port']}/{pg_config['database']}"
            )
            engine = create_engine(database_url)
        else:
            raise ValueError(f"Unsupported database type: {self.config.type}")
        
        logger.info(f"Created database engine for {self.config.type}")
        return engine
    
    def _create_tables(self):
        """Create database tables if they don't exist"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created/verified")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def record_download(
        self,
        site_name: str,
        url: str,
        filename: str,
        file_path: str,
        file_size_bytes: Optional[int] = None,
        content_type: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        checksum: Optional[str] = None
    ) -> DownloadRecord:
        """Record a file download attempt"""
        with self.get_session() as session:
            download_record = DownloadRecord(
                site_name=site_name,
                url=url,
                filename=filename,
                file_path=file_path,
                file_size_bytes=file_size_bytes,
                content_type=content_type,
                success=success,
                error_message=error_message,
                retry_count=retry_count,
                checksum=checksum
            )
            session.add(download_record)
            session.flush()  # Get the ID
            logger.info(f"Recorded download: {filename} ({'success' if success else 'failed'})")
            return download_record
    
    def is_already_downloaded(self, url: str) -> bool:
        """Check if a URL has already been successfully downloaded"""
        with self.get_session() as session:
            record = session.query(DownloadRecord).filter(
                and_(DownloadRecord.url == url, DownloadRecord.success == True)
            ).first()
            return record is not None
    
    def get_download_history(self, site_name: Optional[str] = None, limit: int = 100) -> List[DownloadRecord]:
        """Get download history, optionally filtered by site"""
        with self.get_session() as session:
            query = session.query(DownloadRecord)
            if site_name:
                query = query.filter(DownloadRecord.site_name == site_name)
            
            records = query.order_by(desc(DownloadRecord.downloaded_at)).limit(limit).all()
            return records
    
    def start_scrape_session(self, site_name: str) -> ScrapeSession:
        """Start a new scraping session"""
        with self.get_session() as session:
            scrape_session = ScrapeSession(site_name=site_name)
            session.add(scrape_session)
            session.flush()
            logger.info(f"Started scrape session for {site_name}")
            return scrape_session
    
    def complete_scrape_session(
        self,
        session_id: int,
        success: bool = True,
        pages_scraped: int = 0,
        files_found: int = 0,
        files_downloaded: int = 0,
        files_failed: int = 0,
        error_message: Optional[str] = None
    ):
        """Complete a scraping session with results"""
        with self.get_session() as session:
            scrape_session = session.query(ScrapeSession).filter(
                ScrapeSession.id == session_id
            ).first()
            
            if scrape_session:
                scrape_session.completed_at = datetime.utcnow()
                scrape_session.success = success
                scrape_session.pages_scraped = pages_scraped
                scrape_session.files_found = files_found
                scrape_session.files_downloaded = files_downloaded
                scrape_session.files_failed = files_failed
                scrape_session.error_message = error_message
                
                logger.info(f"Completed scrape session {session_id}: "
                          f"{files_downloaded}/{files_found} files downloaded")
    
    def record_visited_url(self, site_name: str, url: str, content_hash: Optional[str] = None):
        """Record that a URL has been visited"""
        with self.get_session() as session:
            # Check if already exists
            existing = session.query(VisitedUrl).filter(
                and_(VisitedUrl.site_name == site_name, VisitedUrl.url == url)
            ).first()
            
            if existing:
                existing.visited_at = datetime.utcnow()
                existing.content_hash = content_hash
            else:
                visited_url = VisitedUrl(
                    site_name=site_name,
                    url=url,
                    content_hash=content_hash
                )
                session.add(visited_url)
    
    def is_url_visited(self, site_name: str, url: str) -> bool:
        """Check if a URL has been visited"""
        with self.get_session() as session:
            record = session.query(VisitedUrl).filter(
                and_(VisitedUrl.site_name == site_name, VisitedUrl.url == url)
            ).first()
            return record is not None
    
    def log_error(
        self,
        error_type: str,
        error_message: str,
        site_name: Optional[str] = None,
        url: Optional[str] = None,
        stack_trace: Optional[str] = None,
        retry_count: int = 0
    ):
        """Log an error to the database"""
        with self.get_session() as session:
            error_log = ErrorLog(
                site_name=site_name,
                error_type=error_type,
                error_message=error_message,
                url=url,
                stack_trace=stack_trace,
                retry_count=retry_count
            )
            session.add(error_log)
            logger.error(f"Logged error: {error_type} - {error_message}")
    
    def get_error_stats(self, site_name: Optional[str] = None, hours: int = 24) -> Dict[str, Any]:
        """Get error statistics for the specified time period"""
        with self.get_session() as session:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            query = session.query(ErrorLog).filter(ErrorLog.timestamp >= cutoff_time)
            if site_name:
                query = query.filter(ErrorLog.site_name == site_name)
            
            errors = query.all()
            
            stats = {
                "total_errors": len(errors),
                "error_types": {},
                "sites": {}
            }
            
            for error in errors:
                # Count by error type
                if error.error_type not in stats["error_types"]:
                    stats["error_types"][error.error_type] = 0
                stats["error_types"][error.error_type] += 1
                
                # Count by site
                if error.site_name:
                    if error.site_name not in stats["sites"]:
                        stats["sites"][error.site_name] = 0
                    stats["sites"][error.site_name] += 1
            
            return stats
    
    def cleanup_old_records(self, days: int = 30):
        """Clean up old records to prevent database bloat"""
        with self.get_session() as session:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Clean up old error logs
            deleted_errors = session.query(ErrorLog).filter(
                ErrorLog.timestamp < cutoff_date
            ).delete()
            
            # Clean up old visited URLs
            deleted_urls = session.query(VisitedUrl).filter(
                VisitedUrl.visited_at < cutoff_date
            ).delete()
            
            logger.info(f"Cleaned up {deleted_errors} error logs and {deleted_urls} visited URLs")
    
    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """Calculate SHA-256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    @staticmethod
    def calculate_content_hash(content: str) -> str:
        """Calculate SHA-256 hash of string content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
