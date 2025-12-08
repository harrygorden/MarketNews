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
└── scripts/
    └── init_db.py
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
- `AZURE_STORAGE_CONNECTION_STRING` — queue storage (future milestones)
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

## Next Steps
- Milestone 2+: Azure Functions for polling, queueing, and processing
- Add unit tests and CI as new components land