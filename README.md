# SocialPulse

**Multi-platform social media trending intelligence dashboard.**

SocialPulse collects trending topics from nine sources, converts them into a common format, adds AI summaries and categories, groups related items into cross-platform stories, and tracks changes over time. It is built with FastAPI, SQLAlchemy, and a vanilla JavaScript frontend.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Features](#features)
3. [How It Works](#how-it-works)
4. [Data Sources and Provenance](#data-sources-and-provenance)
5. [Configuration](#configuration)
6. [Running with Live Data](#running-with-live-data)
7. [Algorithms](#algorithms)
8. [API Reference](#api-reference)
9. [Project Structure](#project-structure)
10. [Testing](#testing)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)
13. [Known Limitations and Security Notes](#known-limitations-and-security-notes)
14. [License](#license)

---

## Quick Start

The app can run with sample data and without API keys.

**Requirements:** Python 3.11 or newer and Git.

### 1. Clone the repository

```bash
git clone https://github.com/thrishi1011/SocialPulse.git
cd SocialPulse
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux or macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Create the environment file

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux or macOS:**

```bash
cp .env.example .env
```

For a sample-data run, make sure `.env` contains:

```ini
MOCK_FETCH_MODE=true
MOCK_AI_MODE=true
LIVE_SOURCES=
```

`LIVE_SOURCES` must be empty to keep all fetchers in mock mode. If the variable is omitted, the application configuration defaults to the active source list, which can cause live fetches even when `MOCK_FETCH_MODE=true`.

### 5. Initialize the database

```bash
python -m backend.seed
```

### 6. Start the server

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open the dashboard at [http://127.0.0.1:8000](http://127.0.0.1:8000).

| URL | Purpose |
| :--- | :--- |
| `http://127.0.0.1:8000` | Dashboard |
| `http://127.0.0.1:8000/docs` | Interactive API documentation |
| `http://127.0.0.1:8000/health` | Application and database health |

The application starts its scheduler during startup. In live mode, an initial fetch may run in the background. Data may take a short time to appear.

Stop the server with `Ctrl+C`.

---

## Features

- **Live trends dashboard:** Browse items from nine active sources with filters for source, time range, region, category, and sort order.
- **Mastodon integration:** Fetch trending links, hashtags, and statuses from a configurable Mastodon instance.
- **Bluesky integration:** Fetch trending topics and popular posts through the Bluesky/AT Protocol APIs.
- **News coverage:** Collect journalism about trends associated with Instagram, Facebook, X, Reddit, and Twitch. These are news articles, not direct posts from those platforms.
- **AI summaries and categories:** Use Gemini to summarize and categorize items, with a heuristic fallback when AI is disabled or unavailable.
- **Trending regions:** Show an estimated location and the basis for that label where available.
- **Macro Stories:** Group related items from different sources into a cross-platform topic.
- **Trend momentum:** Store snapshots and display whether an item is new, tracking, surging, peaking, cooling, or steady.
- **Analytics:** View category breakdowns, source shares, locations, hourly item counts, and AI coverage.
- **Source Health:** Review fetch status, recent logs, duration, and success rates for each source.
- **Watchlist and bookmarks:** Save keywords and items in browser `localStorage`.
- **CSV export:** Export filtered trend results. Spreadsheet formula-like values are escaped.
- **Community discussion panel:** Fetch real YouTube comments when available and configured. Reactions shown for other sources, and fallback reactions, are generated examples rather than comments retrieved from those platforms.
- **Background scheduler:** Fetch sources, process AI summaries, cluster stories, and prune old trend snapshots.

---

## How It Works

```text
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│ Scheduler   │───▶│ Source       │───▶│ Database     │
│             │    │ fetchers     │    │ SQLite /     │
└─────────────┘    └──────────────┘    │ PostgreSQL   │
                         │             └──────┬───────┘
                         ▼                    │
                 ┌──────────────┐             ▼
                 │ Normalize    │     ┌──────────────┐
                 │ and validate │     │ AI summaries │
                 └──────────────┘     │ and topics   │
                                       └──────┬───────┘
                                              ▼
                                      ┌──────────────┐
                                      │ FastAPI      │
                                      │ REST API     │
                                      └──────┬───────┘
                                             ▼
                                      ┌──────────────┐
                                      │ JavaScript   │
                                      │ dashboard    │
                                      └──────────────┘
```

### Data flow

1. **Fetch:** Each source has a fetcher in `backend/fetchers/`. It obtains source data or loads sample data, depending on configuration and availability.
2. **Normalize:** Fetchers convert source-specific responses into the shared `TrendingItemCreate` format.
3. **Store:** The fetcher base class writes normalized items, deduplicates them by source and external ID, records snapshots, and logs fetch results.
4. **Enrich:** The AI processor adds summaries, categories, and location estimates. Heuristics are used when mock AI mode is enabled or no API key is available.
5. **Cluster:** The clustering service groups items that appear to describe the same event.
6. **Serve:** FastAPI exposes the data through `/api/v1/`, and serves the frontend from `/static`.

### Scheduled jobs

| Job | Interval |
| :--- | :--- |
| Category A source fetches | 15 minutes by default |
| Category B source fetches | 60 minutes by default |
| AI processing | 5 minutes |
| Topic clustering | 30 minutes |
| Snapshot cleanup | 1 hour; removes snapshots older than 7 days |

Each source has its own interval stored in the database. The `PIPELINE_INTERVAL_MINUTES` variable is defined in configuration, but the scheduler uses per-source intervals.

---

## Data Sources and Provenance

SocialPulse separates direct platform data (**Category A**) from search-interest and news signals (**Category B**).

### Category A: Direct platform APIs

| Source | Data collected | Credentials |
| :--- | :--- | :--- |
| **YouTube** | Popular videos for India, including the News & Politics category | `YOUTUBE_API_KEY` |
| **Mastodon** | Trending links, hashtags, and statuses from the configured instance | Optional access token; set `MASTODON_BASE_URL` to select an instance |
| **Bluesky** | Trending topics and popular posts | Public access can work without credentials. Optional session authentication uses a handle and app password. |

Mastodon data depends on the instance configured in `MASTODON_BASE_URL`. Results can vary between instances.

Bluesky fetches trending topics from the public API and searches popular posts for “news.” Credentials are optional for the public requests. When configured, the fetcher attempts to create an authenticated session.

### Category B: Search interest and news coverage

| Source | Data collected |
| :--- | :--- |
| **Google Trends** | Daily search trends for India, with optional state-level interest lookup. |
| **Instagram News** | Articles about Instagram trends and viral discussions. |
| **Facebook News** | Articles about Facebook trends and viral discussions. |
| **X (Twitter) News** | Articles about X/Twitter trends and viral discussions. |
| **Reddit News** | Articles about Reddit trends and viral discussions. |
| **Twitch News** | Articles about Twitch trends and viral discussions. |

News coverage is collected from configured RSS feeds, news sections, and Google News searches. Filters aim to keep relevant third-party journalism rather than social posts or raw Google News URLs. Outlets may block automated requests or change their pages, so the number of results can vary.

### Sample data and live results

Sample data is available in `backend/mock/`. It can be used when mock mode is active, when a live fetch fails, or when a fetcher applies its own fallback or supplementation behavior. For example, the Bluesky fetcher supplements small result sets with sample topics.

As a result, a live run can contain sample items. Check the **Source Health** page and item provenance when deciding whether a result came from a live fetch or fallback data. Sample URLs may be illustrative.

### Trending region

Region labels are estimates, and the first applicable rule is used:

1. **Local:** A city or state is detected in the story or assigned during enrichment.
2. **India:** The story is identified as nationwide, or the source is queried for India.
3. **Global:** The source does not provide a regional filter and no more specific region was assigned.

For news items, the location refers to where the story happened when the location can be identified. It does not mean that the item is trending in that location.

---

## Configuration

Copy `.env.example` to `.env`. The following settings are read by the application.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MOCK_FETCH_MODE` | `true` | Enables sample fetch behavior for sources not listed in `LIVE_SOURCES`. |
| `MOCK_AI_MODE` | `true` | Uses heuristic summaries and categories instead of Gemini. |
| `LIVE_SOURCES` | All nine active sources | Comma-separated source slugs forced to live mode. Set it to an empty value for sample-only fetches. |
| `GEMINI_KEY` | Empty | Gemini API key for AI processing. |
| `GEMINI_KEY_SCRAP` | Empty | Optional Gemini key used for Category B processing where configured. |
| `YOUTUBE_API_KEY` | Empty | YouTube Data API v3 key; needed for live YouTube data and live YouTube comments. |
| `MASTODON_API` | Empty | Mastodon bearer token. The code also accepts `MASTODON_ACCESS_TOKEN` and `MASTODON_API_KEY`. |
| `MASTODON_BASE_URL` | `https://mastodon.social` | Mastodon instance base URL. |
| `BLUESKY_API_KEY` | Empty | Bluesky app password. The code also accepts `BLUESY_API`, `BLUESKY_API`, and `BLUESKY_APP_PASSWORD`. |
| `BLUESKY_IDENTIFIER` | Configured default | Bluesky account handle or identifier. The code also accepts `BLUESKY_HANDLE`. |
| `DATABASE_URL` | Empty | PostgreSQL connection string. If empty, the app uses SQLite. |
| `DB_PATH` | `socialpulse.db` | SQLite database filename when `DATABASE_URL` is empty. |
| `PIPELINE_INTERVAL_MINUTES` | `15` | Defined in settings; source scheduling uses per-source database intervals. |

Keep API keys and app passwords in `.env` or your deployment provider’s secret settings. Do not commit them to GitHub.

The `.env.example` currently does not list all supported Mastodon and Bluesky settings. Add the relevant variables to your local `.env` when enabling those integrations.

---

## Running with Live Data

Set the sources you want to fetch live and add credentials where the source requires them. For example:

```ini
MOCK_FETCH_MODE=false
MOCK_AI_MODE=false
LIVE_SOURCES=youtube,mastodon,bluesky,google_trends,instagram_news,facebook_news,twitter_news,reddit_news,twitch_news

GEMINI_KEY=your_gemini_key
YOUTUBE_API_KEY=your_youtube_key

# Optional Mastodon token and instance
MASTODON_API=your_mastodon_access_token
MASTODON_BASE_URL=https://mastodon.social

# Optional Bluesky session credentials
BLUESKY_IDENTIFIER=your-handle.bsky.social
BLUESKY_API_KEY=your_bluesky_app_password
```

You can run only selected sources by listing their slugs in `LIVE_SOURCES`. Use `MOCK_FETCH_MODE=true` to keep other sources on sample data.

### Getting API credentials

- **YouTube:** In the [Google Cloud Console](https://console.cloud.google.com/), create a project, enable **YouTube Data API v3**, then create an API key under **APIs & Services → Credentials**. Add it to `.env` as `YOUTUBE_API_KEY`.

- **Gemini:** Create an API key in [Google AI Studio](https://aistudio.google.com/). Add it to `.env` as `GEMINI_KEY`.

- **Bluesky (optional):**
  1. Sign in to [Bluesky](https://bsky.app/).
  2. Open **Settings → Advanced → App Passwords** and create an app password. Do not use your main account password.
  3. Add your Bluesky handle and the app password to `.env`:

     ```ini
     BLUESKY_IDENTIFIER=your-handle.bsky.social
     BLUESKY_API_KEY=your-app-password
     ```

  The app can request public Bluesky trends without these credentials. The app password enables the authenticated session used by the fetcher. See the [Bluesky API reference](https://docs.bsky.app/docs/api/app-bsky-feed-get-author-feed).

- **Mastodon (optional):**
  1. Choose the Mastodon instance where your account is registered, for example [Mastodon.social](https://mastodon.social/).
  2. Sign in and open **Preferences/Settings → Development → New Application**.
  3. Create an application and copy its access token. Treat the token like a password.
  4. Add the token and instance URL to `.env`:

     ```ini
     MASTODON_BASE_URL=https://mastodon.social
     MASTODON_API=your-access-token
     ```

  Replace `https://mastodon.social` with your own instance URL if you use a different server. Some public trend endpoints may work without a token. See Mastodon’s [authentication guide](https://docs.joinmastodon.org/client/token/) for details.

## Algorithms

### 1. Trend momentum

The application stores item rank and engagement snapshots. Momentum is estimated by comparing snapshots over time.

- **New:** The item has only recently appeared.
- **Tracking:** There is not enough snapshot history to estimate movement.
- **Surging:** Rank or engagement growth passes configured thresholds.
- **Cooling:** Rank or engagement declines beyond configured thresholds.
- **Peaking:** The item has high rank or engagement but is not surging or cooling.
- **Steady:** None of the other states apply.

Momentum is a heuristic based on the data available for each source. News-source ranks can reflect article ordering rather than genuine social engagement growth.

### 2. Cross-platform story clustering

The clustering service looks for items that may describe the same event:

1. It selects recent items as candidates.
2. It normalizes titles by lowercasing and removing punctuation and common words.
3. It uses Jaccard title similarity as an offline grouping method.
4. When configured, Gemini can help group items and produce summaries.
5. Returned model groups are validated against the requested item IDs.
6. A topic is considered cross-platform when it includes items from at least two distinct sources.

Clustering is approximate. Related stories may be split, and different developments may occasionally be grouped together.

### 3. AI enrichment

When live AI mode is enabled and a Gemini key is available, the AI processor can generate summaries, categories, and location estimates. The application validates and cleans model output and uses heuristics when AI is disabled or unavailable.

Generated summaries are not independent verification of the underlying source. Review the original source links for important claims.

### 4. Source health

| State | Meaning |
| :--- | :--- |
| **healthy** | Recent fetch succeeded. |
| **stale** | The last successful fetch is older than expected. |
| **degraded** | A fetch used fallback data or the success rate is low. |
| **error** | The most recent fetch failed. |
| **disabled** | The source is disabled. |
| **never_run** | No fetch has been logged. |

### 5. CSV export protection

CSV export escapes values that begin with spreadsheet formula characters, such as `=`, `+`, `-`, or `@`, and limits the number of exported rows.

### 6. Recency rules

Chart-style sources use fetch time to represent what is currently appearing on a trend feed. News coverage uses publication time where available, falling back to fetch time.

---

## API Reference

Interactive API documentation is available at `/docs`. Endpoints are under `/api/v1` unless marked otherwise.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Application and database health. |
| `GET` | `/api/v1/trends` | List trends with source, category, region, recency, and sort filters. |
| `GET` | `/api/v1/trends/{id}` | Get trend details. |
| `GET` | `/api/v1/trends/{id}/history` | Get trend snapshot history. |
| `GET` | `/api/v1/trends/{id}/comments` | Get discussion data. YouTube comments can be retrieved live with a YouTube API key; other comments may be generated examples. |
| `GET` | `/api/v1/trends/export.csv` | Export the filtered trend list as CSV. |
| `GET` | `/api/v1/topics` | List cross-platform Macro Stories. |
| `GET` | `/api/v1/topics/{id}` | Get a Macro Story and its items. |
| `GET` | `/api/v1/topics/{id}/comments` | Get topic-level discussion reactions, which may include generated examples. |
| `GET` | `/api/v1/analytics/overview` | Get dashboard aggregates. |
| `GET` | `/api/v1/sources` | List configured sources. |
| `GET` | `/api/v1/sources/health` | Get source health and fetch status. |
| `GET` | `/api/v1/sources/{slug}/logs` | Get recent fetch logs. |
| `GET` | `/api/v1/sources/{slug}/status` | Get one source's status and item count. |
| `GET` | `/api/v1/categories` | List categories. |
| `GET` | `/api/v1/pipeline/status` | Get pipeline status. |
| `POST` | `/api/v1/pipeline/run` | Run a fetch cycle for sources. |
| `POST` | `/api/v1/pipeline/run/{slug}` | Run a fetch cycle for one source. |
| `POST` | `/api/v1/pipeline/process-ai` | Start AI processing for unprocessed items. |

---

## Project Structure

```text
SocialPulse/
├── backend/
│   ├── main.py                 # FastAPI app, startup, static frontend
│   ├── config.py               # Environment and API configuration
│   ├── database.py             # SQLAlchemy database setup
│   ├── models.py               # Database models
│   ├── schemas.py              # API response schemas
│   ├── seed.py                 # Database initialization and source seeding
│   ├── migrations.py           # Startup schema migrations
│   ├── fetchers/               # Source fetchers and shared normalization
│   ├── routers/                # Trends, topics, analytics, source, pipeline APIs
│   ├── services/
│   │   ├── orchestrator.py     # Coordinates source fetches
│   │   ├── scheduler.py        # Periodic background jobs
│   │   ├── ai_processor.py     # Gemini enrichment
│   │   ├── clustering.py       # Macro Story clustering
│   │   ├── momentum.py         # Trend movement calculations
│   │   ├── news_coverage.py    # News discovery and filtering
│   │   ├── news_sources.py     # Configured news outlets
│   │   └── comments_service.py # Retrieved or generated discussion data
│   ├── utils/                  # Helpers such as rate limiting and translation
│   └── mock/                   # Sample source and AI data
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/icons/
├── test_*.py                   # Automated tests
├── render.yaml                 # Render service configuration
├── requirements.txt
└── .env.example
```

Some fetcher and sample-data files may remain from earlier versions and are not used by the active nine-source configuration.

---

## Testing

Run the offline test suite from the repository root:

```bash
python -m pytest test_phase1.py test_phase2.py test_phase3.py test_e2e.py test_phase8.py test_comments.py -v
```

The listed suite is intended to use mock data and avoid real Gemini API calls. Review individual tests before running them if your local environment contains credentials or production data.

| Test file | Main coverage |
| :--- | :--- |
| `test_phase1.py` | Database seeding, source normalization, mock fetches, deduplication, fetch logging. |
| `test_phase2.py` | API endpoints, source categories, and recency filtering. |
| `test_phase3.py` | Frontend delivery and static assets. |
| `test_e2e.py` | Cold-start pipeline behavior. |
| `test_phase8.py` | Momentum, clustering validation, analytics, source health, CSV escaping. |
| `test_comments.py` | Comment data generation and sentiment classification. |
| `test_phase7.py` | Uses the real Gemini API and requires a valid `GEMINI_KEY`; run separately. |

---

## Deployment

The repository includes a `render.yaml` for Render.

1. Create a Render Web Service from the repository.
2. Configure the required environment variables in Render.
3. Use the configured start command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Use a persistent PostgreSQL database if trend history should survive service restarts or redeployments. A local SQLite database on temporary hosting storage may be lost.

The configured service runs the scheduler while the web service is active. Hosting sleep or restart behavior can interrupt scheduled work.

**Before exposing a deployment publicly, add authentication and authorization to the API.** In the current code, the API does not require user authentication, and CORS allows all origins. In particular, pipeline endpoints can trigger work. Do not treat the current deployment configuration as a production security boundary.

---

## Troubleshooting

| Problem | Suggested check |
| :--- | :--- |
| `ERR_CONNECTION_REFUSED` | Confirm that the server is running and check the terminal for startup errors. |
| `ModuleNotFoundError: No module named 'backend'` | Run commands from the repository root. |
| `uvicorn` is not recognized | Activate the virtual environment and run `python -m uvicorn ...`. |
| Port 8000 is in use | Stop the other local service or select another port. |
| Database schema errors | Back up important data, then initialize or migrate the database as appropriate. |
| Dashboard is empty at first | Wait for the initial fetch to finish and refresh the page. |
| Sample data appears in live mode | Check `MOCK_FETCH_MODE`, `LIVE_SOURCES`, and Source Health; some fetchers supplement short results with sample items. |
| AI summaries are pending | Check `MOCK_AI_MODE`, Gemini credentials, provider quotas, and application logs. |
| Mastodon has no live items | Check the configured instance URL and that its trends endpoints are available. |
| Bluesky has no live items | Check network access and, if using session authentication, the handle and app password. |
| YouTube has no live items or comments | Check `YOUTUBE_API_KEY`, API availability, and quota. |

---

## Known Limitations and Security Notes

1. **Sample data can be mixed with live data.** Failed or short fetches can trigger fallback or supplementation. Use Source Health and provenance information when interpreting results.
2. **Momentum is approximate.** News ranking changes do not necessarily represent social engagement changes.
3. **Clustering can be wrong.** Similar titles may be unrelated, and the same event may be described with different wording.
4. **Region labels are estimates.** Social platforms may not provide location data for trends.
5. **News collection depends on third parties.** RSS feeds and news pages can change, block automated clients, or become unavailable.
6. **AI output can be inaccurate.** Summaries and categories should be treated as assistance, not fact verification.
7. **Discussion data is not always sourced.** YouTube comments may be fetched from the API; reactions for other sources or fallback cases can be generated examples.
8. **No user accounts are implemented.** Watchlists and bookmarks are stored in browser `localStorage`.
9. **The API currently has no authentication.** Protect the service before deploying it to a public network, especially endpoints that start pipeline or AI jobs.
10. **CORS is permissive in the current configuration.** Restrict allowed origins before production deployment.

---

## License

Developed for educational, research, and social intelligence demonstration.
