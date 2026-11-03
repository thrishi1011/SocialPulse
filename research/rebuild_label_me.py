"""
research/rebuild_label_me.py

Rebuilds research/label_me.csv and research/label_me_meta.csv:
1. Picks 8 real videos from socialpulse.db:
   - 4 News & Politics videos (Category 25 / "[Trending in News]")
   - 2 Entertainment videos
   - 2 Other videos (Sports/Culture & Gaming)
   - 8 distinct channels
   - Heavy representation of Hindi, Tamil, Telugu, and Hinglish comments
2. Fetches 2 pages (up to 200 comments) per video with order=time (strictly tracking quota < 25 units).
3. Cleans whitespace, drops exact duplicates and strings < 2 chars; keeps emoji-only comments.
4. Samples 300 comments (~37-38 per video, strictly <= 60 per video).
5. Writes research/label_me.csv (id, video_title, text, label).
6. Writes research/label_me_meta.csv (id, video_id, category, script_type).
7. Prints distribution per video and per script type.
"""
import sys
import os
import pathlib
import time
import csv
import random
import unicodedata
import httpx
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv()
from backend.config import settings

QUOTA_UNITS_USED = 0

def track_quota(units: int = 1, desc: str = ""):
    global QUOTA_UNITS_USED
    QUOTA_UNITS_USED += units
    print(f"  [QUOTA] +{units} unit(s) ({desc}) | Total: {QUOTA_UNITS_USED} units")


def detect_script_type(text: str) -> str:
    """Classifies script as 'latin', 'non-latin', or 'mixed'."""
    has_latin = False
    has_non_latin = False
    for ch in text:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            if "LATIN" in name:
                has_latin = True
            else:
                has_non_latin = True
    if has_latin and has_non_latin:
        return "mixed"
    elif has_non_latin:
        return "non-latin"
    else:
        # Latin or emoji/punctuation/digit-only
        return "latin"


# 8 distinct real videos selected from socialpulse.db
SELECTED_VIDEOS = [
    {
        "external_id": "qWjfDow0xGQ",
        "title": "How Indian Media BRAINWASHES You! | Dhruv Rathee",
        "channel": "Dhruv Rathee",
        "category": "News & Politics",
        "expected_lang": "Hinglish / English / Hindi"
    },
    {
        "external_id": "d2tIByGSNIU",
        "title": "நள்ளிரவில் பேருந்துகளை நிறுத்தி போலீஸ் செய்த தரமான சம்பவம்! | Kumudam News",
        "channel": "Kumudam News 24x7",
        "category": "News & Politics",
        "expected_lang": "Tamil / Tanglish"
    },
    {
        "external_id": "Ml560VNB-Fc",
        "title": "పులివెందులలో జగన్ పర్యటనకు అనుమతి లేదు : Koya Praveen IPS | TV9",
        "channel": "TV9 Telugu Live",
        "category": "News & Politics",
        "expected_lang": "Telugu"
    },
    {
        "external_id": "RHYytLTeEAE",
        "title": "Rahul Warning : 'आपकी सबकी फाइल तैयार' राहुल के निशाने पर कौन ?",
        "channel": "Punya Prasun Bajpai",
        "category": "News & Politics",
        "expected_lang": "Hindi / Hinglish"
    },
    {
        "external_id": "nCa4BGy3MJ8",
        "title": "Eetha | Official Trailer | Shraddha Kapoor | Babil Khan | Laxman Utekar",
        "channel": "Maddock Films",
        "category": "Entertainment",
        "expected_lang": "Hindi / Hinglish"
    },
    {
        "external_id": "LM4ByXufv2w",
        "title": "Scene - Official Trailer | Suriya | Nazriya Nazim | Naslen | Jithu Madhavan",
        "channel": "Sony Music South",
        "category": "Entertainment",
        "expected_lang": "Malayalam / Tamil / English"
    },
    {
        "external_id": "-xJY_BDNyNA",
        "title": "#Video | पिया बिहरिया | Khesari Lal Yadav | Piya Bihariya | Bhojpuri Hit Song",
        "channel": "Mangalam Music",
        "category": "Others (Culture & Music)",
        "expected_lang": "Bhojpuri / Hindi"
    },
    {
        "external_id": "CoNyot0UsSY",
        "title": "DON'T ENTER THIS HAUNTED SUPERMARKET AT 3AM!",
        "channel": "Karry Kraft",
        "category": "Others (Gaming)",
        "expected_lang": "English / Hinglish"
    }
]


def fetch_video_comments(client: httpx.Client, api_key: str, video_meta: dict, pages: int = 2):
    """Fetch up to 2 pages (200 threads) for a video using order=time."""
    vid = video_meta["external_id"]
    title = video_meta["title"]
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    page_token = None
    fetched_comments = []

    for page_idx in range(1, pages + 1):
        params = {
            "part": "snippet",
            "videoId": vid,
            "order": "time",
            "maxResults": 100,
            "textFormat": "plainText",
            "key": api_key
        }
        if page_token:
            params["pageToken"] = page_token

        t0 = time.perf_counter()
        track_quota(1, f"commentThreads page={page_idx} vid={vid}")
        resp = client.get(url, params=params, timeout=20.0)
        dur_ms = (time.perf_counter() - t0) * 1000

        if resp.status_code != 200:
            print(f"    [WARN] Failed to fetch page {page_idx} for {vid} (status {resp.status_code}): {resp.text[:100]}")
            break

        data = resp.json()
        items = data.get("items", [])
        for it in items:
            snip = it.get("snippet", {})
            top_c = snip.get("topLevelComment", {}).get("snippet", {})
            c_id = it.get("id") or top_c.get("id")
            raw_text = top_c.get("textDisplay") or top_c.get("textOriginal") or ""
            
            # Normalize whitespace while preserving characters and emojis
            clean_text = " ".join(raw_text.split())

            # Rule 3: remove comments shorter than 2 characters; keep emoji-only comments
            if len(clean_text) >= 2:
                fetched_comments.append({
                    "id": c_id,
                    "video_id": vid,
                    "video_title": title,
                    "category": video_meta["category"],
                    "text": clean_text
                })

        print(f"    Page {page_idx}: {len(items)} threads returned ({dur_ms:.1f}ms) | Valid: {len(fetched_comments)}")
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return fetched_comments


