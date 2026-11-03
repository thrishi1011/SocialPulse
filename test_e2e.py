import asyncio
import os
import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings
from backend.database import SessionLocal, Base, engine
from backend.models import TrendingItem, Source, Category, FetchLog
from backend.seed import init_db, seed_db
from backend.services.orchestrator import run_pipeline
from backend.services.ai_processor import process_unprocessed_items
from backend.main import app

def test_e2e_verification():
    print("=" * 80)
    print("SOCIALPULSE COMPLETE E2E COLD-START PIPELINE TEST")
    print("=" * 80)

    original_mock = settings.MOCK_FETCH_MODE
    original_live = list(settings.LIVE_SOURCES)
    original_ai_mock = settings.MOCK_AI_MODE
    settings.MOCK_FETCH_MODE = True
    settings.LIVE_SOURCES = []
    settings.MOCK_AI_MODE = True

    db = SessionLocal()
    try:
        # 1. Cold Start: Reset Database
        print("\n--- 1. Cold Start: Initializing Fresh Database ---")
        init_db()
        db.query(TrendingItem).delete()
        db.query(FetchLog).delete()
        db.query(Source).delete()
        db.query(Category).delete()
        db.commit()

        # 2. Seed Database
        print("--- 2. Seeding 9 Sources and 12 Categories ---")
        seed_db(db)

        sources = db.query(Source).all()
        categories = db.query(Category).all()
        print(f"[OK] Seeded {len(sources)} sources and {len(categories)} taxonomy categories.")
        assert len(sources) == 9, f"Expected 9 sources, got {len(sources)}"
        assert len(categories) >= 10, f"Expected at least 10 categories, got {len(categories)}"

        # 3. Pipeline Fetching Across All Sources
        print("\n--- 3. Executing Full Ingestion Pipeline across All 9 Sources ---")
        results = asyncio.run(run_pipeline(db))
        total_fetched = sum(r.items_fetched for r in results)
        print(f"[OK] Ingestion finished -> {total_fetched} total items fetched across {len(results)} sources.")
        assert total_fetched > 0, "Zero items fetched during pipeline execution!"

        for r in results:
            status_tag = "[OK]" if r.status in ["success", "fallback_mock"] else "[WARN]"
            print(f"  {status_tag:6} {r.source_slug:16} | Status: {r.status:7} | Items: {r.items_fetched:2} | Latency: {r.duration_ms:4}ms")

        # 4. Batch AI Processing
        print("\n--- 4. Executing Batch AI Summarization ---")
        attempted, succeeded, failed = asyncio.run(process_unprocessed_items(db, limit=10))
        print(f"[OK] AI processing completed -> Processed {succeeded}/{attempted} items (Failures: {failed}).")
        assert succeeded > 0, "No items were successfully processed with AI!"

        # 5. REST API Integration Verification via TestClient
        print("\n--- 5. Verifying REST API Endpoints via TestClient ---")
        client = TestClient(app)

        # 5.1 Health Check
        res_health = client.get("/health")
        assert res_health.status_code == 200, f"Health check failed: {res_health.status_code}"
        print(f"  [OK] GET /health -> {res_health.json()}")

        # 5.2 Sources Endpoint
        res_sources = client.get("/api/v1/sources")
        assert res_sources.status_code == 200
        sources_data = res_sources.json()
        assert sources_data["total_sources"] == 9
        assert len(sources_data["sources"]) == 9
        print(f"  [OK] GET /api/v1/sources -> 9 sources returned.")

        # 5.3 Categories Endpoint
        res_cats = client.get("/api/v1/categories")
        assert res_cats.status_code == 200
        cats_data = res_cats.json()
        assert cats_data["total_categories"] >= 10
        assert len(cats_data["categories"]) >= 10
        print(f"  [OK] GET /api/v1/categories -> {cats_data['total_categories']} categories returned.")

        # 5.4 Trends Filter: Category A (Official APIs)
        res_cat_a = client.get("/api/v1/trends?source_category=A&page=1&per_page=10")
        assert res_cat_a.status_code == 200
        data_a = res_cat_a.json()
        assert all(item["source_category"] == "A" for item in data_a["items"])
        print(f"  [OK] GET /api/v1/trends?source_category=A -> {len(data_a['items'])} items returned (Total: {data_a['total']}).")

        # 5.5 Trends Filter: Category B (Derived Signals)
        res_cat_b = client.get("/api/v1/trends?source_category=B&page=1&per_page=10")
        assert res_cat_b.status_code == 200
        data_b = res_cat_b.json()
        assert all(item["source_category"] == "B" for item in data_b["items"])
        print(f"  [OK] GET /api/v1/trends?source_category=B -> {len(data_b['items'])} items returned (Total: {data_b['total']}).")

        # 5.6 Recency Filter
        res_recency = client.get("/api/v1/trends?recency=24h&page=1&per_page=5")
        assert res_recency.status_code == 200
        print(f"  [OK] GET /api/v1/trends?recency=24h -> 200 OK.")

        # 5.7 Category Filter Test Across Multiple Categories
        for cat_name in ["Technology", "Culture", "Entertainment", "Politics", "Gaming", "Sports", "Business"]:
            res_cat = client.get(f"/api/v1/trends?category={cat_name}&recency=all")
            assert res_cat.status_code == 200
            count = res_cat.json()["total"]
            print(f"  [OK] GET /api/v1/trends?category={cat_name} -> {count} items.")

        # 5.8 Trend Detail & Audit Trail
        sample_item_id = data_a["items"][0]["id"]
        res_detail = client.get(f"/api/v1/trends/{sample_item_id}")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["id"] == sample_item_id
        assert "raw_json" in detail_data
        print(f"  [OK] GET /api/v1/trends/{sample_item_id} -> Title: '{detail_data['title'][:40]}...' (raw_json length: {len(detail_data.get('raw_json') or '')} chars)")

        # 5.9 Pipeline Single Source Trigger
        res_pipe = client.post("/api/v1/pipeline/run/youtube")
        assert res_pipe.status_code == 200
        print(f"  [OK] POST /api/v1/pipeline/run/youtube -> {res_pipe.json()['message']}")

        # 6. Checkpoint Verification
        print("\n" + "=" * 80)
        print("ALL E2E PIPELINE & API TESTS PASSED WITH 100% INTEGRITY!")
        print("=" * 80)
    finally:
        settings.MOCK_FETCH_MODE = original_mock
        settings.LIVE_SOURCES = original_live
        settings.MOCK_AI_MODE = original_ai_mock
        db.close()

if __name__ == "__main__":
    test_e2e_verification()
