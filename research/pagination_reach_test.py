"""
research/pagination_reach_test.py

Phase 2: Pagination Reach Test & Comment Sampling
- Measures pagination reach with order=time on two real YouTube videos:
  Video 1: High-volume video (s4458uJDx_o, ~12,305 reported comments)
  Video 2: Medium-volume video (3,000–8,000 reported comments)
- Strict quota tracking (< 150 units).
- Evaluates:
  1. Pages fetched
  2. Threads returned
  3. Whether nextPageToken stopped early vs reached end of available threads
  4. Ratio of threads to statistics.commentCount
- Generates research/label_me.csv with 300 randomly sampled comments for user labeling.
"""
import sys
import os
import pathlib
import time
import json
import csv
import random
from datetime import datetime
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings

TOTAL_QUOTA_UNITS = 0

def track_quota(units: int = 1, operation: str = ""):
    global TOTAL_QUOTA_UNITS
    TOTAL_QUOTA_UNITS += units
    print(f"  [QUOTA] +{units} unit(s) ({operation}) | Total: {TOTAL_QUOTA_UNITS} units")


def get_video_stats(client: httpx.Client, api_key: str, video_id: str) -> dict:
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "id": video_id,
        "key": api_key
    }
    track_quota(1, f"videos.list id={video_id}")
    resp = client.get(url, params=params, timeout=15.0)
    if resp.status_code != 200:
        raise RuntimeError(f"videos.list failed ({resp.status_code}): {resp.text}")
    items = resp.json().get("items", [])
    if not items:
        raise RuntimeError(f"Video {video_id} not found.")
    return items[0]


def find_medium_volume_video(client: httpx.Client, api_key: str) -> dict:
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": "IN",
        "maxResults": 50,
        "key": api_key
    }
    track_quota(1, "videos.list popular IN (search 3k-8k)")
    resp = client.get(url, params=params, timeout=15.0)
    if resp.status_code != 200:
        raise RuntimeError(f"popular videos.list failed ({resp.status_code}): {resp.text}")
    
    candidates = []
    for it in resp.json().get("items", []):
        cc = int(it.get("statistics", {}).get("commentCount", 0))
        if 2500 <= cc <= 8500:
            candidates.append((cc, it))
    
    if candidates:
        # Pick candidate closest to 4,500
        candidates.sort(key=lambda x: abs(x[0] - 4500))
        return candidates[0][1]
    
    # Fallback search if chart didn't have one
    print("  Popular chart had no 3k-8k candidate, querying search...")
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "snippet",
        "q": "trailer 2026 hindi",
        "type": "video",
        "maxResults": 10,
        "key": api_key
    }
    track_quota(100, "search.list fallback")
    s_resp = client.get(search_url, params=search_params, timeout=15.0)
    video_ids = [item["id"]["videoId"] for item in s_resp.json().get("items", [])]
    
    v_resp = client.get(url, params={"part": "snippet,statistics", "id": ",".join(video_ids), "key": api_key})
    track_quota(1, "videos.list by ids")
    for it in v_resp.json().get("items", []):
        cc = int(it.get("statistics", {}).get("commentCount", 0))
        if 2000 <= cc <= 10000:
            return it
    
    return v_resp.json().get("items", [])[0]


