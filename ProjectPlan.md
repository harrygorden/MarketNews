# MarketNews Project Plan

## Executive Summary

MarketNews is a stock market news monitoring and analysis application designed for futures traders focused on ES (S&P 500 E-mini), NQ (Nasdaq E-mini), and GC (Gold). The system automatically polls financial news APIs, scrapes full article content, performs multi-LLM sentiment analysis, and delivers actionable insights through Discord notifications and a web interface.

**Timeline**: 1-2 weeks (MVP)  
**Tech Stack**: Python 3.12, Flask, Azure Functions, PostgreSQL, Azure Storage Queue  
**Primary Users**: Futures traders requiring real-time market sentiment intelligence

### Key Capabilities

- **Automated News Polling**: Monitors StockNewsAPI with market-hours-aware scheduling
- **Multi-LLM Analysis**: Cross-references Claude Sonnet 4.5, GPT-4o, and Gemini 2.5 Pro for consensus sentiment
- **Smart Notifications**: Discord alerts for high-impact articles with LLM consensus
- **Scheduled Digests**: Premarket, lunch, post-market, and weekly summaries
- **Web Dashboard**: Browse, filter, and analyze collected articles and their sentiments

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph External["External Services"]
        SNAPI[StockNewsAPI]
        FC[FireCrawl]
        CLAUDE[Claude Sonnet 4.5]
        GPT[GPT-4o]
        GEMINI[Gemini 2.5 Pro]
        DISCORD[Discord Webhooks]
    end

    subgraph Azure["Azure Infrastructure"]
        subgraph Functions["Azure Functions (Consumption)"]
            POLL[poll_news<br/>Timer: 5min/1hr]
            PROCESS[process_article<br/>Queue Trigger]
            DIGEST[send_digest<br/>Timer: 4x daily + weekly]
        end
        
        QUEUE[(Azure Storage Queue<br/>article-processing)]
        DLQ[(Dead Letter Queue<br/>article-processing-poison)]
        
        subgraph AppService["Azure App Service (B1)"]
            FLASK[Flask Web App]
        end
        
        PG[(Azure PostgreSQL<br/>Flexible Server)]
    end

    subgraph Users["Users"]
        TRADER[Futures Trader]
        DCLIENT[Discord Client]
    end

    %% Data Flow
    POLL -->|Poll every 5min/1hr| SNAPI
    SNAPI -->|New articles| POLL
    POLL -->|Enqueue article_id| QUEUE
    
    QUEUE -->|Trigger| PROCESS
    PROCESS -->|Scrape| FC
    FC -->|Article content| PROCESS
    PROCESS -->|Analyze| CLAUDE
    PROCESS -->|Analyze| GPT
    PROCESS -->|Analyze| GEMINI
    CLAUDE -->|Analysis| PROCESS
    GPT -->|Analysis| PROCESS
    GEMINI -->|Analysis| PROCESS
    
    PROCESS -->|High impact alert| DISCORD
    PROCESS -->|Store results| PG
    PROCESS -.->|On failure| DLQ
    
    DIGEST -->|Read articles| PG
    DIGEST -->|Send digest| DISCORD
    DIGEST -->|Update digest history| PG
    
    DISCORD -->|Notifications| DCLIENT
    
    FLASK -->|Query| PG
    TRADER -->|Browse| FLASK

    style POLL fill:#4a9eff
    style PROCESS fill:#4a9eff
    style DIGEST fill:#4a9eff
    style FLASK fill:#22c55e
    style PG fill:#f59e0b
    style QUEUE fill:#8b5cf6
