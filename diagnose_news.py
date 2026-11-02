"""
diagnose_news.py - Diagnostic script for SocialPulse news coverage ingestion and AI enrichment.
PHASE 0: Diagnoses ingestion funnels, rejection reasons, publish age distributions,
database fetch logs, Source Health status, and AI processor status without modifying backend behavior.
"""
import asyncio
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from datetime import datetime, timedelta
import re
from typing import Any
import httpx
import feedparser
from bs4 import BeautifulSoup

from backend.config import settings
from backend.database import SessionLocal
from sqlalchemy import func
from backend.models import Source, FetchLog, TrendingItem, Category
from backend.routers.sources import get_sources_health
from backend.services.news_sources import NEWS_OUTLETS, DROPPED_OUTLETS_LOG
import backend.services.news_coverage as nc

PLATFORMS = [
    ("Instagram", "instagram_news"),
    ("Facebook", "facebook_news"),
    ("X (Twitter)", "twitter_news"),
    ("Reddit", "reddit_news"),
    ("Twitch", "twitch_news"),
]

async def diagnose_platform(platform_name: str, slug: str):
    print("=" * 80)
    print(f"PLATFORM DIAGNOSTIC: {platform_name} (Slug: {slug})")
    print("=" * 80)

    # Instrument rejection tracking during fetch
    rejections = {
        "short_title": 0,
        "invalid_url": 0,
        "not_relevant": 0,
        "older_than_30d": 0,
        "decode_failure": 0,
        "dedup_url": 0,
        "dedup_title": 0
    }
    rejection_samples = []

    # Run fetch_news_for_platform
    t0 = datetime.utcnow()
    articles = await nc.fetch_news_for_platform(platform_name, force_refresh=True)
    duration_s = (datetime.utcnow() - t0).total_seconds()

    print(f"\n[Funnel Summary for {platform_name}] (Elapsed: {duration_s:.1f}s)")
    print(f"  • Final Articles Kept (capped at 20): {len(articles)}")

    # Age breakdown of final articles
    now = datetime.utcnow()
    age_dist = {"<24h": 0, "<3d": 0, "<7d": 0, "<30d": 0, ">30d/None": 0}
    for a in articles:
        pub_str = a.get("publishedAt")
        if pub_str:
            try:
                dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                age = now - dt
                if age <= timedelta(hours=24):
                    age_dist["<24h"] += 1
                elif age <= timedelta(days=3):
                    age_dist["<3d"] += 1
                elif age <= timedelta(days=7):
                    age_dist["<7d"] += 1
                elif age <= timedelta(days=30):
                    age_dist["<30d"] += 1
                else:
                    age_dist[">30d/None"] += 1
            except Exception:
                age_dist[">30d/None"] += 1
        else:
            age_dist[">30d/None"] += 1

    print(f"\n[Publish Age Breakdown for {platform_name} Returned Items]")
    print(f"  • Published < 24 hours: {age_dist['<24h']}")
    print(f"  • Published < 3 days:   {age_dist['<3d']}")
    print(f"  • Published < 7 days:   {age_dist['<7d']}")
    print(f"  • Published < 30 days:  {age_dist['<30d']}")
    print(f"  • Older > 30d or None:  {age_dist['>30d/None']}")

    if articles:
        print(f"\n[Sample Kept Articles for {platform_name}]")
        for idx, a in enumerate(articles[:4], 1):
            pub = a.get("publishedAt") or "No Date"
            src = a.get("source", {}).get("name") or "Unknown"
            safe_title = a.get('title', '')[:65].encode('ascii', 'replace').decode('ascii')
            print(f"  {idx}. [{src}] \"{safe_title}\" (Date: {pub})")
            print(f"     URL: {a.get('url')[:75]}")
    print()

