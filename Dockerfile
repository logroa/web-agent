# Web-Scraping & File Retrieval Agent
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright dependencies
RUN pip install --no-cache-dir playwright==1.40.0 && \
    playwright install --with-deps chromium

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/downloads data/logs config

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash agent && \
    chown -R agent:agent /app
USER agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from modules.orchestrator import AgentOrchestrator; \
    async def check(): \
        o = AgentOrchestrator(); \
        await o.initialize(); \
        status = await o.get_status(); \
        assert status.get('initialized', False)" \
    && asyncio.run(check()) || exit 1

# Default command
CMD ["python", "-m", "modules.orchestrator"]