def paginate_comments(client: httpx.Client, api_key: str, video_id: str, max_pages: int = 70):
    """
    Paginates commentThreads with order=time until nextPageToken is None or max_pages reached.
    """
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    page_token = None
    pages_fetched = 0
    all_threads = []
    total_replies_signaled = 0
    stopped_by_token_end = False

    while pages_fetched < max_pages:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "order": "time",
            "maxResults": 100,
            "textFormat": "plainText",
            "key": api_key
        }
        if page_token:
            params["pageToken"] = page_token

        t0 = time.perf_counter()
        track_quota(1, f"commentThreads page={pages_fetched+1} vid={video_id}")
        resp = client.get(url, params=params, timeout=20.0)
        dur_ms = (time.perf_counter() - t0) * 1000

        if resp.status_code == 403:
            err = resp.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
            print(f"  [403 ERROR] {err}: {resp.text[:120]}")
            break
        elif resp.status_code != 200:
            print(f"  [ERROR] Status {resp.status_code}: {resp.text[:120]}")
            break

        data = resp.json()
        items = data.get("items", [])
        pages_fetched += 1

        for it in items:
            snip = it.get("snippet", {})
            top_comment = snip.get("topLevelComment", {}).get("snippet", {})
            c_id = it.get("id") or top_comment.get("id")
            c_text = top_comment.get("textDisplay") or top_comment.get("textOriginal") or ""
            author = top_comment.get("authorDisplayName", "Anonymous")
            likes = top_comment.get("likeCount", 0)
            published = top_comment.get("publishedAt", "")
            rep_count = snip.get("totalReplyCount", 0)
            total_replies_signaled += rep_count

            all_threads.append({
                "id": c_id,
                "text": c_text,
                "author": author,
                "like_count": likes,
                "published_at": published,
                "reply_count": rep_count
            })

        print(f"    Page {pages_fetched:2d}: {len(items):3d} threads (latency: {dur_ms:.1f}ms) | Accumulated: {len(all_threads)}")

        next_token = data.get("nextPageToken")
        if not next_token:
            stopped_by_token_end = True
            print("    --> Reached end of pagination: nextPageToken is None/empty.")
            break
        page_token = next_token

    return {
        "pages_fetched": pages_fetched,
        "threads_retrieved": len(all_threads),
        "total_replies_signaled": total_replies_signaled,
        "stopped_by_token_end": stopped_by_token_end,
        "threads": all_threads
    }


