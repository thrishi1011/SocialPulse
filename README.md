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
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete.`, then open:

| URL | What it is |
| :--- | :--- |
| http://localhost:8000 | Dashboard |
| http://localhost:8000/docs | Interactive API docs (Swagger) |
| http://localhost:8000/health | Health check (shows mock/live mode) |

**Note:** The page opens immediately. If the database is empty or the data is older than 12 hours, the first data load runs in the background, so cards may take a minute or two to appear. Refresh the page after a short wait.

### Running it again later

From the project folder, with the virtual environment active:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Stop the server with `Ctrl+C`.

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
- **Scheduler.** Background jobs fetch each source on its own interval, run the AI sweep, cluster stories, and prune old snapshots.

---

## How It Works (Architecture)

```
 ┌──────────────┐   ┌─────────────┐   ┌────────────────┐   ┌─────────────┐
 │ Data Sources │──▶│ Fetchers    │──▶│ SQLite / Post- │──▶│ FastAPI     │──▶ Frontend
 │ (APIs & RSS) │   │ Normalizer  │   │ greSQL (Models)│   │ (REST API)  │    (SPA)
 └──────────────┘   └─────────────┘   └────────────────┘   └─────────────┘
                           │                  ▲
                           ▼                  │
                    ┌─────────────┐           │
                    │ Background  │───────────┘
                    │ Scheduler   │  (momentum, clustering, AI)
                    └─────────────┘
```

The system runs on two layers:

1. **FastAPI backend (`backend/`):**
   - Connects to SQLite (development) or PostgreSQL (production).
   - Ingests data through source-specific fetchers (`backend/fetchers/`).
   - Normalizes every trend into a single schema: title, source, engagement metric, URL, rank, and publish time.
   - Saves a `TrendSnapshot` on every fetch so momentum can be tracked over time.
   - An APScheduler instance runs background tasks every 15 minutes: fetching sources on staggered intervals, calling the AI processor, clustering related stories, and cleaning up snapshots older than 7 days.
   - Exposes REST endpoints under `/api/v1/` for items, sources, stories, analytics, categories, and pipeline controls.

2. **Vanilla JavaScript frontend (`frontend/`):**
   - Single-page application without a build step, using CSS custom properties for a dark theme and canvas-drawn particle graphics.
   - Hash-based router: `#/feed`, `#/topics` (stories), `#/analytics`, `#/health`, `#/watchlist`, and `#/bookmarks`.
   - Modals: detail drawer with provenance information, raw JSON viewer, and CSV export.
   - Stores the user's watchlist, bookmarks, and muted topics in `localStorage`.

---

## Data Sources and Provenance

SocialPulse tracks **9 active sources** across two categories:

### Category A: Direct Official APIs (3 sources)

Real-time, first-party data from the platforms themselves:

| Source | How it works | Metrics shown |
| :--- | :--- | :--- |
| **YouTube** | YouTube Data API v3 (`videos.list?chart=mostPopular`, India / `regionCode=IN`). In addition, it fetches `videoCategoryId=25` (News & Politics) with pagination to ensure strong news coverage. | Views, likes |
| **Mastodon** | Public API on `mastodon.social` (`/api/v1/trends/tags`, `/api/v1/trends/statuses`). Captures Fediverse discourse. | Uses, accounts |
| **Bluesky** | AT Protocol AppView Trends API (`app.bsky.unspecced.getTaggedSuggestions`). | Post count |

*UI style:* Solid cyan border, "OFFICIAL API" badge, filled-dot indicator, and a button linking to the platform.

### Category B: Derived / Journalistic Signals (6 sources)

Platforms that do not offer open, affordable trending endpoints (for example, the X Trends endpoint requires enterprise pricing, and Meta has no public trending endpoint). SocialPulse tracks them through news coverage and search data:

| Source | How it works |
| :--- | :--- |
| **Google Trends** | Live RSS feed for India search queries, enriched with PyTrends state-level interest data. |
| **News: Instagram** | Technology and culture news reporting on viral Instagram trends, Reels, and platform policies. |
| **News: Facebook** | News coverage of Facebook community discussions, viral posts, and public debates. |
| **News: X (Twitter)** | News articles about viral tweets, trending topics, and policy announcements on X. Strict regex filters prevent bare "X" false positives (like iPhone X or Tesla Model X). |
| **News: Reddit** | Reporting on notable Reddit threads, discoveries, and community discussions. |
| **News: Twitch** | Gaming and streaming news covering record-breaking livestreams and creator events. |

*UI style:* Dashed amber border, "SEARCH INTEREST" or "NEWS COVERAGE" badge, diamond indicator, and a "Read Article →" button that points to the third-party publisher, never implying a direct social post.

#### How news coverage is fetched

The news fetchers query 57 verified Indian and international news outlet RSS feeds, Google News RSS, Bing News RSS, and GDELT DOC 2.0. Every headline is filtered to make sure it is genuinely about the platform, cleaned, deduplicated, and linked directly to the original publisher (Google News redirect URLs are unwrapped and cached).

