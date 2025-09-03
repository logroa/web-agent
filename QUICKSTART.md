# Quick Start Guide

Get the Web Scraping Agent up and running in 5 minutes!

## 🚀 Prerequisites

- Python 3.11 or higher
- Git
- Internet connection

## 📦 Installation

### 1. Clone and Setup
```bash
# Clone the repository
git clone <repository-url>
cd web-agent

# Run the setup script
python setup.py
```

### 2. Verify Installation
```bash
# Run the local test
python test_local.py
```

## 🎯 Quick Test

### Test Basic Functionality
```bash
# Check agent status
python main.py --status
```

### Test with Sample Sites
```bash
# Run with test configuration
python main.py --config-dir config --sites "Test PDF Site"
```

### Check Results
```bash
# View downloaded files
ls -la data/downloads/

# Check logs
tail -f data/logs/agent.log
```

## ⚙️ Configuration

### 1. Edit Site Configuration
Edit `config/sites.yaml` to add your target sites:

```yaml
sites:
  - name: "My Target Site"
    url: "https://example.com/documents"
    enabled: true
    file_types: [".pdf", ".csv"]
    filters:
      include: ["2024", "report"]
      exclude: ["draft", "test"]
    selectors:
      link_selector: "a[href*='.pdf'], a[href*='.csv']"
      title_selector: "a"
```

### 2. Enable LLM Features (Optional)
Edit `.env` file:
```bash
# Add your OpenAI API key
OPENAI_API_KEY=sk-your-openai-api-key-here
```

## 🚀 Usage

### Single Run
```bash
# Run all enabled sites
python main.py

# Run specific sites
python main.py --sites "Site 1" "Site 2"
```

### Continuous Mode
```bash
# Run every 6 hours
python main.py --continuous --interval 6
```

### Verbose Logging
```bash
# Enable debug logging
python main.py --verbose
```

## 📊 Monitoring

### Check Status
```bash
python main.py --status
```

### View Logs
```bash
# Real-time logs
tail -f data/logs/agent.log

# Database queries
sqlite3 data/agent_memory.db "SELECT * FROM download_records ORDER BY created_at DESC LIMIT 10;"
```

## 🔧 Troubleshooting

### Common Issues

**"No links found"**
- Check your CSS selectors in `config/sites.yaml`
- Verify the site structure hasn't changed
- Enable verbose logging: `python main.py --verbose`

**"Download failures"**
- Check network connectivity
- Verify file size limits in `config/settings.yaml`
- Review error logs in `data/logs/agent.log`

**"Rate limited"**
- Increase delays in site configuration
- Reduce `requests_per_minute` in `config/sites.yaml`

### Get Help
```bash
# Show all available options
python main.py --help

# Run tests
python -m pytest tests/ -v
```

## 📁 File Structure

```
web-agent/
├── main.py              # Main entry point
├── setup.py             # Setup script
├── test_local.py        # Local test script
├── config/
│   ├── settings.yaml    # Global settings
│   ├── sites.yaml       # Site configurations
│   └── test_sites.yaml  # Test sites
├── data/
│   ├── downloads/       # Downloaded files
│   ├── logs/           # Log files
│   └── agent_memory.db # SQLite database
└── modules/            # Core agent modules
```

## 🎉 Success!

Your Web Agent is now ready to:
- ✅ Automatically discover downloadable files
- ✅ Intelligently filter content using AI
- ✅ Download files with retry logic
- ✅ Maintain persistent memory of operations
- ✅ Run continuously on a schedule

Start with simple site configurations and gradually add more complex setups!
