import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "SocialPulse — Multi-Platform Social Media Trending Intelligence"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "socialpulse.db")
    _env_db_url: str = os.getenv("DATABASE_URL", "").strip()
    if _env_db_url:
        if _env_db_url.startswith("postgres://"):
            DATABASE_URL: str = "postgresql://" + _env_db_url[len("postgres://"):]
        else:
            DATABASE_URL: str = _env_db_url
    else:
        DATABASE_URL: str = f"sqlite:///{BASE_DIR / DB_PATH}"

    # Execution Modes
    MOCK_FETCH_MODE: bool = os.getenv("MOCK_FETCH_MODE", "true").lower() in ("true", "1", "yes")
    MOCK_AI_MODE: bool = os.getenv("MOCK_AI_MODE", "true").lower() in ("true", "1", "yes")
    # Comma-separated list of sources to run in LIVE mode even if MOCK_FETCH_MODE is true
    LIVE_SOURCES: list[str] = [
        s.strip().lower() for s in os.getenv(
            "LIVE_SOURCES",
            "youtube,mastodon,bluesky,google_trends,instagram_news,facebook_news,twitter_news,reddit_news,twitch_news"
        ).split(",") if s.strip()
    ]

    # Scheduler Settings
    PIPELINE_INTERVAL_MINUTES: int = int(os.getenv("PIPELINE_INTERVAL_MINUTES", "15"))
    NEWS_WINDOW_DAYS: int = int(os.getenv("NEWS_WINDOW_DAYS", "7"))
    POLITICS_TARGET_SHARE: float = float(os.getenv("POLITICS_TARGET_SHARE", "0.40"))

    # Reused Keys (from PulseDesk)
    NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "").strip()
    GNEWS_KEY: str = os.getenv("GNEWS_KEY", "").strip()
    GEMINI_KEY: str = os.getenv("GEMINI_KEY", "").strip()

    # Category A Official API Keys
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "").strip()
    GIPHY_API_KEY: str = os.getenv("GIPHY_API_KEY", "").strip()

    # Subreddit Curated List (Approved)
    REDDIT_SUBREDDITS: list[str] = [
        "all",
        "popular",
        "technology",
        "worldnews",
        "science",
        "gaming",
        "movies",
        "music"
    ]

    # Standard Categories
    CATEGORIES: list[dict[str, str]] = [
        {"name": "Technology", "color": "#3B82F6"},
        {"name": "Politics", "color": "#EF4444"},
        {"name": "Entertainment", "color": "#EC4899"},
        {"name": "Sports", "color": "#F97316"},
        {"name": "Science", "color": "#10B981"},
        {"name": "Gaming", "color": "#8B5CF6"},
        {"name": "Business", "color": "#EAB308"},
        {"name": "Health", "color": "#06B6D4"},
        {"name": "Culture", "color": "#6366F1"},
        {"name": "Breaking News", "color": "#DC2626"},
        {"name": "Lifestyle", "color": "#14B8A6"},
        {"name": "Other", "color": "#6B7280"}
    ]

settings = Settings()
