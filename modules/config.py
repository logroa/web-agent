"""
Configuration management for the Web Agent
Handles loading and validation of YAML configuration files
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from pydantic import ValidationError

from .models import AgentSettings, SitesConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages loading and validation of configuration files"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.settings: Optional[AgentSettings] = None
        self.sites: Optional[SitesConfig] = None
    
    def load_settings(self, settings_file: str = "settings.yaml") -> AgentSettings:
        """Load and validate global settings"""
        settings_path = self.config_dir / settings_file
        
        if not settings_path.exists():
            logger.warning(f"Settings file not found: {settings_path}. Using defaults.")
            self.settings = AgentSettings()
            return self.settings
        
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f)
            
            # Substitute environment variables
            processed_config = self._substitute_env_vars(raw_config)
            
            self.settings = AgentSettings(**processed_config)
            logger.info(f"Loaded settings from {settings_path}")
            return self.settings
            
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML in {settings_path}: {e}")
            raise ConfigurationError(f"Invalid YAML syntax: {e}")
        
        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ConfigurationError(f"Configuration validation failed: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error loading settings: {e}")
            raise ConfigurationError(f"Failed to load settings: {e}")
    
    def load_sites(self, sites_file: str = "sites.yaml") -> SitesConfig:
        """Load and validate site configurations"""
        sites_path = self.config_dir / sites_file
        
        if not sites_path.exists():
            logger.error(f"Sites file not found: {sites_path}")
            raise ConfigurationError(f"Sites configuration file not found: {sites_path}")
        
        try:
            with open(sites_path, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f)
            
            # Substitute environment variables
            processed_config = self._substitute_env_vars(raw_config)
            
            self.sites = SitesConfig(**processed_config)
            logger.info(f"Loaded {len(self.sites.sites)} site configurations from {sites_path}")
            
            # Log enabled sites
            enabled_sites = [site.name for site in self.sites.sites if site.enabled]
            logger.info(f"Enabled sites: {enabled_sites}")
            
            return self.sites
            
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML in {sites_path}: {e}")
            raise ConfigurationError(f"Invalid YAML syntax: {e}")
        
        except ValidationError as e:
            logger.error(f"Site configuration validation failed: {e}")
            raise ConfigurationError(f"Site configuration validation failed: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error loading sites: {e}")
            raise ConfigurationError(f"Failed to load sites: {e}")
    
    def _substitute_env_vars(self, config: Any) -> Any:
        """Recursively substitute environment variables in configuration"""
        if isinstance(config, dict):
            return {key: self._substitute_env_vars(value) for key, value in config.items()}
        elif isinstance(config, list):
            return [self._substitute_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
            # Extract environment variable name
            env_var = config[2:-1]  # Remove ${ and }
            default_value = None
            
            # Handle default values: ${VAR_NAME:default_value}
            if ":" in env_var:
                env_var, default_value = env_var.split(":", 1)
            
            value = os.getenv(env_var, default_value)
            if value is None:
                logger.warning(f"Environment variable {env_var} not set and no default provided")
            return value
        else:
            return config
    
    def get_enabled_sites(self) -> list:
        """Get list of enabled site configurations"""
        if not self.sites:
            raise ConfigurationError("Sites not loaded. Call load_sites() first.")
        
        return [site for site in self.sites.sites if site.enabled]
    
    def get_site_by_name(self, name: str):
        """Get a specific site configuration by name"""
        if not self.sites:
            raise ConfigurationError("Sites not loaded. Call load_sites() first.")
        
        for site in self.sites.sites:
            if site.name == name:
                return site
        
        raise ConfigurationError(f"Site '{name}' not found in configuration")
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate the complete configuration and return validation results"""
        results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Check if settings are loaded
        if not self.settings:
            try:
                self.load_settings()
            except Exception as e:
                results["valid"] = False
                results["errors"].append(f"Failed to load settings: {e}")
        
        # Check if sites are loaded
        if not self.sites:
            try:
                self.load_sites()
            except Exception as e:
                results["valid"] = False
                results["errors"].append(f"Failed to load sites: {e}")
        
        # Validate directory paths exist
        if self.settings:
            # Check storage path
            storage_path = Path(self.settings.storage.local_path)
            if not storage_path.exists():
                try:
                    storage_path.mkdir(parents=True, exist_ok=True)
                    results["warnings"].append(f"Created storage directory: {storage_path}")
                except Exception as e:
                    results["errors"].append(f"Cannot create storage directory {storage_path}: {e}")
                    results["valid"] = False
            
            # Check log directory
            log_path = Path(self.settings.logging.log_file).parent
            if not log_path.exists():
                try:
                    log_path.mkdir(parents=True, exist_ok=True)
                    results["warnings"].append(f"Created log directory: {log_path}")
                except Exception as e:
                    results["errors"].append(f"Cannot create log directory {log_path}: {e}")
                    results["valid"] = False
        
        # Check for enabled sites
        if self.sites:
            enabled_sites = self.get_enabled_sites()
            if not enabled_sites:
                results["warnings"].append("No sites are enabled in configuration")
        
        return results
    
    def reload_configuration(self):
        """Reload both settings and sites configuration"""
        logger.info("Reloading configuration...")
        self.settings = None
        self.sites = None
        self.load_settings()
        self.load_sites()
        logger.info("Configuration reloaded successfully")


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors"""
    pass


# Utility functions for configuration management
def create_default_config_files(config_dir: str = "config"):
    """Create default configuration files if they don't exist"""
    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)
    
    settings_file = config_path / "settings.yaml"
    sites_file = config_path / "sites.yaml"
    
    if not settings_file.exists():
        logger.info(f"Creating default settings file: {settings_file}")
        # This would be created with default values
        # Implementation depends on whether you want to write defaults
        pass
    
    if not sites_file.exists():
        logger.info(f"Creating default sites file: {sites_file}")
        # This would be created with example site
        pass


def load_env_file(env_file: str = ".env"):
    """Load environment variables from a .env file"""
    env_path = Path(env_file)
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            logger.info(f"Loaded environment variables from {env_path}")
        except ImportError:
            logger.warning("python-dotenv not installed, skipping .env file loading")
        except Exception as e:
            logger.error(f"Failed to load .env file: {e}")
    else:
        logger.debug(f".env file not found: {env_path}")
