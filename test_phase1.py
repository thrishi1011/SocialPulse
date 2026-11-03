import asyncio
import os
import sys
import pytest
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings
from backend.database import engine, SessionLocal, Base
from backend.models import Source, Category, TrendingItem, FetchLog
from backend.seed import init_db, seed_db
from backend.fetchers import ALL_FETCHERS

ACTIVE_SLUGS = [
    # Category A (3)
    "youtube", "mastodon", "bluesky",
    # Category B (6)
    "google_trends", "instagram_news", "facebook_news",
    "twitter_news", "reddit_news", "twitch_news"
]

def test_phase1_database_and_seeding():
    print("=" * 60)
    print("RUNNING TEST 1: Database Initialization & Seeding")
    print("=" * 60)

    # Initialize tables
    init_db()
    db = SessionLocal()
    try:
        seed_db(db)

        sources = db.query(Source).all()
        categories = db.query(Category).all()

        print(f"[OK] Total sources seeded: {len(sources)}")
        for s in sources:
            print(f"  - [{s.source_category}] {s.slug:16} -> {s.display_name} ({s.source_type_label}) [Enabled: {s.is_enabled}]")

        cat_a_count = db.query(Source).filter(Source.source_category == "A", Source.is_enabled == True).count()
        cat_b_count = db.query(Source).filter(Source.source_category == "B", Source.is_enabled == True).count()

        assert len(sources) == 9, f"Expected 9 sources, found {len(sources)}"
        assert cat_a_count == 3, f"Expected 3 enabled Category A sources, found {cat_a_count}"
        assert cat_b_count == 6, f"Expected 6 enabled Category B sources, found {cat_b_count}"
        assert len(categories) >= 10, f"Expected at least 10 categories, found {len(categories)}"

        print(f"[OK] Total categories seeded: {len(categories)}")
        print("[PASSED] Database & Seeding Test Passed!\n")
    finally:
        db.close()

def test_phase1_mock_normalization():
    print("=" * 60)
    print("RUNNING TEST 2: Mock Data Loading & Normalization")
    print("=" * 60)

    for slug in ACTIVE_SLUGS:
        fetcher = ALL_FETCHERS[slug]
        raw_items = fetcher.load_mock_data()
        assert len(raw_items) > 0, f"Mock file for '{slug}' returned 0 items!"

        normalized = fetcher.normalize(raw_items)
        assert len(normalized) > 0, f"Normalization for '{slug}' produced 0 items!"

        sample = normalized[0]
        assert sample.external_id, f"Missing external_id in {slug}"
        assert sample.title, f"Missing title in {slug}"
        assert sample.url.startswith("http"), f"Invalid URL in {slug}: {sample.url}"

        print(f"[OK] {slug:16} | Raw items: {len(raw_items):2} | Normalized: {len(normalized):2} | Sample: '{sample.title[:45]}...'")

    print("[PASSED] Normalization Test Passed!\n")