def main():
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        print("[FATAL] YOUTUBE_API_KEY is not configured in .env or settings.")
        sys.exit(1)

    print("======================================================================")
    print("PHASE 2: PAGINATION REACH & COMMENT SAMPLING TEST")
    print("======================================================================")

    all_sampled_comments = []

    with httpx.Client() as client:
        # ------------------------------------------------------------------
        # TEST 1: High Volume Video (s4458uJDx_o, reported ~12,305 comments)
        # ------------------------------------------------------------------
        vid1_id = "s4458uJDx_o"
        print(f"\n--- Testing Video 1 (High Volume: {vid1_id}) ---")
        v1_meta = get_video_stats(client, api_key, vid1_id)
        v1_title = v1_meta.get("snippet", {}).get("title", "")
        v1_reported_cc = int(v1_meta.get("statistics", {}).get("commentCount", 0))
        print(f"Title: {v1_title}")
        print(f"Reported commentCount: {v1_reported_cc}")

        # Budget max 65 pages for Video 1
        res1 = paginate_comments(client, api_key, vid1_id, max_pages=65)
        res1["video_id"] = vid1_id
        res1["title"] = v1_title
        res1["reported_comment_count"] = v1_reported_cc
        res1["thread_coverage_ratio"] = res1["threads_retrieved"] / v1_reported_cc if v1_reported_cc > 0 else 0
        res1["combined_coverage_ratio"] = (res1["threads_retrieved"] + res1["total_replies_signaled"]) / v1_reported_cc if v1_reported_cc > 0 else 0

        all_sampled_comments.extend(res1["threads"])

        # ------------------------------------------------------------------
        # TEST 2: Medium Volume Video (3,000 - 8,000 comments)
        # ------------------------------------------------------------------
        print(f"\n--- Selecting Video 2 (Medium Volume: 3,000–8,000 comments) ---")
        v2_meta = find_medium_volume_video(client, api_key)
        vid2_id = v2_meta["id"]
        v2_title = v2_meta.get("snippet", {}).get("title", "")
        v2_reported_cc = int(v2_meta.get("statistics", {}).get("commentCount", 0))
        print(f"Selected Video 2: {vid2_id}")
        print(f"Title: {v2_title}")
        print(f"Reported commentCount: {v2_reported_cc}")

        # Budget remaining pages (up to 55 pages or until nextPageToken ends)
        max_v2_pages = min(55, 140 - TOTAL_QUOTA_UNITS)
        print(f"Paginating Video 2 with max {max_v2_pages} pages...")
        res2 = paginate_comments(client, api_key, vid2_id, max_pages=max_v2_pages)
        res2["video_id"] = vid2_id
        res2["title"] = v2_title
        res2["reported_comment_count"] = v2_reported_cc
        res2["thread_coverage_ratio"] = res2["threads_retrieved"] / v2_reported_cc if v2_reported_cc > 0 else 0
        res2["combined_coverage_ratio"] = (res2["threads_retrieved"] + res2["total_replies_signaled"]) / v2_reported_cc if v2_reported_cc > 0 else 0

        all_sampled_comments.extend(res2["threads"])

    # ----------------------------------------------------------------------
    # RESULTS REPORTING
    # ----------------------------------------------------------------------
    print("\n======================================================================")
    print("PAGINATION REACH TEST RESULTS SUMMARY")
    print("======================================================================")
    print(f"Total Quota Units Spent in this test: {TOTAL_QUOTA_UNITS} units (limit <= 150)")
    
    for idx, r in enumerate([res1, res2], 1):
        print(f"\nVideo {idx}: {r['title']} ({r['video_id']})")
        print(f"  Reported commentCount      : {r['reported_comment_count']}")
        print(f"  Pages Fetched              : {r['pages_fetched']}")
        print(f"  Top-level Threads Returned : {r['threads_retrieved']}")
        print(f"  Replies Signaled           : {r['total_replies_signaled']}")
        print(f"  Combined (Threads+Replies) : {r['threads_retrieved'] + r['total_replies_signaled']}")
        print(f"  Stopped By Token End       : {r['stopped_by_token_end']}")
        print(f"  Thread Coverage Ratio      : {r['thread_coverage_ratio']*100:.2f}%")
        print(f"  Combined Coverage Ratio    : {r['combined_coverage_ratio']*100:.2f}%")

    # Save detailed telemetry to research/reach_test_results.json
    results_payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_quota_units_used": TOTAL_QUOTA_UNITS,
        "video_1": {k: v for k, v in res1.items() if k != "threads"},
        "video_2": {k: v for k, v in res2.items() if k != "threads"},
    }
    with open(BASE_DIR / "research" / "reach_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)

    # ----------------------------------------------------------------------
    # CREATE research/label_me.csv (300 randomly sampled real comments)
    # ----------------------------------------------------------------------
    print("\n----------------------------------------------------------------------")
    print(f"Generating research/label_me.csv from pool of {len(all_sampled_comments)} real comments...")
    
    # Filter comments to avoid empty texts or pure symbols
    valid_comments = []
    seen_texts = set()
    for c in all_sampled_comments:
        raw_text = (c.get("text") or "").strip()
        # Clean newlines and excessive whitespace for clean CSV row structure
        clean_text = " ".join(raw_text.split())
        if len(clean_text) >= 10 and clean_text not in seen_texts:
            seen_texts.add(clean_text)
            valid_comments.append({
                "id": c["id"],
                "text": clean_text,
                "label": ""  # Strictly empty label for user annotation
            })

    print(f"Valid distinct comments pool: {len(valid_comments)}")
    # Reproducible random sample of 300
    rng = random.Random(42)
    sample_300 = rng.sample(valid_comments, min(300, len(valid_comments)))

    csv_path = BASE_DIR / "research" / "label_me.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["id", "text", "label"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in sample_300:
            writer.writerow(row)

    print(f"Successfully wrote {len(sample_300)} comments to {csv_path}")
    print("CSV columns: ['id', 'text', 'label'] where label is empty.")
    print("======================================================================")


if __name__ == "__main__":
    main()
