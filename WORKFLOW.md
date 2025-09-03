1. 🚀 INITIALIZATION
   ├── Load config/sites.yaml (3 sites configured)
   ├── Initialize SQLite database
   ├── Start Playwright browser
   └── Setup logging to data/logs/agent.log

2. ��️ PERCEPTION (Site 1: "Example Reports")
   ├── Detect: Static site, use aiohttp
   ├── Scrape: Found 25 PDF links
   ├── Extract: Titles, dates, file sizes
   └── Result: 25 ScrapedLink objects

3. 🧠 REASONING (Filtering)
   ├── Deduplication: 25 → 24 links (1 duplicate)
   ├── History check: 24 → 20 links (4 already downloaded)
   ├── Rule filtering: 20 → 15 links (5 don't match criteria)
   ├── LLM filtering: 15 → 8 links (7 below relevance threshold)
   └── Prioritization: Sort by date, size, relevance

4. 📥 ACTION (Downloads)
   ├── Download 8 files concurrently (max 3 at once)
   ├── Retry failed downloads (3 attempts each)
   ├── Generate safe filenames with site prefix
   └── Result: 7 successful, 1 failed

5. 💾 MEMORY (Storage)
   ├── Record 7 successful downloads in database
   ├── Log 1 download failure with error details
   ├── Update scrape session statistics
   └── Mark URLs as visited

6. 🔄 REPEAT for remaining sites
   └── Process "SEC EDGAR Filings" and "Open Data Portal"

7. �� FINAL RESULTS
   ├── Total: 3 sites processed
   ├── Links found: 67 total
   ├── Files downloaded: 23 successful
   ├── Storage used: 45.2 MB
   └── Duration: 2.3 minutes