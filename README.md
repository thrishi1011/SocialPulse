# SocialPulse

**Multi-platform social media trending intelligence dashboard.**

SocialPulse collects trending topics from 9 sources, normalizes them into one format, adds AI summaries and categories, groups related items into cross-platform stories, and tracks how fast trends are rising or cooling. It is built with FastAPI, SQLAlchemy and a zero-build vanilla JavaScript frontend.


---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Features](#features)
3. [How It Works (Architecture)](#how-it-works-architecture)
4. [Data Sources and Provenance](#data-sources-and-provenance)
5. [Configuration Reference](#configuration-reference)
6. [Running in Live Mode](#running-in-live-mode)
7. [Algorithms Explained](#algorithms-explained)
8. [API Reference](#api-reference)
9. [Project Structure](#project-structure)
10. [Testing](#testing)
11. [Deployment (Render)](#deployment-render)
12. [Troubleshooting](#troubleshooting)
13. [Known Limitations](#known-limitations)
14. [License](#license)

---

## Quick Start

Runs in about 5 minutes. **No API keys needed** for the first run, because it uses bundled sample data.

**Requirements:** Python 3.11 or newer, and Git.

### 1. Clone the repository

```bash
git clone https://github.com/thrishi1011/SocialPulse.git
cd SocialPulse
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first.

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env` file

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

Open `.env` and make sure it contains these three lines. They keep the app on sample data so it runs without any keys:

```ini
MOCK_FETCH_MODE=true
MOCK_AI_MODE=true
LIVE_SOURCES=
```

`LIVE_SOURCES=` must be present and **empty**. If you leave it out, the app's built-in default list makes every source run live even when `MOCK_FETCH_MODE=true`.

### 5. Initialize the database

```bash
python -m backend.seed
```

### 6. Start the server

```bash
# Recommended command (works reliably across Windows, macOS, and Linux):
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
# Or if port 8000 is occupied:
# python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

> **Note for Windows users:** Always run with `python -m uvicorn ...` instead of bare `uvicorn ...`. This ensures Python executes directly from your active virtual environment, avoiding `The term 'uvicorn' is not recognized` or `CommandNotFoundException` errors.

Wait for `Application startup complete.`, then open:

| URL | What it is |
| :--- | :--- |
| http://localhost:8000 or http://127.0.0.1:8000 (or port 8001) | Dashboard UI |
| http://localhost:8000/docs | Interactive API docs (Swagger UI) |
| http://localhost:8000/health | System health check (shows mock/live status) |

**Note:** The page opens immediately. If the database is empty or data is older than 12 hours, the initial data ingestion runs seamlessly in the background so the server is never blocked. Cards will populate automatically; simply refresh the page.

### Running it again later

Whenever you return to the project:

1. Open a terminal in the project directory (`cd SocialPulse`).
2. Activate your virtual environment:
   - **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
   - **Linux / macOS:** `source venv/bin/activate`
3. Launch the server:
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
# Or if port 8000 is occupied:
# python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
   ```

Stop the server anytime with `Ctrl+C`.

---

## Features

- **Live Feed.** Trending cards from all 9 sources, with filters for source, recency (6h / 12h / 24h), region, category and sort order (most recent, highest engagement, rising now), plus pagination.
- **AI summaries and categories.** Each item gets a short "why it's trending" summary, a category from a 12-item taxonomy, and an India location if one is genuinely tied to the story. Uses Google Gemini, with a keyword-based fallback when Gemini is off.
- **Trending region.** Every card and detail drawer shows a resolved region with an explanation of how it was determined (see [Trending region](#trending-region-fallback-chain)).
- **Macro Stories.** Items from different platforms about the same real-world event are grouped into one story card with a convergence badge (for example "Trending across 3 sources").
- **Trend momentum.** Snapshots are stored on every fetch. Cards show sparklines and badges: surging, peaking, cooling, steady, new, or tracking.
- **Analytics dashboard.** Category breakdown, platform share, data provenance ratio, top locations, a 24-hour volume timeline, and AI coverage, all computed with SQL aggregates.
- **Source Health.** Live status for every source: last fetch, duration, 24-hour success rate, recent logs, and a "Run now" button.
- **Watchlist, bookmarks and CSV export.** Keyword watchlist and saved items (stored in your browser's `localStorage`), and a CSV export of the current filtered view with formula-injection protection.
- **Community Discussions & Sentiment.** Real top-level comments for YouTube videos via YouTube Data API v3 with upvote ranking and automated sentiment categorization (positive, neutral, critical, curious, excited). Macro stories include cross-platform community reaction synthesis.
- **Scheduler.** Background jobs fetch each source on its own interval, run the AI sweep, cluster stories, and prune old snapshots.

---

## How It Works (Architecture)

```
 ┌──────────────┐   ┌─────────────┐   ┌────────────────┐   ┌──────────────┐
 │  Scheduler   │──▶│  Fetchers   │──▶│   Database     │──▶│  AI sweep    │
 │ (APScheduler)│   │ (9 sources) │   │ SQLite/Postgres│   │ (Gemini or   │
 └──────────────┘   └─────────────┘   └───────┬────────┘   │  heuristics) │
                                              │            └──────┬───────┘
                          ┌───────────────────┤                   │
                          ▼                   ▼                   ▼
                  ┌──────────────┐   ┌────────────────┐   ┌──────────────┐
                  │ Snapshots →  │   │ Topic          │   │ Summary,     │
                  │ Momentum     │   │ clustering     │   │ category,    │
                  └──────┬───────┘   └───────┬────────┘   │ location     │
                         └──────────┬────────┘            └──────┬───────┘
                                    ▼                            │
                            ┌───────────────┐◀───────────────────┘
                            │ FastAPI       │
                            │ REST API      │
                            └───────┬───────┘
                                    ▼
                            ┌───────────────┐
                            │ Vanilla JS    │
                            │ frontend      │
                            └───────────────┘
```

**Data flow in plain words:**

1. **Fetch.** Each source has a fetcher (`backend/fetchers/`) with two steps: `fetch_raw()` gets raw data from an API or website, and `normalize()` converts it into one common format (`TrendingItemCreate`).
2. **Store.** `AbstractFetcher.execute()` in `base.py` retries failed fetches with exponential backoff, upserts items (deduplicated by source + external ID), writes a trend snapshot, and logs the run in the `fetch_logs` table.
3. **Enrich.** The AI sweep processes items in batches of 8: summary, category, India location, and a check that news items are really about the platform. If Gemini is unavailable, keyword heuristics are used.
4. **Cluster.** The clustering service groups items about the same story into Topics.
5. **Serve.** FastAPI exposes everything under `/api/v1/`, and the frontend is served as static files from `/static`.

**Scheduler jobs (APScheduler):**

| Job | Interval |
| :--- | :--- |
| Fetch each Category A source | every 15 min (per-source setting) |
| Fetch each Category B source | every 60 min (per-source setting) |
| AI sweep | every 5 min |
| Topic clustering | every 30 min, and after each full pipeline run |
| Snapshot pruning (older than 7 days) | every hour |

**Startup behavior:** On startup the app initializes the database and starts the scheduler. If any enabled source has no items from the last 12 hours, it starts the first fetch and AI sweep as a **background task**, so the server accepts requests right away.

---

## Data Sources and Provenance

SocialPulse separates first-party platform data (**Category A**) from derived signals (**Category B**), and never presents one as the other.

### Category A: Direct APIs (3 sources)

First-party data with real engagement numbers. Cards have a solid cyan border and an "OFFICIAL API" badge.

| Source | Data | Notes |
| :--- | :--- | :--- |
| **YouTube** | Most popular videos in India (`regionCode=IN`), merged with the News & Politics category (`videoCategoryId=25`) | Needs `YOUTUBE_API_KEY` |
| **Mastodon** | Trending hashtags from `mastodon.social` (`/api/v1/trends/tags`) | No key. Global, no regional data |
| **Bluesky** | Trending topics from the public AppView (`app.bsky.unspecced.getTrendingTopics`) | No key. Global, no regional data |

### Category B: Derived signals (6 sources)

Search interest and news coverage. Cards have a dashed amber border, a "SEARCH INTEREST" or "NEWS COVERAGE" badge, and a "Read Article →" link. They never claim to be a direct social media post.

| Source | Data |
| :--- | :--- |
| **Google Trends** | Daily search trends for India via the Google Trends RSS feed, optionally enriched with state-level interest through `pytrends` for the top 3 trends. Non-English queries are translated to English. |
| **News Coverage: Instagram, Facebook, X (Twitter), Reddit, Twitch** | Journalism *about* each platform's trends. Articles come from RSS feeds and section pages of up to 30 configured outlets (`backend/services/news_sources.py`) plus Google News RSS searches. |

**News filtering.** An article is kept only if it is a genuine third-party news URL (not a social post or raw Google link), mentions the platform, and mentions a trend/viral keyword. Duplicates are removed by normalized URL and by near-duplicate title (more than 80% token overlap). Articles older than 30 days are dropped, and results are cached for 10 minutes. Some outlets block scrapers, and the list of tested-and-dropped outlets is kept in `DROPPED_OUTLETS_LOG`.

### Sample data (fallback)

Each source has a sample file in `backend/mock/`. Sample data is used when:

- `MOCK_FETCH_MODE=true` and the source is not listed in `LIVE_SOURCES`, or
- a live fetch fails (the fetch is then logged as `fallback_mock` and shows as "degraded" in Source Health), or
- a live fetch returns fewer than 4 items (the sample items are added as supplements).

Sample items have their dates regenerated so they look recent, and sample news URLs are illustrative and may not point to real articles. For real data, run in live mode and check the **Source Health** page.

### Trending region (fallback chain)

Every item gets a region label and a plain-language reason. The first rule that matches wins:

1. **Local.** A specific Indian city or state was found in the story (keyword matching or Gemini). Label example: "Bengaluru, Karnataka". Basis: *Location detected from the story content*.
2. **Country.** The story is a nationwide Indian story, or the source is queried for India (Google Trends `geo=IN`, YouTube `regionCode=IN`). Label: "India".
3. **Global.** No regional filter is available for the source. Label: "Global".

For news items, the location is where the *story happened*, not where it is trending by traffic.

---

## Configuration Reference

All settings are environment variables, read from `.env` (copy `.env.example`).

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MOCK_FETCH_MODE` | `true` | `true` uses sample data for sources not in `LIVE_SOURCES`. `false` runs every source live. |
| `MOCK_AI_MODE` | `true` | `true` uses keyword heuristics instead of Gemini. |
| `LIVE_SOURCES` | all 9 sources | Comma-separated sources that always run live. **Set it empty (`LIVE_SOURCES=`) to force sample data.** |
| `GEMINI_KEY` | empty | Google Gemini API key for AI summaries and clustering. |
| `GEMINI_KEY_SCRAP` | empty | Optional secondary Gemini API key specifically for Category B news discovery and fallback enrichment, isolating news scraping from core AI quotas. |
| `YOUTUBE_API_KEY` | empty | YouTube Data API v3 key. Without it YouTube falls back to sample data. |
| `DATABASE_URL` | empty | PostgreSQL URL for persistent history. Empty uses local SQLite. |
| `DB_PATH` | `socialpulse.db` | SQLite file name when `DATABASE_URL` is empty. |
| `PIPELINE_INTERVAL_MINUTES` | `15` | Defined in config, but the scheduler uses each source's own interval from the database. |

`.env.example` also lists keys for services that are not used by the current 9 sources (NewsAPI, GNews, Reddit, Twitch, Pinterest). You can leave them empty.

---

## Running in Live Mode

For real data, edit `.env`:

```ini
MOCK_FETCH_MODE=false
MOCK_AI_MODE=false
GEMINI_KEY=your_gemini_key
YOUTUBE_API_KEY=your_youtube_key
```

and remove the `LIVE_SOURCES=` line (or list the sources you want live).

**Getting the keys:**

- **YouTube:** in the [Google Cloud Console](https://console.cloud.google.com/), create a project, enable *YouTube Data API v3*, then create an API key under *APIs & Services → Credentials*.
- **Gemini:** create a key in [Google AI Studio](https://aistudio.google.com/).

**Important notes about Gemini:**

- **Free-tier limits are small.** Quotas apply per model, per minute and per day, and they can change. A daily limit as low as 20 requests per model has been observed. When a model's quota is exhausted, summaries stay "pending" and retry on the next sweep.
- **Model names change.** If you see `404 ... model is no longer available`, list the models your key can use:
```bash
  python -W ignore -c "import os; from dotenv import load_dotenv; import google.generativeai as genai; load_dotenv(); genai.configure(api_key=os.getenv('GEMINI_KEY')); [print(m.name) for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]"
```
  and update the model names in `backend/services/ai_processor.py`, `backend/services/clustering.py` and `backend/utils/translator.py`.
- **The app works without Gemini.** With `MOCK_AI_MODE=true` you get keyword-based categories and locations, template summaries, and Jaccard-only clustering.
- The `google-generativeai` package prints a deprecation warning at startup. It still works, but Google recommends migrating to the newer `google-genai` package.

---

## Algorithms Explained

### 1. Trend momentum

Every fetch stores a snapshot of each item's rank and engagement (`trend_snapshots` table, with a 5-minute deduplication window and 7-day retention). Momentum is computed from the snapshots:

$$\Delta rank = rank_{first} - rank_{last} \qquad G = \frac{(V_{last} - V_{first}) / \Delta t_{hours}}{\max(V_{first}, 1)}$$

A positive $\Delta rank$ means the item climbed toward #1. $G$ is relative engagement growth per hour.

| State | Rule (constants in `backend/services/momentum.py`) |
| :--- | :--- |
| **tracking** | Fewer than 3 snapshots, or they span less than 30 minutes (and the item was first seen more than 60 minutes ago). The UI says momentum needs a few fetch cycles. |
| **new** | Fewer than 3 snapshots (or span under 30 minutes), and first seen within the last 60 minutes. |
| **surging** | $\Delta rank \ge 3$ **or** $G \ge 0.25$ per hour |
| **cooling** | $\Delta rank \le -3$ **or** $G \le -0.05$ per hour |
| **peaking** | Not surging or cooling, and current rank is 5 or better, or engagement is in the top 20% for its source |
| **steady** | Everything else |

Snapshots for a whole page of results are loaded in a single query, so there is no N+1 query problem. The `sort=momentum` option ranks by growth rate, then rank change.

### 2. Cross-platform story clustering

Goal: find items from different sources that report the **same real-world event**.

1. **Candidates.** Items fetched in the last 24 hours.
2. **Normalize titles.** Lowercase, strip punctuation, remove stopwords, drop tokens of 2 characters or fewer and pure numbers.
3. **Offline pass (Jaccard + union-find).** Compute the Jaccard similarity between every pair of titles:
   $$J(A, B) = \frac{|A \cap B|}{|A \cup B|}$$
   Pairs with $J \ge 0.5$ are merged using a Disjoint Set Union (union-find) structure. This works with no network, and is the fallback whenever Gemini is unavailable.
4. **Gemini pass.** When Gemini is available, up to 60 compact items per call (maximum 2 calls per run) are sent with strict instructions to group only items about the *exact same event*, not the same broad theme.
5. **Validation.** Every ID returned by the model must exist in the request, an ID can appear in only one group, and groups need at least 2 items. Invalid groups are dropped. On a parse failure the call is retried once, then the Jaccard result is used for that batch.
6. **Incremental tracking.** New items are first compared with active topics (Jaccard $\ge 0.4$) before new topics are created. Topics with no new items for 48 hours become inactive.
7. **Convergence rule.** A topic counts as cross-platform only if it has items from **2 or more distinct sources**. Two articles from the same source do not count.
8. **Summaries.** Up to 5 new cross-platform topics are summarized in one batched Gemini call, keeping hedging words like "reportedly" for unverified claims.

Clustering runs every 30 minutes and after each full pipeline run, protected by a lock so two runs never overlap.

### 3. AI enrichment

Items are processed in batches of 8 per Gemini call, returning JSON with `summary`, `category`, `location_india` and `is_platform_trend`. Rules in the prompt: preserve uncertainty for unverified claims, never classify creator or streaming drama as Health, avoid generic template text, and only fill the location when the story is genuinely tied to that place. The code validates IDs, retries once on a parse error, falls back to single-item calls for missing items, and uses a sliding-window rate limiter (5 requests per 62 seconds) across models. Off-topic news items are removed only when a platform has more than 8 items, so no platform's feed becomes empty.

### 4. Source health states

| State | Meaning |
| :--- | :--- |
| **healthy** | Last fetch succeeded and is newer than 2 × the fetch interval |
| **stale** | Last fetch succeeded but is older than 2 × the fetch interval |
| **degraded** | Last fetch fell back to sample data, or the 24-hour success rate is below 80% |
| **error** | The last fetch failed |
| **disabled** | The source is turned off |
| **never_run** | No fetch has been logged yet |

### 5. CSV export protection

Spreadsheet apps treat cells starting with `=`, `+`, `-` or `@` as formulas (CWE-1236). The export prefixes such cells with a single quote so they stay plain text. Exports are capped at 5,000 rows.

### 6. Recency rules

"Recency" means different things for different sources. **Chart-style sources** (YouTube, Google Trends, Mastodon, Bluesky) use the time they were fetched, because "trending now" means "currently on the chart". **News sources** use the article's publication time, falling back to the fetch time.

---

## API Reference

Interactive documentation is at `/docs`. All paths are under `/api/v1` unless noted.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` (no prefix) | System health, database connection, mock flags, enabled sources |
| `GET` | `/trends` | List items. Filters: `source` (repeatable), `source_category` (A/B), `category`, `recency` (6h/12h/24h/all), `region_scope` (all/india/global/local), `sort` (recency/engagement/momentum), `page`, `per_page` |
| `GET` | `/trends/{id}` | Full item details with trending region and momentum |
| `GET` | `/trends/{id}/history` | Snapshot series (rank and engagement over time) |
| `GET` | `/trends/{id}/comments` | Sourced real community comments and sentiment breakdown for YouTube trending items |
| `GET` | `/trends/export.csv` | CSV export using the same filters as `/trends` |
| `GET` | `/topics` | Macro stories. Params: `min_sources` (default 2), `recency` |
| `GET` | `/topics/{id}` | One story with all member items |
| `GET` | `/topics/{id}/comments` | Cross-platform discussion reactions for a macro story topic |
| `GET` | `/analytics/overview` | Aggregates: category breakdown, platform share, provenance ratio, top locations, hourly volume, AI coverage. Param: `recency` |
| `GET` | `/sources` | All sources and their configuration |
| `GET` | `/sources/health` | Health state, 24h success rate and last fetch for every source |
| `GET` | `/sources/{slug}/logs` | Recent fetch logs for a source |
| `GET` | `/sources/{slug}/status` | Status and 24h item count for one source |
| `GET` | `/categories` | Categories with item counts |
| `GET` | `/pipeline/status` | Pipeline state, last run time, item and AI counts |
| `POST` | `/pipeline/run` | Run a fetch cycle for all sources (`?force_live=true` to force live) |
| `POST` | `/pipeline/run/{slug}` | Run a fetch cycle for one source |
| `POST` | `/pipeline/process-ai` | Run the AI sweep (`?limit=50`) |

---

## Project Structure

```
SocialPulse/
├── backend/
│   ├── main.py                 # FastAPI app, startup, static files
│   ├── config.py               # Environment settings
│   ├── database.py             # SQLAlchemy engine (SQLite or Postgres)
│   ├── models.py               # Source, Category, TrendingItem, FetchLog, Topic, TrendSnapshot
│   ├── schemas.py              # Pydantic response models
│   ├── seed.py                 # Seeds the 9 sources and 12 categories
│   ├── migrations.py           # Adds new columns to existing databases
│   ├── fetchers/               # One fetcher per source (base.py = shared logic)
│   ├── routers/                # API endpoints (trends, topics, analytics, sources, ...)
│   ├── services/
│   │   ├── orchestrator.py     # Runs fetch cycles
│   │   ├── scheduler.py        # Background jobs
│   │   ├── ai_processor.py     # Gemini enrichment
│   │   ├── clustering.py       # Macro story clustering
│   │   ├── momentum.py         # Trend velocity
│   │   ├── news_coverage.py    # News scraping engine
│   │   ├── news_sources.py     # Configured news outlets
│   │   └── mock_ai.py          # Keyword heuristics (categories, locations)
│   ├── utils/                  # Rate limiter, translator
│   └── mock/                   # Sample data files
├── frontend/
│   ├── index.html
│   ├── css/styles.css
│   ├── js/                     # app.js, api.js, utils.js
│   │   └── views/              # topics.js, analytics.js, health.js
│   └── assets/icons/           # Platform icons
├── test_*.py                   # Test suites
├── render.yaml                 # Render deployment config
├── requirements.txt
└── .env.example
```

Some files are leftovers from earlier versions and are not used by the current 9 sources: `reddit_fetcher.py`, `twitch_fetcher.py` and `pinterest_fetcher.py` in `backend/fetchers/`, and some sample files in `backend/mock/` (for example Hacker News, GitHub, Dev.to, Lemmy, Giphy, Wikipedia and Reddit).

---

## Testing

```bash
python -m pytest test_phase1.py test_phase2.py test_phase3.py test_e2e.py test_phase8.py test_comments.py -v
```

All tests run offline in mock mode and make no real Gemini calls.

| File | Covers |
| :--- | :--- |
| `test_phase1.py` | Database seeding (9 sources), mock normalization, deduplication, fetch logging |
| `test_phase2.py` | REST endpoints, Category A/B separation, recency filtering |
| `test_phase3.py` | Frontend delivery, static assets, platform icons |
| `test_e2e.py` | Cold-start pipeline across all sources |
| `test_phase8.py` | Momentum states, clustering validation, analytics, source health, CSV injection guard |
| `test_comments.py` | Community comments, YouTube comment thread retrieval, sentiment classification, topic reactions |

`test_phase7.py` calls the **real Gemini API** and needs a valid `GEMINI_KEY`. It is not part of the offline suite.

---

## Deployment (Render)

The repository includes a `render.yaml` for a free Render web service.

1. Push the repository to GitHub and create a new **Web Service** on [Render](https://render.com) from it.
2. Set the environment variables: `GEMINI_KEY`, `YOUTUBE_API_KEY`, and `DATABASE_URL`.
3. The start command is `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.

**Use a persistent database.** Render's free disk is temporary, so a local SQLite file is wiped on redeploy or sleep, and trend history (momentum, sparklines) would be lost. Create a free PostgreSQL database (for example on Neon or Supabase) and paste its connection string into `DATABASE_URL`. Both `postgres://` and `postgresql://` URLs are accepted.

**The free tier sleeps when idle**, and background jobs only run while the service is awake.

---

## Troubleshooting

| Problem | Fix |
| :--- | :--- |
| `ERR_CONNECTION_REFUSED` / "localhost refused to connect" | The server is not running yet. Check the terminal for `Application startup complete.` |
| `ModuleNotFoundError: No module named 'backend'` | Run commands from the project root (the folder containing `backend/`), not from inside `backend/`. |
| `uvicorn` is not recognized | Use `python -m uvicorn ...`, and make sure the virtual environment is active. |
| Port 8000 already in use | Stop the old server (`Get-Process python \| Stop-Process -Force` on Windows) or use `--port 8001`. |
| `no such column` / `no such table` | Delete `socialpulse.db`, `socialpulse.db-wal` and `socialpulse.db-shm`, then run `python -m backend.seed`. |
| Page is empty at first | Data loads in the background after startup. Wait a minute and refresh. |
| Cards look generic or the AI summary says "pending" | Mock AI mode is on, or Gemini quota is used up. Check `/health` and the terminal logs. |
| Everything shows sample data | Check `MOCK_FETCH_MODE`, and make sure `LIVE_SOURCES` is not empty if you want live data. |
| Gemini `404 model is no longer available` | Update the model names (see [Running in Live Mode](#running-in-live-mode)). |
| Gemini `429 / RESOURCE_EXHAUSTED` | The free-tier limit was reached. Wait for the reset or use `MOCK_AI_MODE=true`. |
| YouTube shows no live items | Set `YOUTUBE_API_KEY`, and check the YouTube row in **Source Health** for the error. |
| `pip install` fails on `psycopg2-binary` | Use Python 3.11 or 3.12. |

---

## Known Limitations

1. **Sample data can appear in live mode.** A failed or thin live fetch is topped up with sample items (see [Sample data](#sample-data-fallback)). Check Source Health to see which sources are degraded.
2. **Momentum needs time.** It needs at least 3 snapshots spanning 30 minutes, so new items show "Tracking…". With SQLite on a free host, history is lost when the disk resets.
3. **Momentum for news items reflects list position.** News fetchers rank articles by their position in a list sorted by recency, so their rank changes do not measure real trend movement. Treat momentum as meaningful mainly for YouTube, Google Trends, Mastodon and Bluesky.
4. **Clustering is probabilistic.** It uses token overlap and a language model, so distinct developments in the same news cycle may occasionally be merged or split. Without Gemini, titles from different platforms rarely overlap enough to be linked.
5. **Region means where the story happened, not where it trends.** Only Google Trends (and YouTube's chart) are filtered to India as a whole. Mastodon and Bluesky have no regional data, so they show "Global".
6. **News scraping depends on third-party sites.** Outlets can block scrapers or change their pages. The number of articles kept per platform is often small, because strict relevance filters reject most headlines.
7. **Free-tier AI limits.** Gemini quotas are small and change over time, so AI summaries may lag behind the data.
8. **No user accounts.** The watchlist and bookmarks live in your browser's `localStorage` and are not shared between devices.

---

## License

MIT License. Developed for educational, research and social intelligence demonstration.
