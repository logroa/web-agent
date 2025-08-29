# Product Requirements Document (PRD)  
**Project:** Web-Scraping & File Retrieval Agent  
**Owner:** Logan Roach  
**Date:** August 2025  

---

## 1. Problem Statement  

Organizations often need to **retrieve structured/unstructured documents from the web** (e.g., financial reports, datasets, policy documents). Manual scraping and downloading are inefficient and error-prone. Current solutions (ad-hoc scripts, one-off scrapers) lack **extensibility, logging, error recovery, and autonomous decision-making**.  

This project aims to build an **agentic AI system** that:  
- Scrapes websites.  
- Interprets and filters content.  
- Downloads relevant files.  
- Persists memory of past work.  
- Operates autonomously on a schedule.  

---

## 2. Goals & Objectives  

### Goals  
- Provide an extensible **agent framework** for web scraping and file retrieval.  
- Enable both **rule-based** and **AI-driven reasoning**.  
- Maintain a persistent log of actions to ensure idempotency.  
- Support **containerized deployment** and optional cloud scaling.  

### Non-Goals  
- Circumventing anti-bot protections (e.g., CAPTCHA solving).  
- General-purpose autonomous browsing (scope limited to scraping + downloading).  

---

## 3. Use Cases  

1. **Financial Data Collection**  
   - Retrieve PDFs/CSVs of market reports from government or institutional websites.  

2. **Research Automation**  
   - Download datasets from open portals with filtering rules (e.g., only 2025 climate data).  

3. **Compliance Monitoring**  
   - Periodically check for new regulatory documents and log changes.  

---

## 4. System Overview  

The agent follows the **Perception → Reasoning → Action → Memory** loop:  

- **Perception:** Extract content from web pages using Playwright + BeautifulSoup.  
- **Reasoning:** Decide which files are relevant via rule-based filters or LLM reasoning.  
- **Action:** Download files to local storage (or S3).  
- **Memory:** Track downloads and visited URLs in SQLite/Postgres.  

### Architecture Diagram  

```
User Configs ─┐
              │
[Perception]  │ Playwright → BeautifulSoup → Parsed DOM
              │
[Reasoning]   │ Rule Engine / LLM Planner → Filtered Targets
              │
[Action]      │ Download Executor → Save to storage (local/S3)
              │
[Memory]      │ SQLite/Postgres (download log, errors, retries)
              │
[Orchestration] Airflow/Prefect → Scheduling & Monitoring
```

---

## 5. Requirements  

### Functional Requirements  
- Agent must support configuration of target sites (`sites.yaml`).  
- Agent must extract and filter links based on file types and keywords.  
- Agent must download and persist files to a local directory or S3.  
- Agent must record metadata (URL, filename, timestamp) in memory (SQLite/Postgres).  
- Agent must support both rule-based and LLM-driven filtering.  
- Agent must run on a schedule (daily/weekly) with Airflow/Prefect integration.  

### Non-Functional Requirements  
- **Reliability:** Must retry failed downloads at least 3 times.  
- **Scalability:** Support multiple sites concurrently.  
- **Observability:** Must log actions, errors, and metrics (success/failure rates).  
- **Extensibility:** Modules must be pluggable (scraper, reasoning, executor).  
- **Compliance:** Must respect `robots.txt` and ToS of target sites.  

---

## 6. Tech Stack  

- **Language:** Python 3.11+  
- **Scraping:** Playwright, BeautifulSoup4, lxml  
- **Decision Engine:**  
  - v1: Rule-based filters  
  - v2: LLM planner (OpenAI API, ReAct loop)  
- **Persistence:** SQLite (default), Postgres (production)  
- **Deployment:** Docker  
- **Orchestration:** Airflow/Prefect  
- **Optional Infra:** Terraform modules for S3, RDS, Cloud logging  

---

## 7. Project Structure  

```
web_agent_project/
├── README.md                # Project documentation
├── requirements.txt         # Dependencies
├── Dockerfile               # Container setup
├── config/
│   ├── sites.yaml           # Config rules for scraping targets
│   ├── settings.yaml        # Global agent configs
├── modules/
│   ├── perception.py        # Scraping/parsing logic
│   ├── reasoning.py         # Rule/LLM decision engine
│   ├── action.py            # File download logic
│   ├── memory.py            # State persistence
│   └── orchestrator.py      # Main agent loop
├── data/
│   ├── downloads/           # Saved files
│   ├── logs/                # Agent logs
│   └── agent_memory.db      # SQLite (default)
├── tests/
│   ├── test_perception.py
│   ├── test_reasoning.py
│   ├── test_action.py
│   └── test_memory.py
└── infra/
    ├── terraform/           # Optional infra setup
    └── airflow_dag.py       # Example DAG for orchestration
```

---

## 8. Deployment  

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "modules/orchestrator.py"]
```

### CI/CD  
- Run unit tests (`pytest`) in pipeline.  
- Build and push Docker images via GitHub Actions/GitLab CI.  
- Deploy to orchestrator (Airflow, Prefect, or Cron).  

### Monitoring  
- Logs stored locally and optionally shipped to ELK/CloudWatch.  
- Metrics: download success rate, failure rate, execution time.  

---

## 9. Risks & Mitigations  

- **Scraping breaks due to site changes** → Config-driven parsing rules, monitoring alerts.  
- **Blocked by anti-bot measures** → Rate limiting, compliance with robots.txt.  
- **Data duplication** → Persistent DB log with unique URL constraints.  
- **Scaling bottlenecks** → Async execution, container scaling via Kubernetes.  

---

## 10. Roadmap  

- **Phase 1 (MVP):** Rule-based scraper + SQLite + Docker.  
- **Phase 2:** LLM decision-making + Postgres + Airflow orchestration.  
- **Phase 3:** Semantic filtering (embeddings) + multi-agent orchestration.  
- **Phase 4:** Enterprise deployment (Terraform infra, monitoring dashboards).  

---

## 11. Success Metrics  

- **Functional:**  
  - % of target files successfully downloaded per run (>95%).  
  - Duplicate download rate (<1%).  
- **Performance:**  
  - Time to scrape + download target site (<2 minutes avg).  
- **Reliability:**  
  - Mean failure rate per run (<5%).  
- **Adoption:**  
  - Number of configured sites onboarded by end of Q1.  

---

## 12. Appendix  

**Example Config (`config/sites.yaml`)**  

```yaml
sites:
  - name: "Example Reports"
    url: "https://example.com/reports"
    file_types: [".pdf", ".csv"]
    filters:
      include: ["2025"]
      exclude: ["draft", "test"]
```
