"""
research/measure_youtube_api.py

Experimental measurement script for YouTube Data API v3:
- Strictly tracks and prints YouTube quota units used (limit < 300).
- Selects 3 real Indian YouTube videos with different comment volumes (Low, Medium, High).
- Paginates commentThreads.list, measuring latency, returned count, replies, and mismatches.
- Saves ~250 real comments to research/raw_comments_sample.json for sentiment benchmarking.
"""
import sys
import pathlib
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import time
import json
import httpx
from datetime import datetime
from backend.config import settings

QUOTA_UNITS_USED = 0

def track_quota(units: int = 1, operation: str = ""):
    global QUOTA_UNITS_USED
    QUOTA_UNITS_USED += units
    print(f"  [QUOTA] +{units} unit(s) ({operation}) | Total used so far: {QUOTA_UNITS_USED}")

def get_popular_indian_videos(api_key: str):
    """Fetch recent popular videos in IN to pick 3 with different comment volumes."""
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": "IN",
        "maxResults": 25,
        "key": api_key
    }
    track_quota(1, "videos.list (popular IN)")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"videos.list failed ({resp.status_code}): {resp.text}")
        return resp.json().get("items", [])

def fetch_comment_threads(api_key: str, video_id: str, max_pages: int = 5, order: str = "relevance"):
    """
    Fetch comment threads for a video, recording per-page timing,
    counts, replies, and next page token behaviour.
    """
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    page_token = None
    pages_data = []
    all_comments = []
    page_num = 0

    with httpx.Client(timeout=15.0) as client:
        while True:
            page_num += 1
            if page_num > max_pages:
                break

            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 100,
                "order": order,
                "key": api_key
            }
            if page_token:
                params["pageToken"] = page_token

            t0 = time.perf_counter()
            track_quota(1, f"commentThreads.list (page {page_num} for {video_id})")
            resp = client.get(url, params=params)
            latency_ms = (time.perf_counter() - t0) * 1000

            if resp.status_code != 200:
                print(f"    [ERROR] Page {page_num} failed with status {resp.status_code}: {resp.text}")
                pages_data.append({
                    "page": page_num,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "items_count": 0,
                    "error": resp.text
                })
                break

            data = resp.json()
            items = data.get("items", [])
            page_token = data.get("nextPageToken")

            total_reply_count_on_page = sum(it.get("snippet", {}).get("totalReplyCount", 0) for it in items)

            pages_data.append({
                "page": page_num,
                "status_code": 200,
                "latency_ms": round(latency_ms, 2),
                "items_count": len(items),
                "total_reply_count": total_reply_count_on_page,
                "has_next_page_token": bool(page_token)
            })

            for it in items:
                top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                all_comments.append({
                    "video_id": video_id,
                    "comment_id": it.get("id"),
                    "author": top.get("authorDisplayName", "Unknown"),
                    "text": top.get("textOriginal") or top.get("textDisplay", ""),
                    "likeCount": top.get("likeCount", 0),
                    "totalReplyCount": it.get("snippet", {}).get("totalReplyCount", 0),
                    "publishedAt": top.get("publishedAt")
                })

            if not page_token:
                print(f"    [END] Reached last page at page {page_num} (nextPageToken absent)")
                break

    return pages_data, all_comments