def test_phase1_pipeline_execution_and_dedup():
    print("=" * 60)
    print("RUNNING TEST 3: Pipeline Execution, Deduplication & Logging")
    print("=" * 60)

    original_mock = settings.MOCK_FETCH_MODE
    original_live = list(settings.LIVE_SOURCES)
    settings.MOCK_FETCH_MODE = True
    settings.LIVE_SOURCES = []

    async def _run():
        db = SessionLocal()
        try:
            # Clear existing items and logs for clean test
            db.query(TrendingItem).delete()
            db.query(FetchLog).delete()
            db.commit()

            total_inserted_first_run = 0

            print("--- First Fetch Cycle (Cold Ingestion in Mock Mode) ---")
            for slug in ACTIVE_SLUGS:
                fetcher = ALL_FETCHERS[slug]
                res = await fetcher.execute(db, force_live=False)
                assert res.status in ["success", "fallback_mock"], f"Fetch failed for {slug}: {res.error_message}"
                assert res.items_new > 0, f"Expected new items for {slug}, got {res.items_new}"
                total_inserted_first_run += res.items_new
                print(f"  [OK] {slug:16} -> Fetched: {res.items_fetched:2}, New: {res.items_new:2}, Duration: {res.duration_ms:3}ms")

            total_in_db = db.query(TrendingItem).count()
            assert total_in_db == total_inserted_first_run, f"DB count mismatch: {total_in_db} vs {total_inserted_first_run}"
            print(f"[OK] Total items in DB after 1st cycle: {total_in_db}")

            print("\n--- Second Fetch Cycle (Deduplication Check) ---")
            total_new_second_run = 0
            for slug in ACTIVE_SLUGS:
                fetcher = ALL_FETCHERS[slug]
                res = await fetcher.execute(db, force_live=False)
                assert res.status in ["success", "fallback_mock"]
                assert res.items_new == 0, f"Expected 0 new items on 2nd cycle for {slug} (dedup), got {res.items_new}"
                total_new_second_run += res.items_new

            total_in_db_after = db.query(TrendingItem).count()
            assert total_in_db_after == total_in_db, f"Deduplication failed! Items grew from {total_in_db} to {total_in_db_after}"
            print(f"[OK] Deduplication verified: 0 duplicates created across all {len(ACTIVE_SLUGS)} sources.")

            # Check fetch_logs
            logs_count = db.query(FetchLog).count()
            assert logs_count == len(ACTIVE_SLUGS) * 2, f"Expected {len(ACTIVE_SLUGS)*2} log entries, found {logs_count}"
            print(f"[OK] Fetch logs recorded: {logs_count} entries.")

            print("[PASSED] Pipeline Execution & Deduplication Test Passed!\n")
        finally:
            db.close()

    try:
        asyncio.run(_run())
    finally:
        settings.MOCK_FETCH_MODE = original_mock
        settings.LIVE_SOURCES = original_live

def test_phase1_queries_and_filtering():
    print("=" * 60)
    print("RUNNING TEST 4: Category A/B Queries & Recency Filtering")
    print("=" * 60)

    db = SessionLocal()
    try:
        # 1. Category A vs B separation
        cat_a_items = db.query(TrendingItem).filter(TrendingItem.source_category == "A").all()
        cat_b_items = db.query(TrendingItem).filter(TrendingItem.source_category == "B").all()

        print(f"[OK] Category A (Direct Platform APIs) items in DB: {len(cat_a_items)}")
        print(f"[OK] Category B (Derived / Signals) items in DB:    {len(cat_b_items)}")

        assert len(cat_a_items) > 0, "No Category A items found in DB"
        assert len(cat_b_items) > 0, "No Category B items found in DB"

        # Verify Category B sources are only the 6 expected sources
        cat_b_slugs = {item.source.slug for item in cat_b_items}
        expected_cat_b = {"google_trends", "instagram_news", "facebook_news", "twitter_news", "reddit_news", "twitch_news"}
        assert cat_b_slugs == expected_cat_b, f"Unexpected Cat B sources: {cat_b_slugs}"
        print(f"[OK] Category B source provenance verified: {cat_b_slugs}")

        # 2. Recency query test (Past 24 hours vs Past 6 hours)
        now = datetime.utcnow()
        h24_items = db.query(TrendingItem).filter(TrendingItem.fetched_at >= now - timedelta(hours=24)).count()
        assert h24_items == len(cat_a_items) + len(cat_b_items), "24h filter did not return all freshly fetched items"
        print(f"[OK] Recency filter (24h) returned all {h24_items} active items.")

        print("[PASSED] Filtering & Querying Test Passed!\n")
    finally:
        db.close()

if __name__ == "__main__":
    test_phase1_database_and_seeding()
    test_phase1_mock_normalization()
    asyncio.run(test_phase1_pipeline_execution_and_dedup())
    test_phase1_queries_and_filtering()
    print("=" * 60)
    print("ALL PHASE 1 TESTS PASSED SUCCESSFULLY! (100% GREEN)")
    print("=" * 60)
