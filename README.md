# Web-Scraping & File Retrieval Agent

An intelligent, agentic system for automated web scraping and file retrieval with persistent memory and configurable reasoning.

## Overview

This agent implements the **Perception → Reasoning → Action → Memory** loop to autonomously:
- Scrape websites for downloadable files
- Filter and prioritize content using rule-based and (future) LLM reasoning
- Download files with retry logic and deduplication
- Maintain persistent memory of all operations

## Features

### Phase 1 (Current - MVP)
- ✅ **Rule-based scraping** with configurable selectors
- ✅ **File type filtering** and content-based filtering
- ✅ **Concurrent downloads** with rate limiting
- ✅ **SQLite database** for persistent memory
- ✅ **Docker containerization**
- ✅ **Comprehensive logging** with structured JSON format
- ✅ **Retry logic** and error handling
- ✅ **Robots.txt compliance**

### Phase 2 (Planned)
- 🔄 **LLM-based reasoning** for intelligent filtering
- 🔄 **PostgreSQL support** for production deployments
- 🔄 **Airflow/Prefect integration** for orchestration

### Phase 3 (Future)
- 📋 **Semantic filtering** with embeddings
- 📋 **Multi-agent orchestration**
- 📋 **Cloud storage** (S3) support

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional)

### Installation

1. **Clone and setup:**
```bash
git clone <repository-url>
cd web-agent
pip install -r requirements.txt
```

2. **Install Playwright browsers:**
```bash
playwright install chromium
```

3. **Configure sites:**
Edit `config/sites.yaml` to define target websites:
```yaml
sites:
  - name: "Example Reports"
    url: "https://example.com/reports"
    enabled: true
    file_types: [".pdf", ".csv"]
    filters:
      include: ["2025", "annual"]
      exclude: ["draft", "test"]
```

4. **Run the agent:**
```bash
python -m modules.orchestrator
```

### Docker Usage

1. **Build image:**
```bash
docker build -t web-agent .
```

2. **Run container:**
```bash
docker run -v $(pwd)/data:/app/data -v $(pwd)/config:/app/config web-agent
```

## Configuration

### Global Settings (`config/settings.yaml`)

```yaml
# Database Configuration
database:
  type: "sqlite"  # sqlite or postgres
  sqlite_path: "data/agent_memory.db"

# Storage Configuration  
storage:
  type: "local"  # local or s3
  local_path: "data/downloads"

# Scraping Configuration
scraping:
  user_agent: "WebAgent/1.0"
  timeout_seconds: 30
  max_retries: 3
  respect_robots_txt: true
  rate_limit_delay_seconds: 1
  max_file_size_mb: 100
  concurrent_downloads: 3

# Logging Configuration
logging:
  level: "INFO"
  format: "json"
  log_file: "data/logs/agent.log"
```

### Site Configuration (`config/sites.yaml`)

```yaml
sites:
  - name: "My Target Site"
    url: "https://example.com/data"
    enabled: true
    file_types: [".pdf", ".csv", ".xlsx"]
    
    # Content Filters
    filters:
      include: ["2025", "quarterly", "report"]
      exclude: ["draft", "preliminary"]
    
    # CSS Selectors
    selectors:
      link_selector: "a[href*='.pdf'], a[href*='.csv']"
      title_selector: "a"
      date_selector: ".date"
    
    # Pagination Support
    pagination:
      enabled: true
      next_button_selector: ".next"
      max_pages: 10
    
    # Rate Limiting
    rate_limit:
      requests_per_minute: 30
      delay_between_requests: 2
```

## Usage Examples

### Single Run
```bash
# Process all enabled sites
python -m modules.orchestrator

# Process specific sites
python -m modules.orchestrator --sites "Site 1" "Site 2"

# Show status
python -m modules.orchestrator --status
```

### Continuous Mode
```bash
# Run every 24 hours
python -m modules.orchestrator --continuous --interval 24

# Run every 6 hours
python -m modules.orchestrator --continuous --interval 6
```

### Cleanup
```bash
# Clean up old data and failed downloads
python -m modules.orchestrator --cleanup
```

## Architecture

### Core Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Perception    │───▶│    Reasoning    │───▶│     Action      │
│  (Web Scraper)  │    │ (Filter/Reason) │    │ (File Download) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌─────────────────┐
                    │     Memory      │
                    │ (SQLite/Postgres)│
                    └─────────────────┘
```

### Module Structure

- **`perception.py`** - Web scraping with Playwright/BeautifulSoup
- **`reasoning.py`** - Rule-based filtering and prioritization
- **`action.py`** - File downloads with retry logic
- **`memory.py`** - Database operations and state management
- **`config.py`** - Configuration management with validation
- **`orchestrator.py`** - Main agent loop and coordination
- **`models.py`** - Pydantic and SQLAlchemy data models

## Database Schema

The agent maintains several tables for persistent memory:

- **`download_records`** - Track all download attempts
- **`scrape_sessions`** - Log scraping sessions
- **`visited_urls`** - Prevent re-scraping unchanged pages
- **`error_logs`** - Comprehensive error tracking

## Development

### Running Tests
```bash
pytest tests/
```

### Code Quality
```bash
# Format code
black modules/ tests/

# Lint code
flake8 modules/ tests/

# Type checking
mypy modules/
```

### Adding New Sites

1. Add site configuration to `config/sites.yaml`
2. Test selectors manually or write integration tests
3. Monitor logs for any scraping issues
4. Adjust filters based on results

### Environment Variables

Set these environment variables for production:

```bash
# Database (if using Postgres)
export POSTGRES_PASSWORD="your_password"

# Storage (if using S3)
export S3_BUCKET="your-bucket"
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"

# LLM (Phase 2)
export OPENAI_API_KEY="your_api_key"

# Monitoring
export MONITORING_WEBHOOK_URL="your_webhook"
```

## Monitoring & Observability

### Logs
- **Location:** `data/logs/agent.log`
- **Format:** Structured JSON for easy parsing
- **Rotation:** Automatic with configurable size limits

### Metrics
The agent tracks:
- Download success/failure rates
- Processing time per site
- File sizes and types
- Error frequencies by type and site

### Health Checks
```bash
# Check agent status
python -m modules.orchestrator --status

# Docker health check
docker inspect --format='{{.State.Health.Status}}' <container_id>
```

## Troubleshooting

### Common Issues

**"No links found"**
- Check CSS selectors in site configuration
- Verify the site hasn't changed structure
- Enable debug logging to see scraped content

**"Rate limited"**
- Increase `delay_between_requests` in site config
- Reduce `requests_per_minute` limit
- Check if site requires authentication

**"Download failures"**
- Check file size limits
- Verify network connectivity
- Review error logs for specific failures

**"Database locked"**
- Ensure only one agent instance is running
- Check file permissions on SQLite database
- Consider switching to PostgreSQL for concurrent access

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python -m modules.orchestrator

# Or edit config/settings.yaml:
logging:
  level: "DEBUG"
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure code quality checks pass
5. Submit a pull request

## License

[Your License Here]

## Roadmap

- **Q1 2025:** Phase 2 - LLM integration, PostgreSQL support
- **Q2 2025:** Phase 3 - Semantic filtering, cloud deployment
- **Q3 2025:** Phase 4 - Multi-agent orchestration, enterprise features

## Support

For issues and questions:
- Check the [troubleshooting section](#troubleshooting)
- Review logs in `data/logs/agent.log`
- Open an issue with detailed error information