def main():
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        print("[FATAL] YOUTUBE_API_KEY is missing.")
        sys.exit(1)

    print("======================================================================")
    print("REBUILDING DIVERSE COMMENT DATASET FOR NEWSPULSE")
    print(f"Target: 8 videos (4 News & Politics, 2 Entertainment, 2 Others)")
    print(f"Max quota budget: 25 units")
    print("======================================================================\n")

    per_video_pool = {}
    seen_texts_global = set()

    with httpx.Client() as client:
        for idx, v in enumerate(SELECTED_VIDEOS, 1):
            print(f"[{idx}/8] Fetching comments for: {v['title'][:60]}")
            print(f"      Channel: {v['channel']} | Category: {v['category']} | Lang: {v['expected_lang']}")
            comments = fetch_video_comments(client, api_key, v, pages=2)
            
            # Remove exact duplicates across pool
            unique_for_vid = []
            for c in comments:
                if c["text"] not in seen_texts_global:
                    seen_texts_global.add(c["text"])
                    unique_for_vid.append(c)
            
            print(f"      --> Deduplicated valid pool: {len(unique_for_vid)} comments\n")
            per_video_pool[v["external_id"]] = unique_for_vid

    print(f"Total YouTube Quota Units Used: {QUOTA_UNITS_USED} units (Limit <= 25 units)")
    assert QUOTA_UNITS_USED <= 25, f"Quota limit exceeded! {QUOTA_UNITS_USED} > 25"

    # ----------------------------------------------------------------------
    # SAMPLING: 300 comments total (~37-38 per video, strictly <= 60 per video)
    # ----------------------------------------------------------------------
    rng = random.Random(42)
    # Target distribution across 8 videos to sum to exactly 300
    # 4 videos get 38, 4 videos get 37 -> 4*38 + 4*37 = 152 + 148 = 300
    target_counts = [38, 38, 38, 38, 37, 37, 37, 37]

    sampled_comments = []
    video_sample_counts = {}

    for idx, v in enumerate(SELECTED_VIDEOS):
        vid = v["external_id"]
        pool = per_video_pool.get(vid, [])
        rng.shuffle(pool)
        n_to_take = target_counts[idx]
        taken = pool[:n_to_take]
        sampled_comments.extend(taken)
        video_sample_counts[v["title"]] = len(taken)

    # Final shuffle of all 300 sampled comments
    rng.shuffle(sampled_comments)
    assert len(sampled_comments) == 300, f"Expected 300 comments, got {len(sampled_comments)}"

    # ----------------------------------------------------------------------
    # WRITE research/label_me.csv
    # Columns: id, video_title, text, label (empty)
    # ----------------------------------------------------------------------
    label_me_path = BASE_DIR / "research" / "label_me.csv"
    with open(label_me_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "video_title", "text", "label"], quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for c in sampled_comments:
            writer.writerow({
                "id": c["id"],
                "video_title": c["video_title"],
                "text": c["text"],
                "label": ""  # Strictly empty
            })

    # ----------------------------------------------------------------------
    # WRITE research/label_me_meta.csv
    # Columns: id, video_id, category, script_type
    # ----------------------------------------------------------------------
    script_type_counts = {"latin": 0, "non-latin": 0, "mixed": 0}
    meta_path = BASE_DIR / "research" / "label_me_meta.csv"
    with open(meta_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "video_id", "category", "script_type"], quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for c in sampled_comments:
            st = detect_script_type(c["text"])
            script_type_counts[st] += 1
            writer.writerow({
                "id": c["id"],
                "video_id": c["video_id"],
                "category": c["category"],
                "script_type": st
            })

    # ----------------------------------------------------------------------
    # PRINT RESULTS BREAKDOWN
    # ----------------------------------------------------------------------
    print("\n======================================================================")
    print("DATASET GENERATION REPORT")
    print("======================================================================")
    print(f"Output 1: {label_me_path} (300 rows, empty 'label')")
    print(f"Output 2: {meta_path} (300 rows metadata)")
    print(f"Total Quota Units Used: {QUOTA_UNITS_USED} units (Quota budget: < 25 units)")

    print("\n--- Comments per Video ---")
    for title, cnt in video_sample_counts.items():
        print(f"  {cnt:2d} comments | {title[:65]}")

    print("\n--- Comments per Script Type ---")
    for st, cnt in script_type_counts.items():
        pct = (cnt / len(sampled_comments)) * 100
        print(f"  {st:10s}: {cnt:3d} ({pct:.1f}%)")

    print("======================================================================")


if __name__ == "__main__":
    main()
