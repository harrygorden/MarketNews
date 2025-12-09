# MarketNews

MarketNews monitors and analyzes market-moving news for futures traders (ES, NQ, GC). This repository currently includes the shared configuration, database schema, and initialization tooling for the MVP foundation (Milestone 1).

## Project Structure
```
MarketNews/
├── pyproject.toml
├── .gitignore
├── .env.example
├── README.md
├── src/
│   ├── __init__.py
│   └── shared/
│       ├── __init__.py
│       ├── config.py
│       └── database/
│           ├── __init__.py
│           ├── models.py
│           └── session.py
├── src/functions/
│   ├── __init__.py
│   ├── host.json
│   ├── requirements.txt
│   ├── local.settings.json.example
│   └── poll_news/
│       ├── __init__.py
│       └── function.json
└── scripts/
    └── init_db.py
tests/
└── test_news_api.py
```

## Quickstart
1) **Python 3.12** and **PostgreSQL 14+** installed locally (or Azure PostgreSQL).
2) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # macOS/Linux
   ```
3) Install dependencies (editable with dev extras):
   ```bash
   pip install -e ".[dev]"
   ```
4) Copy environment template and fill in values:
   ```bash
   cp .env.example .env
   ```
5) Initialize the database schema:
   ```bash
   python scripts/init_db.py
   ```

## Environment Variables
All configuration is loaded via `shared.config.Settings` and validated on startup.
- `DATABASE_URL` (required) — async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:password@localhost:5432/marketnews`
- `STOCKNEWS_API_KEY`, `FIRECRAWL_API_KEY` — external API keys
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY` — LLM providers
- `DISCORD_WEBHOOK_ALERTS`, `DISCORD_WEBHOOK_DIGESTS` — Discord targets
- `AZURE_STORAGE_CONNECTION_STRING`, `QUEUE_NAME` — queue storage (default `article-processing`)
- `IMPACT_THRESHOLD` — default 0.7
- `LOG_LEVEL` — default `INFO`

## Database
The schema matches the MVP ERD:
- `articles` with topic metadata and scrape status
- `article_analyses` for model outputs (unique per provider)
- `digests` and `digest_articles` for scheduled summaries
- `processing_queue_failures` for dead-letter style tracking

Initialize or reset the schema with:
```bash
python scripts/init_db.py
```

## Polling Function (Milestone 2)
- Local settings template: `src/functions/local.settings.json.example` (copy to `local.settings.json`).
- Timer schedule: every 5 minutes (UTC). Weekend guard runs only on the top of the hour.
- Paywall filtering: skips articles whose `topics` contain `paywall` or `paylimitwall`.
- Deduplication: skips articles whose `news_url` already exists in the database.
- Run locally with Azure Functions Core Tools:
  ```bash
  cd src/functions
  func start
  ```

### Queue Message Format (Milestone 3)
- Queue: `QUEUE_NAME` (default `article-processing`)
- Message schema (`ArticleQueueMessage`):
  ```json
  {
    "article_id": 123,
    "news_url": "https://example.com/article",
    "source": "Example Source",
    "published_at": "2025-12-08T12:00:00Z"
  }
  ```

## Processing Function (Milestone 4)
- Queue-triggered function `process_article` consumes `QUEUE_NAME`.
- Scrapes article content via Firecrawl (requires `FIRECRAWL_API_KEY`).
- Runs analyzers (Claude/OpenAI/Gemini) in parallel when API keys are set.
- Stores analysis in `article_analyses`, updates `articles.scraped_content`/status.
- Configure Function host env (`AzureWebJobsStorage`, `QUEUE_NAME`, API keys) in `src/functions/local.settings.json`.

### Connectivity Test Script
- Send a test queue message (requires valid `article_id` in DB):
  ```bash
  python scripts/test_queue_connectivity.py --article-id 123 --news-url https://example.com --source Example
  ```

## Deployment (Milestone 8)
GitHub Actions automate deployments:
- `.github/workflows/deploy-functions.yml` packages `src/functions` (run-from-package) and pushes to Azure Functions.
- `.github/workflows/deploy-webapp.yml` deploys the Flask UI to Azure App Service.

### Required GitHub Secrets (federated)
- `AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`
- `AZURE_FUNCTIONAPP_NAME` (Functions target)
- `AZURE_WEBAPP_NAME` (App Service target)

### Azure App Settings
- Shared: `DATABASE_URL`, `STOCKNEWS_API_KEY`, `FIRECRAWL_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_AI_API_KEY`, `DISCORD_WEBHOOK_ALERTS`, `DISCORD_WEBHOOK_DIGESTS`, `AZURE_STORAGE_CONNECTION_STRING`, `QUEUE_NAME`, `IMPACT_THRESHOLD`, `LOG_LEVEL`.
- Function App only: `AzureWebJobsStorage`, `FUNCTIONS_WORKER_RUNTIME=python`.
- Web App: set startup command to `gunicorn -w 4 wsgi:app` (or configure via portal).

### Notes
- Root `requirements.txt` mirrors `pyproject.toml` for App Service builds.
- Functions workflow restores deps into `.python_packages` before zipping `src/functions`.
- Both workflows trigger on pushes to `main` and support manual `workflow_dispatch`.