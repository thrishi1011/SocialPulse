import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings
from backend.database import SessionLocal, Base, engine
from backend.seed import init_db, seed_db
from backend.models import TrendingItem, Source, Category, FetchLog
from backend.main import app

def test_phase2_endpoints():
    print("=" * 70)
    print("PHASE 2 VERIFICATION SUITE — BACKEND API & PIPELINE")
    print("=" * 70)

    original_mock = settings.MOCK_FETCH_MODE
    original_live = list(settings.LIVE_SOURCES)
    original_ai_mock = settings.MOCK_AI_MODE
    settings.MOCK_FETCH_MODE = True
    settings.LIVE_SOURCES = []
    settings.MOCK_AI_MODE = True

    try:
        # 1. Initialize and prepare database
        init_db()
        db = SessionLocal()
        seed_db(db)
        db.close()

        client = TestClient(app)

        # Trigger cold start sweep via pipeline/run to ensure items are present and AI processed
        print("\n--- 0. Triggering Pipeline Run & AI Processing ---")
        resp = client.post("/api/v1/pipeline/run")
        assert resp.status_code == 200, f"Pipeline run failed: {resp.text}"
        print(f"[OK] Pipeline run response: {resp.json()['message']}")

        resp_ai = client.post("/api/v1/pipeline/process-ai?limit=100")
        assert resp_ai.status_code == 200
        print(f"[OK] AI processing: {resp_ai.json()['items_succeeded']} items summarized and categorized.")

        # 1. Health check
        print("\n--- 1. Testing GET /health ---")
        resp_health = client.get("/health")
        assert resp_health.status_code == 200
        health_json = resp_health.json()
        print(json.dumps(health_json, indent=2))
        assert health_json["status"] == "healthy"
        assert health_json["sources_enabled"] == 9

        # 2. Category A vs Category B separation test
        print("\n--- 2. Testing GET /api/v1/trends?source_category=A vs B ---")
        resp_a = client.get("/api/v1/trends?source_category=A&per_page=10")
        resp_b = client.get("/api/v1/trends?source_category=B&per_page=10")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

        data_a = resp_a.json()
        data_b = resp_b.json()

        print(f"[OK] Category A Items Count: {data_a['total']}")
        print(f"[OK] Category B Items Count: {data_b['total']}")

        # Verify all items in A have source_category == 'A'
        for it in data_a["items"]:
            assert it["source_category"] == "A"
            assert it["source"]["source_category"] == "A"

        # Verify all items in B have source_category == 'B'
        for it in data_b["items"]:
            assert it["source_category"] == "B"
            assert it["source"]["source_category"] == "B"

        # Print sample from Category A
        print("\n>>> Sample Category A Item (Direct Official API):")
        sample_a = data_a["items"][0]
        print(json.dumps({
            "id": sample_a["id"],
            "platform": sample_a["source"]["display_name"],
            "source_category": sample_a["source_category"],
            "source_type_label": sample_a["source"]["source_type_label"],
            "title": sample_a["title"],
            "url": sample_a["url"],
            "engagement": sample_a["engagement"],
            "ai_summary": sample_a["ai_summary"],
            "category": sample_a["category"]
        }, indent=2))

        # Print sample from Category B
        print("\n>>> Sample Category B Item (Derived Signal / News Coverage):")
        sample_b = data_b["items"][0]
        print(json.dumps({
            "id": sample_b["id"],
            "platform": sample_b["source"]["display_name"],
            "source_category": sample_b["source_category"],
            "source_type_label": sample_b["source"]["source_type_label"],
            "title": sample_b["title"],
            "url": sample_b["url"],
            "engagement": sample_b["engagement"],
            "ai_summary": sample_b["ai_summary"],
            "category": sample_b["category"]
        }, indent=2))

        # 3. Recency filtering test: 6h vs 24h vs all
        print("\n--- 3. Testing GET /api/v1/trends?recency=6h vs 24h ---")
        # For testing, let's insert one older item with published_at 18 hours ago
        db = SessionLocal()
        src_yt = db.query(Source).filter(Source.slug == "youtube").first()
        old_item = TrendingItem(
            source_id=src_yt.id,
            external_id="older_mock_test_vid",
            title="Retro 18-hour Old Trending Video",
            url="https://youtube.com/watch?v=older_mock",
            published_at=datetime.utcnow() - timedelta(hours=18),
            fetched_at=datetime.utcnow() - timedelta(hours=18),
            source_category="A",
            ai_processed=True
        )
        db.add(old_item)
        db.commit()
        db.close()

        resp_6h = client.get("/api/v1/trends?recency=6h")
        resp_24h = client.get("/api/v1/trends?recency=24h")

        assert resp_6h.status_code == 200
        assert resp_24h.status_code == 200

        data_6h = resp_6h.json()
        data_24h = resp_24h.json()

        print(f"[OK] Items in past 6h:  {data_6h['total']}")
        print(f"[OK] Items in past 24h: {data_24h['total']}")
        assert data_24h["total"] >= data_6h["total"]

        # 4. Source Status endpoint test (showing last_fetch details)
        print("\n--- 4. Testing GET /api/v1/sources/youtube/status ---")
        resp_status = client.get("/api/v1/sources/youtube/status")
        assert resp_status.status_code == 200
        status_json = resp_status.json()
        print(json.dumps(status_json, indent=2))
        assert status_json["slug"] == "youtube"
        assert status_json["last_fetch"] is not None
        assert status_json["last_fetch"]["status"] in ["success", "fallback_mock"]
        assert status_json["last_fetch"]["items_fetched"] > 0

        # 5. Single item detail by ID
        print(f"\n--- 5. Testing GET /api/v1/trends/{sample_a['id']} ---")
        resp_single = client.get(f"/api/v1/trends/{sample_a['id']}")
        assert resp_single.status_code == 200
        single_json = resp_single.json()
        assert single_json["id"] == sample_a["id"]
        print(f"[OK] Successfully fetched single item: '{single_json['title']}' from {single_json['source']['display_name']}")

        # 6. Categories list with counts
        print("\n--- 6. Testing GET /api/v1/categories ---")
        resp_cats = client.get("/api/v1/categories")
        assert resp_cats.status_code == 200
        cats_json = resp_cats.json()
        print(f"[OK] Total Categories: {cats_json['total_categories']}")
        for c in cats_json["categories"][:5]:
            print(f"  - {c['name']:16} (color: {c['color']}) -> {c['item_count']} active items")

        # 7. Pipeline status
        print("\n--- 7. Testing GET /api/v1/pipeline/status ---")
        resp_pipe = client.get("/api/v1/pipeline/status")
        assert resp_pipe.status_code == 200
        pipe_json = resp_pipe.json()
        print(json.dumps(pipe_json, indent=2))
        assert pipe_json["total_items_in_db"] > 0
        assert pipe_json["active_sources_count"] == 9

        print("\n" + "=" * 70)
        print("ALL PHASE 2 API & PIPELINE TESTS PASSED (100% GREEN)!")
        print("=" * 70)
    finally:
        settings.MOCK_FETCH_MODE = original_mock
        settings.LIVE_SOURCES = original_live
        settings.MOCK_AI_MODE = original_ai_mock

if __name__ == "__main__":
    test_phase2_endpoints()
