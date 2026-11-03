import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings
from backend.database import SessionLocal, Base, engine
from backend.seed import init_db, seed_db
from backend.models import TrendingItem, Source, Category
from backend.utils.rate_limiter import RateLimiter
from backend.services.ai_processor import analyze_trend_with_gemini, process_unprocessed_items

def test_rate_limiter_unit():
    print("=" * 80)
    print("TEST 1: Rate Limiter Unit Test (Sliding Window)")
    print("=" * 80)

    limiter = RateLimiter(max_requests=5, window_seconds=2.0)
    start_t = time.time()

    # 5 requests should pass instantly
    for i in range(5):
        limiter.acquire()
    elapsed_burst = time.time() - start_t
    print(f"[OK] Burst of 5 requests acquired in {elapsed_burst:.4f}s (< 0.1s expected)")
    assert elapsed_burst < 0.2

    # 6th request should throttle until 2s window passes
    limiter.acquire()
    elapsed_throttled = time.time() - start_t
    print(f"[OK] 6th request correctly throttled until window expired: {elapsed_throttled:.2f}s (>= 2.0s expected)")
    assert elapsed_throttled >= 1.9

    print("[PASSED] Rate Limiter sliding window test passed!\n")

def test_gemini_live_ai_call():
    print("=" * 80)
    print("TEST 2: Gemini 2.0 Flash Live AI Analysis")
    print("=" * 80)

    # Disable mock mode for testing Gemini directly
    original_mock = settings.MOCK_AI_MODE
    settings.MOCK_AI_MODE = False

    sample_items = [
        {
            "title": "ISRO launches navigation satellite successfully from Sriharikota",
            "description": "Indian Space Research Organisation launches next-generation navigation satellite with live mission coverage on YouTube.",
            "platform_name": "YouTube",
            "source_category": "A"
        },
        {
            "title": "Instagram's 'First Draft' feature aims to make editing Reels less tedious",
            "description": "TechCrunch reports that Meta is rolling out a new AI-powered editing tool on Instagram that stitches raw clips into a cohesive Reel draft automatically.",
            "platform_name": "News Coverage: Instagram",
            "source_category": "B"
        }
    ]

    for item in sample_items:
        print(f"\n[Sending to Gemini] '{item['title']}' ({item['platform_name']})...")
        t0 = time.time()
        res = analyze_trend_with_gemini(
            title=item["title"],
            description=item["description"],
            platform_name=item["platform_name"],
            source_category=item["source_category"]
        )
        duration = int((time.time() - t0) * 1000)

        print(f"  • Category Assigned: [{res['category']}]")
        print(f"  • Generated Summary: \"{res['summary']}\"")
        print(f"  • Latency:           {duration}ms")

        assert res["summary"], "Empty summary returned by Gemini"
        assert res["category"], "Empty category returned by Gemini"

    settings.MOCK_AI_MODE = original_mock
    print("\n[PASSED] Live Gemini API generation test passed!\n")

def test_batch_ai_processing():
    print("=" * 80)
    print("TEST 3: Batch Database AI Processing")
    print("=" * 80)

    async def _run():
        init_db()
        db = SessionLocal()
        seed_db(db)

        # Set some items as un-processed
        unprocessed_count = db.query(TrendingItem).filter(TrendingItem.ai_processed == False).count()
        print(f"[OK] Unprocessed items before sweep: {unprocessed_count}")

        if unprocessed_count == 0:
            # Reset 5 items for test
            items = db.query(TrendingItem).limit(5).all()
            for it in items:
                it.ai_processed = False
                it.ai_summary = None
            db.commit()
            unprocessed_count = 5

        total, succeeded, failed = await process_unprocessed_items(db, limit=10)
        print(f"[OK] Batch sweep completed -> Total: {total}, Succeeded: {succeeded}, Failed: {failed}")
        assert succeeded > 0
        assert failed == 0

        # Verify summaries were saved
        sample_processed = db.query(TrendingItem).filter(TrendingItem.ai_processed == True).order_by(TrendingItem.fetched_at.desc()).first()
        print(f"\n>>> Sample Database Item After AI Processing:")
        print(f"  • ID:          {sample_processed.id}")
        print(f"  • Title:       {sample_processed.title}")
        print(f"  • Platform:    {sample_processed.source.display_name}")
        print(f"  • Category:    {sample_processed.category.name if sample_processed.category else 'None'}")
        print(f"  • AI Summary:  \"{sample_processed.ai_summary}\"")

        db.close()
        print("\n[PASSED] Batch Database AI Processing test passed!")

    asyncio.run(_run())

if __name__ == "__main__":
    test_rate_limiter_unit()
    test_gemini_live_ai_call()
    test_batch_ai_processing()
    print("\n" + "=" * 80)
    print("ALL PHASE 7 GEMINI AI INTEGRATION TESTS PASSED (100% GREEN)!")
    print("=" * 80)