def run_measurements():
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        print("[ERROR] YOUTUBE_API_KEY is not configured in settings!")
        return

    print("=====================================================================")
    print("YOUTUBE DATA API V3 MEASUREMENT HARNESS")
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    print("=====================================================================")

    # 1. Fetch candidate videos
    items = get_popular_indian_videos(api_key)
    print(f"Fetched {len(items)} popular videos from IN region.")

    # Filter videos with commentCount
    valid_videos = []
    for it in items:
        stats = it.get("statistics", {})
        cc = int(stats.get("commentCount", 0)) if stats.get("commentCount") else 0
        snippet = it.get("snippet", {})
        valid_videos.append({
            "id": it["id"],
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "commentCount": cc
        })

    valid_videos.sort(key=lambda x: x["commentCount"])

    # Categorize into Low (<500), Medium (1000 - 5000), High (>10000)
    low_candidates = [v for v in valid_videos if 30 <= v["commentCount"] <= 600]
    med_candidates = [v for v in valid_videos if 1000 <= v["commentCount"] <= 8000]
    high_candidates = [v for v in valid_videos if v["commentCount"] > 10000]

    # Select 1 from each
    low_video = low_candidates[0] if low_candidates else valid_videos[0]
    med_video = med_candidates[0] if med_candidates else valid_videos[len(valid_videos)//2]
    high_video = high_candidates[0] if high_candidates else valid_videos[-1]

    selected_videos = [
        {"tier": "Low Volume", "video": low_video, "max_pages": 6},
        {"tier": "Medium Volume", "video": med_video, "max_pages": 4},
        {"tier": "High Volume", "video": high_video, "max_pages": 4},
    ]

    results = []
    collected_sample_comments = []

    for sel in selected_videos:
        v = sel["video"]
        tier = sel["tier"]
        max_pages = sel["max_pages"]
        safe_title = v['title'][:45].encode('ascii', 'replace').decode('ascii')
        print(f"\n--- Testing {tier}: '{safe_title}...' (ID: {v['id']}) ---")
        print(f"  Reported statistics.commentCount: {v['commentCount']}")

        # Test with order=relevance
        pages_data, comments = fetch_comment_threads(api_key, v["id"], max_pages=max_pages, order="relevance")
        total_retrieved = len(comments)
        total_replies_signaled = sum(p["total_reply_count"] for p in pages_data)
        avg_latency = sum(p["latency_ms"] for p in pages_data) / len(pages_data) if pages_data else 0

        print(f"  Pages Fetched: {len(pages_data)} | Top-Level Threads: {total_retrieved}")
        print(f"  Sum of TotalReplyCount on threads: {total_replies_signaled}")
        print(f"  Average API Latency per page: {avg_latency:.1f} ms")

        # Test 1 page of order=time to compare
        print("  Testing 1 page with order='time' for freshness comparison...")
        time_pages, time_comments = fetch_comment_threads(api_key, v["id"], max_pages=1, order="time")

        results.append({
            "tier": tier,
            "video_id": v["id"],
            "title": v["title"],
            "channel": v["channel"],
            "reported_comment_count": v["commentCount"],
            "pages_fetched": len(pages_data),
            "top_level_threads_retrieved": total_retrieved,
            "replies_signaled": total_replies_signaled,
            "combined_coverage": total_retrieved + total_replies_signaled,
            "coverage_mismatch": v["commentCount"] - (total_retrieved + total_replies_signaled),
            "avg_latency_ms": round(avg_latency, 2),
            "pages_detail": pages_data,
            "order_time_first_comment_age": time_comments[0]["publishedAt"] if time_comments else None,
            "order_relevance_first_comment_age": comments[0]["publishedAt"] if comments else None
        })

        collected_sample_comments.extend(comments[:80])

    print("\n" + "=" * 80)
    print("EXPERIMENT SUMMARY & QUOTA ACCOUNTING")
    print("=" * 80)
    print(f"TOTAL YOUTUBE QUOTA UNITS USED IN THIS RUN: {QUOTA_UNITS_USED} units (Limit is 300)")
    assert QUOTA_UNITS_USED < 300, f"Exceeded 300 quota units! Used {QUOTA_UNITS_USED}"

    # Save measurement results
    out_dir = pathlib.Path("research")
    (out_dir / "api_measurement_results.json").write_text(json.dumps({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_quota_units_used": QUOTA_UNITS_USED,
        "results": results
    }, indent=2), encoding="utf-8")

    # Save raw comments sample (at least 200 comments for sentiment labelling)
    (out_dir / "raw_comments_sample.json").write_text(json.dumps(collected_sample_comments, indent=2), encoding="utf-8")
    print(f"Saved {len(collected_sample_comments)} raw comments to research/raw_comments_sample.json")
    print(f"Saved measurement metrics to research/api_measurement_results.json")

if __name__ == "__main__":
    run_measurements()
