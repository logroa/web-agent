"""
Tests for configuration management
"""

import pytest
import tempfile
import yaml
from pathlib import Path

from modules.config import ConfigManager, ConfigurationError
from modules.models import AgentSettings, SitesConfig


class TestConfigManager:
    
    def test_load_default_settings(self):
        """Test loading default settings when no file exists"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_manager = ConfigManager(temp_dir)
            settings = config_manager.load_settings()
            
            assert isinstance(settings, AgentSettings)
            assert settings.database.type == "sqlite"
            assert settings.scraping.max_retries == 3
    
    def test_load_settings_from_file(self):
        """Test loading settings from YAML file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            settings_file = config_dir / "settings.yaml"
            
            # Create test settings
            test_config = {
                "database": {"type": "postgres"},
                "scraping": {"max_retries": 5}
            }
            
            with open(settings_file, 'w') as f:
                yaml.dump(test_config, f)
            
            config_manager = ConfigManager(temp_dir)
            settings = config_manager.load_settings()
            
            assert settings.database.type == "postgres"
            assert settings.scraping.max_retries == 5
    
    def test_load_sites_configuration(self):
        """Test loading sites configuration"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            sites_file = config_dir / "sites.yaml"
            
            # Create test sites config
            test_config = {
                "sites": [
                    {
                        "name": "Test Site",
                        "url": "https://example.com",
                        "file_types": [".pdf", ".csv"]
                    }
                ]
            }
            
            with open(sites_file, 'w') as f:
                yaml.dump(test_config, f)
            
            config_manager = ConfigManager(temp_dir)
            sites = config_manager.load_sites()
            
            assert isinstance(sites, SitesConfig)
            assert len(sites.sites) == 1
            assert sites.sites[0].name == "Test Site"
            assert sites.sites[0].url == "https://example.com"
    
    def test_environment_variable_substitution(self):
        """Test environment variable substitution"""
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            settings_file = config_dir / "settings.yaml"
            
            # Set test environment variable
            os.environ["TEST_DB_PATH"] = "/test/path/db.sqlite"
            
            try:
                test_config = {
                    "database": {
                        "sqlite_path": "${TEST_DB_PATH}"
                    }
                }
                
                with open(settings_file, 'w') as f:
                    yaml.dump(test_config, f)
                
                config_manager = ConfigManager(temp_dir)
                settings = config_manager.load_settings()
                
                assert settings.database.sqlite_path == "/test/path/db.sqlite"
                
            finally:
                del os.environ["TEST_DB_PATH"]
    
    def test_get_enabled_sites(self):
        """Test filtering enabled sites"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            sites_file = config_dir / "sites.yaml"
            
            test_config = {
                "sites": [
                    {"name": "Site 1", "url": "https://example1.com", "enabled": True},
                    {"name": "Site 2", "url": "https://example2.com", "enabled": False},
                    {"name": "Site 3", "url": "https://example3.com", "enabled": True}
                ]
            }
            
            with open(sites_file, 'w') as f:
                yaml.dump(test_config, f)
            
            config_manager = ConfigManager(temp_dir)
            config_manager.load_sites()
            
            enabled_sites = config_manager.get_enabled_sites()
            assert len(enabled_sites) == 2
            assert enabled_sites[0].name == "Site 1"
            assert enabled_sites[1].name == "Site 3"
    
    def test_invalid_yaml_handling(self):
        """Test handling of invalid YAML"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            settings_file = config_dir / "settings.yaml"
            
            # Create invalid YAML
            with open(settings_file, 'w') as f:
                f.write("invalid: yaml: content: [")
            
            config_manager = ConfigManager(temp_dir)
            
            with pytest.raises(ConfigurationError):
                config_manager.load_settings()


if __name__ == "__main__":
    pytest.main([__file__])