```

### Component Responsibilities

| Component | Responsibility | Trigger |
|-----------|---------------|---------|
| `poll_news` | Fetch new articles from StockNewsAPI, deduplicate, filter paywalls, enqueue for processing | Timer (5min weekday, 1hr weekend) |
| `process_article` | Scrape via FireCrawl, analyze with 3 LLMs, store results, send high-impact alerts | Queue message |
| `send_digest` | Aggregate top articles, generate summary, post to Discord | Timer (4x daily + weekly) |
| Flask App | Web interface for viewing articles, analyses, and digest history | HTTP requests |

---

## Milestones

### Milestone 1: Project Foundation
**Estimated Time**: 3-4 hours  
**Objective**: Establish repository structure, shared configuration, database schema, and local development environment.

#### Subtasks

- [ ] **1.1** Initialize project structure with `pyproject.toml` and package configuration
- [ ] **1.2** Create `src/shared/config.py` with environment variable loading and validation
- [ ] **1.3** Create `src/shared/database/models.py` with SQLAlchemy ORM models
- [ ] **1.4** Create `src/shared/database/session.py` with async database session management
- [ ] **1.5** Create `scripts/init_db.py` for database schema initialization
- [ ] **1.6** Create `.env.example` with all required environment variables
- [ ] **1.7** Create `README.md` with setup instructions
- [ ] **1.8** Set up local PostgreSQL or connection to Azure PostgreSQL for development
- [ ] **1.9** Run `init_db.py` and verify all tables are created correctly

#### Acceptance Criteria

- Repository structure matches the defined monorepo layout
- All environment variables are documented and validated on startup
- Database tables are created with correct schema, constraints, and indexes
- Local development can connect to PostgreSQL (local or Azure)
- `python scripts/init_db.py` executes without errors

#### Dependencies

- None (first milestone)

#### Files to Create

```
MarketNews/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
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

---

### Milestone 2: News Polling Function
**Estimated Time**: 3-4 hours  
**Objective**: Implement Azure Function to poll StockNewsAPI, filter paywalled sources, and store new articles.

#### Subtasks

- [ ] **2.1** Create `src/shared/services/news_api.py` with StockNewsAPI client
- [ ] **2.2** Implement article fetching with proper error handling and retry logic
- [ ] **2.3** Implement paywall detection (check for "paywall" or "paylimitwall" in topics array)
- [ ] **2.4** Create `src/functions/poll_news/__init__.py` Azure Function handler
- [ ] **2.5** Create `src/functions/poll_news/function.json` with timer trigger configuration
- [ ] **2.6** Implement market-hours-aware scheduling logic (5min weekday, 1hr weekend)
- [ ] **2.7** Implement article deduplication by URL before database insert
- [ ] **2.8** Create `src/functions/host.json` and `src/functions/requirements.txt`
- [ ] **2.9** Write unit tests for news API client and paywall filtering
- [ ] **2.10** Test function locally using Azure Functions Core Tools

#### Acceptance Criteria