If a category B source has fewer than 20 items in a 24-hour window, the API automatically expands the time range (3 days, 7 days, up to 30 days) and returns a `window_widened_to` note so the UI can explain why older articles are shown.

---

## Configuration Reference

Configuration is read from `.env` using Pydantic Settings.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MOCK_FETCH_MODE` | `true` | When `true`, fetchers return sample data from `backend/mock/` instead of calling outside APIs. |
| `MOCK_AI_MODE` | `true` | When `true`, summaries and categories are generated with rules and keywords, without calling Gemini. |
| `LIVE_SOURCES` | *(all 9)* | Comma-separated list of sources allowed to run live. Set to empty (`LIVE_SOURCES=`) when using sample data. |
| `GEMINI_KEY` | *(empty)* | Google AI Studio key (`AQ...` or `AIzaSy...`) for live summaries and story clustering. |
| `YOUTUBE_API_KEY` | *(empty)* | Google Cloud key with YouTube Data API v3 enabled. |
| `NEWSAPI_KEY` | *(empty)* | Optional. Used by news fetchers if available. |
| `GNEWS_KEY` | *(empty)* | Optional. Secondary fallback for news fetchers. |
| `DATABASE_URL` | *(empty)* | Database connection string. If empty, defaults to a local SQLite file. Accepts `postgresql://` and `sqlite:///`. |
| `DB_PATH` | `socialpulse.db` | Path to the SQLite database file if `DATABASE_URL` is not set. |
| `PIPELINE_INTERVAL_MINUTES` | `15` | How often the background scheduler runs a fetch cycle. |
| `NEWS_WINDOW_DAYS` | `7` | How many days of news articles to keep during an ingestion sweep. |
| `POLITICS_TARGET_SHARE` | `0.40` | Target fraction of political news in category B feeds. |

---

## Running in Live Mode

To switch from sample data to live data:

