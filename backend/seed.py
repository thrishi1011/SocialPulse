import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from backend.database import engine, Base, SessionLocal
from backend.models import Source, Category
from backend.config import settings

INITIAL_SOURCES = [
    # Category A: Direct Official APIs (3 sources)
    {
        "slug": "youtube",
        "display_name": "YouTube",
        "source_category": "A",
        "source_type_label": "Official API",
        "icon_filename": "youtube.svg",
        "is_enabled": True,
        "fetch_interval_min": 15
    },
    {
        "slug": "mastodon",
        "display_name": "Mastodon",
        "source_category": "A",
        "source_type_label": "Official API",
        "icon_filename": "mastodon.svg",
        "is_enabled": True,
        "fetch_interval_min": 15
    },
    {
        "slug": "bluesky",
        "display_name": "Bluesky",
        "source_category": "A",
        "source_type_label": "Official API",
        "icon_filename": "bluesky.svg",
        "is_enabled": True,
        "fetch_interval_min": 15
    },

    # Category B: Derived / Journalistic Signals (6 sources)
    {
        "slug": "google_trends",
        "display_name": "Google Trends",
        "source_category": "B",
        "source_type_label": "Search Interest",
        "icon_filename": "google-trends.svg",
        "is_enabled": True,
        "fetch_interval_min": 60
    },
    {
        "slug": "instagram_news",
        "display_name": "News Coverage: Instagram",
        "source_category": "B",
        "source_type_label": "News Coverage",
        "icon_filename": "instagram.svg",
        "is_enabled": True,
        "fetch_interval_min": 60
    },
    {
        "slug": "facebook_news",
        "display_name": "News Coverage: Facebook",
        "source_category": "B",
        "source_type_label": "News Coverage",
        "icon_filename": "facebook.svg",
        "is_enabled": True,
        "fetch_interval_min": 60
    },
    {
        "slug": "twitter_news",
        "display_name": "News Coverage: X (Twitter)",
        "source_category": "B",
        "source_type_label": "News Coverage",
        "icon_filename": "twitter.svg",
        "is_enabled": True,
        "fetch_interval_min": 60
    },
    {
        "slug": "reddit_news",
        "display_name": "News Coverage: Reddit",
        "source_category": "B",
        "source_type_label": "News Coverage",
        "icon_filename": "reddit.svg",
        "is_enabled": True,
        "fetch_interval_min": 60
    },
    {
        "slug": "twitch_news",
        "display_name": "News Coverage: Twitch",
        "source_category": "B",
        "source_type_label": "News Coverage",
        "icon_filename": "twitch.svg",
        "is_enabled": True,
        "fetch_interval_min": 60
    }
]

def init_db():
    """Create all tables in the database and run dynamic migrations."""
    Base.metadata.create_all(bind=engine)
    from backend.migrations import run_startup_migrations
    run_startup_migrations(engine)

def seed_db(db: Session | None = None):
    """Seed initial sources and categories if missing."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        # Remove deprecated sources
        valid_slugs = [s["slug"] for s in INITIAL_SOURCES]
        db.query(Source).filter(~Source.slug.in_(valid_slugs)).delete(synchronize_session=False)

        # Seed or Update Sources
        for src_data in INITIAL_SOURCES:
            existing = db.query(Source).filter(Source.slug == src_data["slug"]).first()
            if not existing:
                source = Source(**src_data)
                db.add(source)
            else:
                existing.display_name = src_data["display_name"]
                existing.source_category = src_data["source_category"]
                existing.source_type_label = src_data["source_type_label"]
                existing.icon_filename = src_data["icon_filename"]
                existing.fetch_interval_min = src_data["fetch_interval_min"]
                existing.is_enabled = src_data["is_enabled"]

        # Seed or Update Categories
        for cat_data in settings.CATEGORIES:
            existing = db.query(Category).filter(Category.name == cat_data["name"]).first()
            if not existing:
                category = Category(name=cat_data["name"], color=cat_data["color"])
                db.add(category)

        db.commit()
    finally:
        if should_close:
            db.close()

if __name__ == "__main__":
    init_db()
    seed_db()
    print(f"Database initialized and seeded {len(INITIAL_SOURCES)} sources successfully.")
