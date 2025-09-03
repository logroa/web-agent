#!/usr/bin/env python3
"""
Setup script for Web-Scraping & File Retrieval Agent
Helps with initial setup and configuration
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 11):
        print("❌ Python 3.11+ is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True


def install_dependencies():
    """Install required dependencies"""
    print("📦 Installing dependencies...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


def install_playwright():
    """Install Playwright browsers"""
    print("🌐 Installing Playwright browsers...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("✅ Playwright browsers installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Playwright: {e}")
        return False


def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")
    
    directories = [
        "data",
        "data/downloads",
        "data/logs",
        "config"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created: {directory}")


def setup_environment():
    """Setup environment variables"""
    print("🔧 Setting up environment...")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("📝 Creating .env file...")
        
        env_content = """# Web Agent Environment Variables
# Uncomment and set your API keys to enable LLM features

# OpenAI API Key (for GPT-4o-mini)
# OPENAI_API_KEY=sk-your-openai-api-key-here

# Anthropic API Key (for Claude)
# ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here

# PostgreSQL (optional, for production)
# POSTGRES_PASSWORD=your-postgres-password

# AWS S3 (optional, for cloud storage)
# S3_BUCKET=your-s3-bucket
# AWS_ACCESS_KEY_ID=your-aws-key
# AWS_SECRET_ACCESS_KEY=your-aws-secret

# Monitoring (optional)
# MONITORING_WEBHOOK_URL=your-webhook-url
"""
        
        with open(env_file, 'w') as f:
            f.write(env_content)
        
        print("✅ Created .env file")
        print("   Edit .env to add your API keys for LLM features")
    else:
        print("✅ .env file already exists")


def create_test_config():
    """Create test configuration for initial testing"""
    print("🧪 Setting up test configuration...")
    
    # Copy test sites if it doesn't exist
    test_sites = Path("config/test_sites.yaml")
    if not test_sites.exists():
        print("❌ Test sites configuration not found")
        return False
    
    print("✅ Test configuration ready")
    return True


def run_tests():
    """Run basic tests"""
    print("🧪 Running basic tests...")
    
    try:
        # Test configuration loading
        subprocess.check_call([sys.executable, "-m", "pytest", "tests/test_config.py", "-v"])
        print("✅ Configuration tests passed")
        
        # Test memory module
        subprocess.check_call([sys.executable, "-m", "pytest", "tests/test_memory.py", "-v"])
        print("✅ Memory tests passed")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Some tests failed: {e}")
        return False


def main():
    """Main setup function"""
    print("🚀 Web Agent Setup")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Install Playwright
    if not install_playwright():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Setup environment
    setup_environment()
    
    # Create test config
    if not create_test_config():
        print("⚠️  Test configuration not found")
    
    # Run tests
    print("\n🧪 Running tests...")
    if run_tests():
        print("✅ All tests passed")
    else:
        print("⚠️  Some tests failed, but setup can continue")
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Edit .env file to add your API keys (optional)")
    print("2. Edit config/sites.yaml to configure your target sites")
    print("3. Run: python main.py --status")
    print("4. Run: python main.py --config-dir config --sites 'Test PDF Site'")
    print("5. Check data/downloads/ for downloaded files")


if __name__ == "__main__":
    main()