- Function polls StockNewsAPI and retrieves articles successfully
- Paywalled articles (WSJ, Barron's, etc.) are filtered out
- Duplicate articles are not inserted into the database
- Function respects market hours scheduling (can be tested with mocked time)
- API errors are logged and don't crash the function

#### Dependencies

- Milestone 1 (database models and config)

#### Files to Create/Modify

```
src/
├── shared/
│   └── services/
│       ├── __init__.py
│       └── news_api.py
└── functions/
    ├── __init__.py
    ├── host.json
    ├── requirements.txt
    ├── local.settings.json.example
    └── poll_news/
        ├── __init__.py
        └── function.json
tests/
└── test_news_api.py
```

---

### Milestone 3: Queue Infrastructure
**Estimated Time**: 2-3 hours  
**Objective**: Set up Azure Storage Queue for decoupling article discovery from processing, including dead letter handling.

#### Subtasks

- [ ] **3.1** Create `src/shared/services/queue.py` with Azure Storage Queue client wrapper
- [ ] **3.2** Implement message enqueue function with proper serialization
- [ ] **3.3** Implement poison message handling configuration in function.json
- [ ] **3.4** Create `processing_queue_failures` table tracking logic
- [ ] **3.5** Update `poll_news` function to enqueue article IDs after successful insert
- [ ] **3.6** Create queue message schema using Pydantic
- [ ] **3.7** Test queue operations locally using Azurite or Azure Storage emulator
- [ ] **3.8** Document queue message format in README

#### Acceptance Criteria

- Articles are enqueued after being stored in database
- Queue messages contain article ID and necessary metadata
- Poison messages are moved to dead letter queue after max retries
- Failed processing attempts are logged to `processing_queue_failures` table
- Queue operations are idempotent

#### Dependencies

- Milestone 1 (database models)
- Milestone 2 (poll_news function)

#### Files to Create/Modify

```
src/
└── shared/
    ├── services/
    │   └── queue.py
    └── schemas/
        ├── __init__.py
        └── queue_messages.py
```

---

### Milestone 4: Article Processing Pipeline
**Estimated Time**: 5-6 hours  
**Objective**: Implement queue-triggered function that scrapes articles and performs multi-LLM sentiment analysis.

#### Subtasks

- [ ] **4.1** Create `src/shared/services/firecrawl.py` with FireCrawl API client
- [ ] **4.2** Implement article scraping with error handling for failed scrapes
- [ ] **4.3** Create `src/shared/services/analyzers.py` with base analyzer interface
- [ ] **4.4** Implement Claude Sonnet 4.5 analyzer using Anthropic SDK
- [ ] **4.5** Implement GPT-4o analyzer using OpenAI SDK
- [ ] **4.6** Implement Gemini 2.5 Pro analyzer using Google AI SDK
- [ ] **4.7** Create standardized prompt template for consistent analysis output
- [ ] **4.8** Create Pydantic schema for LLM analysis response validation
- [ ] **4.9** Create `src/functions/process_article/__init__.py` queue-triggered function
- [ ] **4.10** Create `src/functions/process_article/function.json` with queue trigger
- [ ] **4.11** Implement parallel LLM calls using asyncio.gather
- [ ] **4.12** Store all three analyses in `article_analyses` table
- [ ] **4.13** Update article record with scraped content and status
- [ ] **4.14** Handle scrape failures gracefully (mark article, don't block queue)
- [ ] **4.15** Write unit tests for analyzers with mocked LLM responses

#### Acceptance Criteria

- Queue messages trigger article processing
- FireCrawl successfully scrapes article content
- All three LLMs return properly structured analysis
- Analysis results are stored with correct foreign key relationships
- Failed scrapes are marked but don't crash the function
- LLM API errors are handled with appropriate retries

#### Dependencies

- Milestone 1 (database models)
- Milestone 3 (queue infrastructure)

#### Files to Create/Modify

```
src/
├── shared/
│   ├── services/
│   │   ├── firecrawl.py
│   │   └── analyzers.py
│   └── schemas/
│       └── analysis.py
└── functions/
    └── process_article/
        ├── __init__.py
        └── function.json
tests/
├── test_firecrawl.py
└── test_analyzers.py
```

---

### Milestone 5: Discord Notifications
**Estimated Time**: 2-3 hours  
**Objective**: Implement real-time Discord alerts for high-impact articles meeting consensus criteria.

#### Subtasks

- [ ] **5.1** Create `src/shared/services/discord.py` with Discord webhook client
- [ ] **5.2** Implement rich embed message formatting for article alerts
- [ ] **5.3** Implement consensus detection logic (all LLMs agree on sentiment direction)
- [ ] **5.4** Implement impact threshold checking (configurable, default 0.7)
- [ ] **5.5** Implement topic relevance filtering (S&P 500, Nasdaq, Gold, Fed, FOMC)
- [ ] **5.6** Add notification trigger to `process_article` function after analysis
- [ ] **5.7** Include web app detail view link in notification
- [ ] **5.8** Create notification message template with headline, source, sentiment, impact, links
- [ ] **5.9** Add rate limiting to prevent Discord webhook abuse
- [ ] **5.10** Test notifications with mock high-impact articles

#### Acceptance Criteria

- High-impact articles trigger Discord notifications
- Notifications only sent when all three LLMs agree on sentiment
- Notifications include all required information (headline, source, sentiment, impact, links)
- Notification embeds are visually clear with appropriate colors (green=bullish, red=bearish, gray=neutral)
- Rate limiting prevents excessive notifications

#### Dependencies

- Milestone 4 (article processing pipeline)

#### Files to Create/Modify

```
src/
└── shared/
    └── services/
        └── discord.py
```

---

### Milestone 6: Scheduled Digests
**Estimated Time**: 3-4 hours  
**Objective**: Implement timer-triggered functions for premarket, lunch, post-market, and weekly digest generation.

#### Subtasks

- [ ] **6.1** Create `src/functions/send_digest/__init__.py` with digest logic
- [ ] **6.2** Create `src/functions/send_digest/function.json` with timer triggers
- [ ] **6.3** Implement article aggregation query (since last digest, by type)
- [ ] **6.4** Implement article prioritization algorithm:
  - LLM consensus (all three agree) - highest priority
  - Sentiment strength (absolute value of average score)
  - Impact score
- [ ] **6.5** Implement digest message formatting with ranked article list
- [ ] **6.6** Create premarket digest (6:30 AM ET, weekdays)
- [ ] **6.7** Create lunch digest (12:00 PM ET, weekdays)
- [ ] **6.8** Create post-market digest (4:30 PM ET, weekdays)
- [ ] **6.9** Create weekly digest (12:00 PM ET, Saturday)
- [ ] **6.10** Store digest records in `digests` and `digest_articles` tables
- [ ] **6.11** Update articles with `included_in_digest_at` timestamp
- [ ] **6.12** Handle empty digest periods gracefully (no articles = no message or summary message)
- [ ] **6.13** Test digest generation with various article scenarios

#### Acceptance Criteria

- Digests are sent at correct times (ET timezone)
- Digests include top articles prioritized correctly
- Digest history is stored in database
- Weekly digest covers full previous week
- Empty periods are handled gracefully
- Digests are sent to the correct Discord channel (Digests channel, not Alerts)

#### Dependencies

- Milestone 1 (database models)
- Milestone 5 (Discord service)

#### Files to Create/Modify

```
src/
└── functions/
    └── send_digest/
        ├── __init__.py
        └── function.json
```

---

### Milestone 7: Web Interface
**Estimated Time**: 5-6 hours  
**Objective**: Build Flask web application for viewing articles, analyses, and digest history.

#### Subtasks

- [ ] **7.1** Create `src/webapp/app.py` with Flask application factory
- [ ] **7.2** Create `src/webapp/routes/__init__.py` with blueprint registration
- [ ] **7.3** Create `src/webapp/routes/articles.py` with article list and detail routes
- [ ] **7.4** Create `src/webapp/routes/digests.py` with digest history routes
- [ ] **7.5** Create base template with navigation and consistent styling
- [ ] **7.6** Create article list template with:
  - Sentiment badges (color-coded)
  - Impact indicators (visual bar or number)
  - Source and date information
  - Pagination
- [ ] **7.7** Create article detail template with:
  - Full summary from each LLM (side by side or tabbed)
  - Sentiment scores comparison
  - Key topics/entities
  - Link to original article
- [ ] **7.8** Create digest history template with:
  - List of past digests by type
  - Expandable article list per digest
- [ ] **7.9** Implement filter functionality:
  - Date range picker
  - Sentiment filter (bullish/bearish/neutral)
  - Source filter
  - Impact level filter
- [ ] **7.10** Implement search functionality (headline/content search)
- [ ] **7.11** Create static assets (CSS, minimal JS for interactions)
- [ ] **7.12** Create `src/webapp/wsgi.py` for production deployment
- [ ] **7.13** Test all routes and filters locally
- [ ] **7.14** Ensure responsive design for mobile viewing

#### Acceptance Criteria

- Home page displays recent articles with pagination
- Article detail page shows all three LLM analyses
- Filters work correctly and can be combined
- Search returns relevant results
- Digest history shows past digests with associated articles
- UI is clean, responsive, and easy to navigate
- No authentication required

#### Dependencies

- Milestone 1 (database models)
- Milestone 4 (article analyses exist in database)
- Milestone 6 (digest records exist in database)

#### Files to Create/Modify

```
src/
└── webapp/
    ├── __init__.py
    ├── app.py
    ├── wsgi.py
    ├── routes/
    │   ├── __init__.py
    │   ├── articles.py
    │   └── digests.py
    ├── templates/
    │   ├── base.html
    │   ├── articles/
    │   │   ├── list.html
    │   │   └── detail.html
    │   └── digests/
    │       └── history.html
    └── static/
        ├── css/
        │   └── style.css
        └── js/
            └── main.js
```

---

### Milestone 8: Deployment & CI/CD
**Estimated Time**: 3-4 hours  
**Objective**: Configure GitHub Actions for automated deployment to Azure Functions and App Service.

#### Subtasks

- [ ] **8.1** Create `.github/workflows/deploy-functions.yml` for Azure Functions deployment
- [ ] **8.2** Create `.github/workflows/deploy-webapp.yml` for App Service deployment
- [ ] **8.3** Configure GitHub repository secrets for Azure credentials
- [ ] **8.4** Create Azure Function App resource (Consumption plan, Python 3.12)
- [ ] **8.5** Configure Function App application settings (environment variables)
- [ ] **8.6** Configure App Service application settings
- [ ] **8.7** Set up Azure PostgreSQL firewall rules for Function App and App Service
- [ ] **8.8** Create production database schema using `init_db.py`
- [ ] **8.9** Deploy Functions and verify timer triggers are running
- [ ] **8.10** Deploy Web App and verify it's accessible
- [ ] **8.11** Test end-to-end flow in production:
  - Poll fetches articles
  - Queue triggers processing
  - LLM analysis completes
  - Discord notifications sent
  - Web app displays results
- [ ] **8.12** Set up Application Insights for monitoring (optional but recommended)
- [ ] **8.13** Document deployment process in README

#### Acceptance Criteria

- Push to main branch triggers deployment workflows
- Functions deploy and run on schedule
- Web app is accessible via Azure App Service URL
- All environment variables are configured in Azure
- End-to-end flow works in production
- Monitoring/logging is available for debugging

#### Dependencies

- All previous milestones

#### Files to Create/Modify

```
.github/
└── workflows/
    ├── deploy-functions.yml
    └── deploy-webapp.yml
README.md (update with deployment instructions)
```

---

## Environment Setup Instructions

### Prerequisites

- Python 3.12+
- Azure CLI (`az`)
- Azure Functions Core Tools v4
- PostgreSQL 14+ (local) or Azure PostgreSQL connection
- Git

### Local Development Setup

#### 1. Clone Repository

```bash
git clone https://github.com/harrygorden/MarketNews.git
cd MarketNews
```

#### 2. Create Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

#### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

#### 4. Configure Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your values
```

#### 5. Required Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/marketnews

# APIs
STOCKNEWS_API_KEY=your_stocknews_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key

# LLM Providers
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_AI_API_KEY=your_google_ai_api_key

# Discord Webhooks
DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_DIGESTS=https://discord.com/api/webhooks/...

# Azure Storage (for queue)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...

# Optional
IMPACT_THRESHOLD=0.7
LOG_LEVEL=INFO
```

#### 6. Initialize Database

```bash
python scripts/init_db.py
```

#### 7. Run Azure Functions Locally

```bash
cd src/functions
func start
```

#### 8. Run Flask App Locally

```bash
cd src/webapp
flask run --debug
```

### Azure Resource Setup

#### Required Azure Resources

| Resource | SKU/Tier | Purpose |
|----------|----------|---------|
| Resource Group | - | Container for all resources |
| Storage Account | Standard_LRS | Queue storage |
| Function App | Consumption (Y1) | Serverless functions |
| App Service Plan | B1 | Web app hosting |
| App Service | - | Flask web application |
| PostgreSQL Flexible Server | Burstable B1ms | Database |

#### Azure CLI Setup Commands

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "Your Subscription Name"

# Create resource group (if not exists)
az group create --name rg-marketnews --location eastus

# Create storage account for queues
az storage account create \
  --name stmarketnews \
  --resource-group rg-marketnews \
  --location eastus \
  --sku Standard_LRS

# Create storage queue
az storage queue create \
  --name article-processing \
  --account-name stmarketnews

# Create Function App
az functionapp create \
  --name func-marketnews \
  --resource-group rg-marketnews \
  --storage-account stmarketnews \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.12 \
  --functions-version 4

# Create App Service Plan
az appservice plan create \
  --name plan-marketnews \
  --resource-group rg-marketnews \
  --sku B1 \
  --is-linux

# Create Web App
az webapp create \
  --name app-marketnews \
  --resource-group rg-marketnews \
  --plan plan-marketnews \
  --runtime "PYTHON:3.12"
```

---

## Database Schema

### Entity Relationship Diagram

```mermaid
erDiagram
    articles ||--o{ article_analyses : has
    articles ||--o{ digest_articles : included_in
    digests ||--o{ digest_articles : contains
    articles ||--o{ processing_queue_failures : may_have

    articles {
        int id PK
        string news_url UK "Unique article URL"
        string title
        string source
        timestamp published_at
        jsonb topics "Array of topic strings"
        string api_sentiment "From StockNewsAPI"
        jsonb raw_api_response
        text scraped_content
        timestamp scraped_at
        boolean scrape_failed
        timestamp created_at
        timestamp included_in_digest_at
    }

    article_analyses {
        int id PK
        int article_id FK
        string model_provider "anthropic/openai/google"
        string model_name "claude-sonnet-4-5/gpt-4o/gemini-2.5-pro"
        text summary
        string sentiment "Bullish/Bearish/Neutral"
        float sentiment_score "-1.0 to 1.0"
        float impact_score "0.0 to 1.0"
        jsonb key_topics "Array of entities/topics"
        jsonb raw_response
        timestamp analyzed_at
    }

    digests {
        int id PK
        string digest_type "premarket/lunch/postmarket/weekly"
        timestamp sent_at
        int article_count
        string discord_message_id
    }

    digest_articles {
        int id PK
        int digest_id FK
        int article_id FK
        int rank "Position in digest"
    }

    processing_queue_failures {
        int id PK
        int article_id FK
        string error_message
        text stack_trace
        int attempt_count
        timestamp first_failure_at
        timestamp last_failure_at
        boolean resolved
    }
```

### SQL Schema

```sql
-- Articles table
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    news_url VARCHAR(2048) NOT NULL UNIQUE,
    title VARCHAR(500) NOT NULL,
    source VARCHAR(100),
    published_at TIMESTAMP WITH TIME ZONE,
    topics JSONB DEFAULT '[]',
    api_sentiment VARCHAR(50),
    raw_api_response JSONB,
    scraped_content TEXT,
    scraped_at TIMESTAMP WITH TIME ZONE,
    scrape_failed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    included_in_digest_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_articles_published_at ON articles(published_at DESC);
CREATE INDEX idx_articles_created_at ON articles(created_at DESC);
CREATE INDEX idx_articles_source ON articles(source);
CREATE INDEX idx_articles_scrape_failed ON articles(scrape_failed) WHERE scrape_failed = TRUE;

-- Article analyses table
CREATE TABLE article_analyses (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    model_provider VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    summary TEXT,
    sentiment VARCHAR(20),
    sentiment_score NUMERIC(4,3) CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0),
    impact_score NUMERIC(4,3) CHECK (impact_score >= 0.0 AND impact_score <= 1.0),
    key_topics JSONB DEFAULT '[]',
    raw_response JSONB,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(article_id, model_provider)
);

CREATE INDEX idx_analyses_article_id ON article_analyses(article_id);
CREATE INDEX idx_analyses_sentiment ON article_analyses(sentiment);
CREATE INDEX idx_analyses_impact_score ON article_analyses(impact_score DESC);

-- Digests table
CREATE TABLE digests (
    id SERIAL PRIMARY KEY,
    digest_type VARCHAR(20) NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    article_count INTEGER DEFAULT 0,
    discord_message_id VARCHAR(100)
);

CREATE INDEX idx_digests_type_sent ON digests(digest_type, sent_at DESC);

-- Digest articles junction table
CREATE TABLE digest_articles (
    id SERIAL PRIMARY KEY,
    digest_id INTEGER NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    rank INTEGER,
    UNIQUE(digest_id, article_id)
);

-- Processing queue failures (dead letter tracking)
CREATE TABLE processing_queue_failures (
    id SERIAL PRIMARY KEY,
    article_id INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    error_message VARCHAR(1000),
    stack_trace TEXT,
    attempt_count INTEGER DEFAULT 1,
    first_failure_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_failure_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_failures_resolved ON processing_queue_failures(resolved) WHERE resolved = FALSE;
```

---

## LLM Prompt Template

The following prompt template ensures consistent analysis output across all three LLMs:

```
You are a financial news analyst specializing in market sentiment analysis for futures traders.

Analyze the following news article and provide a structured assessment.

ARTICLE:
Title: {title}
Source: {source}
Published: {published_at}
Content:
{content}

Provide your analysis in the following JSON format:
{
  "summary": "A 2-3 sentence summary of the article's key points and market implications",
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "sentiment_score": <float from -1.0 (most bearish) to 1.0 (most bullish)>,
  "impact_score": <float from 0.0 (minimal impact) to 1.0 (major market-moving)>,
  "key_topics": ["list", "of", "relevant", "entities", "and", "topics"]
}

SCORING GUIDELINES:
- Sentiment: Consider implications for S&P 500, Nasdaq, and Gold futures
- Impact Score: 
  - 0.0-0.3: Routine news, minor market relevance
  - 0.4-0.6: Notable news, moderate market relevance
  - 0.7-0.9: Significant news, high market relevance
  - 0.9-1.0: Major market-moving event (Fed decisions, major economic data, geopolitical events)

Focus on implications for:
- ES (S&P 500 E-mini futures)
- NQ (Nasdaq E-mini futures)  
- GC (Gold futures)
- Federal Reserve / FOMC policy
- Major economic indicators

Return ONLY the JSON object, no additional text.
```

---

## Phase 2 Roadmap

The following features are documented for future development but are **out of scope for MVP**:

### User Authentication & Personalization
- **User Accounts**: Email/password authentication with secure password hashing
- **OAuth Integration**: Google, GitHub login options
- **User Profiles**: Saved preferences, notification settings
- **Session Management**: JWT tokens with refresh capability

### Customizable Watchlists
- **Ticker Watchlists**: Users can create custom lists of tickers to monitor
- **Custom Filters**: Per-user filter presets for the web interface
- **Watchlist Alerts**: Notifications only for articles matching user's watchlist
- **Sector Groupings**: Pre-built sector-based watchlists (Tech, Energy, Finance, etc.)

### Premium Subscription Tier
- **Stripe Integration**: Payment processing for subscriptions
- **Tier Definitions**:
  - Free: Limited to 50 articles/day, standard digests
  - Premium: Unlimited articles, priority notifications, custom digest schedules
- **Usage Metering**: Track and enforce tier limits
- **Subscription Management**: Upgrade, downgrade, cancellation flows

### Additional Notification Channels
- **Email Notifications**: SendGrid/AWS SES integration for email alerts
- **SMS Alerts**: Twilio integration for critical alerts
- **Slack Integration**: Webhook support for Slack workspaces
- **Push Notifications**: Browser push for web app users

### Historical Sentiment Analysis
- **Trend Charts**: Visualize sentiment trends over time by topic/sector
- **Sentiment Heatmaps**: Calendar view of market sentiment
- **Correlation Analysis**: Compare sentiment shifts across different topics
- **Export Capabilities**: CSV/JSON export of historical data

### Backtesting Integration
- **Price Data Integration**: Connect to market data APIs (Alpha Vantage, Yahoo Finance)
- **Sentiment vs Price**: Overlay sentiment scores on price charts
- **Signal Analysis**: Evaluate sentiment as trading signals
- **Performance Reports**: Track hypothetical returns from sentiment-based strategies

---

## Risk Assessment & Considerations

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM API rate limits | Medium | High | Implement retry with exponential backoff; queue processing naturally throttles |
| FireCrawl scraping failures | High | Medium | Mark articles as failed, don't block queue; provide manual retry option |
| Azure Function cold starts | Medium | Low | Consumption plan acceptable for 5-min intervals; consider Premium plan if latency critical |
| Database connection limits | Low | Medium | Use connection pooling; PostgreSQL Flexible Server handles well |
| StockNewsAPI downtime | Low | Medium | Log failures, continue with next poll; no data loss |

### Cost Considerations

| Service | Estimated Monthly Cost | Notes |
|---------|----------------------|-------|
| Azure Functions | $0-20 | Consumption plan, depends on volume |
| Azure App Service (B1) | ~$13 | Fixed cost |
| Azure PostgreSQL (B1ms) | ~$15-25 | Burstable, depends on storage |
| Azure Storage | <$5 | Queue operations minimal |
| StockNewsAPI | Varies | Depends on plan |
| FireCrawl | Varies | Per-scrape pricing |
| OpenAI API | ~$20-50 | Depends on article volume |
| Anthropic API | ~$20-50 | Depends on article volume |
| Google AI API | ~$10-30 | Generally lower pricing |
| **Total Estimated** | **$80-200/month** | Varies with volume |

### Security Considerations

- **API Keys**: All API keys stored in Azure Key Vault or App Settings (encrypted at rest)
- **Database**: Azure PostgreSQL SSL required, firewall rules restricted to Azure services
- **Discord Webhooks**: Webhook URLs are secrets, not exposed in client-side code
- **No Authentication**: MVP has no auth; consider IP restrictions if needed
- **Input Validation**: All external data validated via Pydantic before database insert

### Operational Considerations

- **Monitoring**: Set up Azure Application Insights for Functions and App Service
- **Alerting**: Configure alerts for function failures, high error rates
- **Logging**: Structured logging with correlation IDs for debugging
- **Backup**: Enable automated PostgreSQL backups (default in Azure)
- **Timezone Handling**: All times stored as UTC, converted to ET for display/scheduling

### StockNewsAPI Specifics

- **Rate Limits**: Check API plan for request limits
- **Pagination**: Handle pagination for high-volume periods
- **Topics Filter**: Use topics parameter to focus on market-relevant news
- **Paywall Detection**: Filter articles where `topics` array contains "paywall" or "paylimitwall"

### LLM Analysis Considerations

- **Token Limits**: Truncate very long articles to fit context windows
- **Cost Optimization**: Consider caching identical content analysis
- **Consensus Logic**: "Agree on direction" means all Bullish, all Bearish, or all Neutral
- **Fallback**: If one LLM fails, still process with available analyses

---

## Testing Strategy

### Unit Tests
- News API client parsing and filtering
- Paywall detection logic
- LLM response parsing and validation
- Consensus calculation
- Digest prioritization algorithm

### Integration Tests
- Database CRUD operations
- Queue enqueue/dequeue
- Discord webhook delivery (use test webhook)

### End-to-End Tests
- Full flow from poll → queue → process → notify
- Digest generation with real data
- Web app routes with database queries

### Manual Testing Checklist
- [ ] Poll function retrieves articles correctly
- [ ] Paywalled articles are filtered
- [ ] Duplicate articles are not stored
- [ ] Queue messages trigger processing
- [ ] FireCrawl scrapes articles successfully
- [ ] All three LLMs return valid analyses
- [ ] High-impact articles trigger Discord alerts
- [ ] Digests are generated at scheduled times
- [ ] Web app displays articles and analyses
- [ ] Filters and search work correctly

---

## Quick Reference

### Key Commands

```bash
# Run functions locally
cd src/functions && func start

# Run web app locally
cd src/webapp && flask run --debug

# Initialize database
python scripts/init_db.py

# Run tests
pytest tests/

# Deploy functions
func azure functionapp publish func-marketnews

# Deploy web app
az webapp up --name app-marketnews
```

### Important URLs

- **GitHub**: https://github.com/harrygorden/MarketNews
- **StockNewsAPI Docs**: https://stocknewsapi.com/documentation
- **Azure Functions Docs**: https://docs.microsoft.com/azure/azure-functions/
- **Flask Docs**: https://flask.palletsprojects.com/

### Discord Channel Setup

1. **General Market News** (Alerts): Create channel, generate webhook URL
2. **Market News Digests**: Create channel, generate webhook URL
3. Store webhook URLs in environment variables

---

## Glossary

| Term | Definition |
|------|------------|
| ES | E-mini S&P 500 futures contract |
| NQ | E-mini Nasdaq-100 futures contract |
| GC | Gold futures contract |
| FOMC | Federal Open Market Committee |
| Consensus | All three LLMs agree on sentiment direction |
| Impact Score | 0.0-1.0 rating of article's market significance |
| Digest | Scheduled summary of top articles |
| Dead Letter | Queue message that failed processing after max retries |