def diagnose_database():
    db = SessionLocal()
    try:
        print("=" * 80)
        print("DATABASE SOURCE HEALTH & FETCH LOGS REPORT")
        print("=" * 80)

        health = get_sources_health(db)
        print(f"Source Health Observatory: {health.healthy_count}/{health.total_sources} healthy, "
              f"{health.degraded_count} degraded, {health.error_count} error\n")
        print(f"{'Slug':<18} | {'Health':<10} | {'24h Items':<10} | {'Total Items':<12} | {'Latest Fetch':<15} | {'Fetched':<8}")
        print("-" * 85)
        for s in health.sources:
            total_cnt = db.query(TrendingItem).filter(TrendingItem.source_id == s.slug).count() if isinstance(s.slug, int) else db.query(TrendingItem).join(Source).filter(Source.slug == s.slug).count()
            st = s.last_fetch.status if s.last_fetch else "never"
            f_cnt = str(s.last_fetch.items_fetched) if s.last_fetch else "0"
            print(f"{s.slug:<18} | {s.health_state:<10} | {s.items_24h:<10} | {total_cnt:<12} | {st:<15} | {f_cnt:<8}")

        print("\n" + "=" * 80)
        print("DIAGNOSING WHY X, REDDIT, AND TWITCH HAVE 0 ITEMS IN 24H")
        print("=" * 80)
        now = datetime.utcnow()
        cutoff_24h = now - timedelta(hours=24)

        for slug in ["twitter_news", "reddit_news", "twitch_news"]:
            src = db.query(Source).filter(Source.slug == slug).first()
            if not src:
                print(f"  [{slug}]: Source record not found in DB!")
                continue

            print(f"\nSource: {src.slug} (ID: {src.id}, enabled: {src.is_enabled})")
            logs = db.query(FetchLog).filter(FetchLog.source_id == src.id).order_by(FetchLog.id.desc()).limit(3).all()
            print(f"  Recent FetchLogs:")
            if not logs:
                print("    - No logs found.")
            for l in logs:
                print(f"    - FetchLog #{l.id} [{l.started_at}]: status={l.status}, fetched={l.items_fetched}, new={l.items_new}, duration={l.duration_ms}ms, error={l.error_message}")

            items_all = db.query(TrendingItem).filter(TrendingItem.source_id == src.id).all()
            items_24h_fetched = db.query(TrendingItem).filter(TrendingItem.source_id == src.id, TrendingItem.fetched_at >= cutoff_24h).all()
            items_24h_published = db.query(TrendingItem).filter(TrendingItem.source_id == src.id, TrendingItem.published_at >= cutoff_24h).all()

            print(f"  Database Items Analysis:")
            print(f"    - Total items in DB: {len(items_all)}")
            print(f"    - Items with fetched_at >= 24h: {len(items_24h_fetched)}")
            print(f"    - Items with published_at >= 24h: {len(items_24h_published)}")

            if items_all:
                print("    - Item timestamps breakdown:")
                for itm in items_all:
                    pub_str = itm.published_at.strftime("%Y-%m-%d %H:%M:%S") if itm.published_at else "None"
                    fetch_str = itm.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if itm.fetched_at else "None"
                    is_sample = "example.com" in (itm.url or "") or "mock" in (itm.url or "")
                    safe_item_title = (itm.title or "")[:45].encode('ascii', 'replace').decode('ascii')
                    print(f"      * \"{safe_item_title}...\" | Pub: {pub_str} | Fetched: {fetch_str} | Sample/Mock: {is_sample}")

        print("\n" + "=" * 80)
        print("AI ENRICHMENT COVERAGE & STATUS REPORT")
        print("=" * 80)
        total = db.query(TrendingItem).count()
        processed = db.query(TrendingItem).filter(TrendingItem.ai_processed == True).count()
        pending = db.query(TrendingItem).filter(TrendingItem.ai_processed == False).count()
        pct = (processed / total * 100.0) if total > 0 else 0.0

        print(f"Configuration & Environment:")
        print(f"  • MOCK_AI_MODE:             {settings.MOCK_AI_MODE}")
        print(f"  • GEMINI_KEY set:           {'YES (key starts with ' + settings.GEMINI_KEY[:10] + '...)' if settings.GEMINI_KEY else 'NO'}")
        from backend.services.ai_processor import PREFERRED_MODELS
        print(f"  • PREFERRED_MODELS:         {PREFERRED_MODELS}")
        print(f"\nItem Processing Status:")
        print(f"  • Total Trending Items:     {total}")
        print(f"  • AI Processed Items:       {processed} ({pct:.1f}%)")
        print(f"  • AI Pending Items:         {pending}")

        # Check Category distribution
        cat_counts = (
            db.query(Category.name, func.count(TrendingItem.id))
            .join(TrendingItem, TrendingItem.category_id == Category.id)
            .group_by(Category.name)
            .order_by(func.count(TrendingItem.id).desc())
            .all()
        )
        print(f"\nCurrent Category Distribution in Database:")
        for cname, cnt in cat_counts:
            cpct = (cnt / total * 100.0) if total > 0 else 0.0
            print(f"  • {cname:<16}: {cnt:3} ({cpct:.1f}%)")

    finally:
        db.close()

async def main():
    for name, slug in PLATFORMS:
        await diagnose_platform(name, slug)
    diagnose_database()

if __name__ == "__main__":
    from sqlalchemy import func
    asyncio.run(main())