1. **Get an AI key (free):** Generate a Gemini key at [Google AI Studio](https://aistudio.google.com/).
2. **Get a YouTube key (free tier):** In the [Google Cloud Console](https://console.cloud.google.com/), create a project, enable the **YouTube Data API v3**, and create an API key under Credentials.
3. Edit your `.env` file:

```ini
MOCK_FETCH_MODE=false
MOCK_AI_MODE=false
LIVE_SOURCES=youtube,mastodon,bluesky,google_trends,instagram_news,facebook_news,twitter_news,reddit_news,twitch_news
GEMINI_KEY=your_gemini_key_here
YOUTUBE_API_KEY=your_youtube_key_here
```

4. Restart the server:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Mastodon, Bluesky, Google Trends, and all five News Coverage sources require **no API keys** to run live. They will start fetching real data immediately.

### Sample data fallback

If a live source fails (for example: rate limits, missing key, or network issue), it automatically falls back to bundled sample data and records the problem in `fetch_logs`. You can check which sources are live and which are using sample data at `http://localhost:8000/health` or on the **Source Health** tab (`#/health`).

---

## Algorithms Explained

### 1. Topic Clustering (Macro Stories)

Related trends from different platforms are grouped using a two-pass algorithm:

- **Pass 1 — Token overlap (Jaccard similarity).** Headlines are cleaned (removing punctuation, common stopwords, and platform names), stemmed, and compared using word-level Jaccard similarity. Pairs scoring above 0.35 are merged into candidate clusters using Disjoint Set Union (DSU).
- **Pass 2 — Gemini verification and naming.** If Gemini is configured, candidate clusters are sent to the model to confirm that the items are genuinely about the same event, give the story an editorial title, write a 2–3 sentence summary comparing how platforms cover it, and pick a primary category.
- **Convergence rule:** A group is only shown as a Macro Story if it contains items from at least 2 distinct platforms. Groups from a single source are discarded.
- **Lifecycle:** New trends are compared against active stories before creating new ones. Stories with no new items for 48 hours are closed.

### 2. Trend Momentum and Velocity

Snapshots of each item's rank and engagement are saved on every fetch cycle. Once an item has at least 3 snapshots spanning at least 30 minutes, the engine computes:

$$\Delta\text{Rank} = \text{Rank}_{\text{earliest}} - \text{Rank}_{\text{latest}}$$

$$\text{Velocity} = \frac{\Delta\text{Rank}}{\Delta t\text{ (hours)}}$$

The slope of a linear regression across all snapshot ranks determines the state:

| State | Badge | When it triggers |
| :--- | :--- | :--- |
| **Surging** | 🚀 Surging | Rank improved by $\ge 3$ positions and is still climbing |
| **Peaking** | 🔥 Peaking | Item reached the top 3 (or improved by $\ge 5$), but is now leveling off |
| **Cooling** | 📉 Cooling | Rank dropped by $\ge 3$ positions |
| **Steady** | ⏸️ Steady | Rank has not changed by more than 2 positions |
| **New** | ✨ New | First seen within the past 2 hours, fewer than 3 snapshots |
| **Tracking** | ⏳ Tracking | Ingested, but needs more snapshots before a trend can be calculated |

Cards in the UI include a 7-point inline SVG sparkline showing rank history over the last 24 hours.

### 3. Trending Region Fallback Chain

Every item resolves to a region and an explanation:

1. **City / State:** If the text clearly mentions an Indian location (e.g. "Bengaluru", "Maharashtra"), it is tagged with that city or state.
2. **India (National):** If it comes from Google Trends India, YouTube's India chart, or Indian news desks.
3. **Global:** For decentralized sources (Mastodon, Bluesky) that have no regional filters.

The UI displays the tag (e.g. `📍 Bengaluru, Karnataka` or `🌐 Global`) alongside a tooltip explaining how the location was determined.

---

## API Reference

Interactive documentation is available at `http://localhost:8000/docs`.

### Trends

- `GET /api/v1/trends` — Returns paginated trending items. Supports filtering by:
  - `source` (e.g. `?source=youtube&source=bluesky`)
  - `source_category` (`A` or `B`)
  - `recency` (`6h`, `12h`, `24h`)
  - `category` (e.g. `Technology`, `Sports`, `Politics`)
  - `region` (e.g. `india`, `global`)
  - `velocity` (`surging`, `cooling`, `peaking`, `steady`, `new`, `tracking`)
  - `sort` (`recency`, `engagement`, `velocity`)
  - `page`, `per_page`
- `GET /api/v1/trends/{id}` — Returns a single item with its full snapshot history, raw JSON payload, and resolved location metadata.
- `GET /api/v1/trends/export/csv` — Exports the filtered list as a CSV file with formula-injection sanitization.

### Stories (Clusters)

- `GET /api/v1/topics` — Lists active Macro Stories with platform coverage pills, cross-source counts, and member items.
- `GET /api/v1/topics/{id}` — Details for a single story.

### Analytics

- `GET /api/v1/analytics/overview` — Aggregated metrics: items by category, platform share, provenance ratio (A vs B), top locations, and AI coverage percentage.
- `GET /api/v1/analytics/timeline` — 24-hour hourly ingestion volume buckets.

### Source Health and Pipeline

- `GET /api/v1/sources` — Lists all sources with their category, configuration, and health status.
- `GET /api/v1/sources/{slug}/status` — Status, error messages, and metrics for a single source.
- `GET /api/v1/sources/{slug}/logs` — Ingestion execution logs for audit inspection.
- `POST /api/v1/pipeline/run` — Manually triggers an ingestion cycle across all sources (`?force_live=true`).
- `POST /api/v1/pipeline/run/{slug}` — Triggers ingestion for a single source.
- `POST /api/v1/pipeline/process-ai` — Triggers batch Gemini AI summarization on unprocessed items.
- `GET /health` — Health check, database connection status, and active sources count.

---

## Project Structure

```
SocialPulse/
├── backend/
│   ├── config.py               # Settings and environment loading
│   ├── database.py             # SQLAlchemy session and engine
│   ├── models.py               # Database tables
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── seed.py                 # Initial data seeding
│   ├── main.py                 # FastAPI application, routes, and lifecycle
│   ├── fetchers/               # Source-specific ingestion logic
│   │   ├── base.py             # Abstract base fetcher with retries
│   │   ├── youtube_fetcher.py
│   │   ├── mastodon_fetcher.py
│   │   ├── bluesky_fetcher.py
│   │   ├── google_trends_fetcher.py
│   │   └── *_news_fetcher.py   # Category B news fetchers
│   ├── services/
│   │   ├── ai_processor.py     # Gemini AI summarization and classification
│   │   ├── clustering.py       # Topic clustering (Macro Stories)
│   │   ├── news_coverage.py    # RSS news search, scraping, and URL unwrapping
│   │   ├── orchestrator.py     # Pipeline execution
│   │   └── scheduler.py        # Background task scheduler
│   └── mock/                   # Bundled sample data for offline mode
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
python -m pytest test_phase1.py test_phase2.py test_phase3.py test_e2e.py test_phase8.py test_news_coverage_fixes.py -v
```

All tests run offline in mock mode and make no real Gemini calls.

| File | Covers |
| :--- | :--- |
| `test_phase1.py` | Database seeding (9 sources), mock normalization, deduplication, fetch logging |
| `test_phase2.py` | REST endpoints, Category A/B separation, recency filtering |
| `test_phase3.py` | Frontend delivery, static assets, platform icons |
| `test_e2e.py` | Cold-start pipeline across all sources |
| `test_phase8.py` | Momentum states, clustering validation, analytics, source health, CSV injection guard |
| `test_news_coverage_fixes.py` | News coverage cap (80), Twitter/X regex, URL normalization, near-duplicate title dedup, window widening |

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
