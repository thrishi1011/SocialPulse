import json
import logging
from datetime import datetime
from typing import Any
import httpx

from backend.config import settings
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

logger = logging.getLogger("socialpulse.fetchers.youtube")

class YouTubeFetcher(AbstractFetcher):
    slug = "youtube"
    source_category = "A"

    async def fetch_raw(self) -> list[dict]:
        """Fetch most popular videos and trending news videos in India via YouTube Data API v3."""
        if not settings.YOUTUBE_API_KEY:
            logger.error("[youtube] Missing required configuration: YOUTUBE_API_KEY is not set or empty.")
            raise ValueError("YOUTUBE_API_KEY is not configured or is empty. Please set a valid YouTube Data API key in .env.")

        url = "https://www.googleapis.com/youtube/v3/videos"
        base_params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": "IN",
            "maxResults": 50,
            "key": settings.YOUTUBE_API_KEY
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Fetch general mostPopular list (a)
            resp_a = await client.get(url, params=base_params)
            resp_a.raise_for_status()
            items_a = resp_a.json().get("items", [])

            # 2. Fetch News & Politics list (b) (videoCategoryId=25) with nextPageToken paging
            items_b = []
            try:
                params_b = dict(base_params)
                params_b["videoCategoryId"] = "25"
                resp_b = await client.get(url, params=params_b)
                if resp_b.status_code == 200:
                    data_b = resp_b.json()
                    items_b = data_b.get("items", [])
                    # Page through category 25 with nextPageToken for richer political coverage
                    next_token = data_b.get("nextPageToken")
                    if next_token:
                        params_b_page2 = dict(params_b)
                        params_b_page2["pageToken"] = next_token
                        resp_b2 = await client.get(url, params=params_b_page2)
                        if resp_b2.status_code == 200:
                            items_b.extend(resp_b2.json().get("items", []))
                else:
                    logger.warning(f"[youtube] Category 25 fetch returned HTTP {resp_b.status_code}: {resp_b.text}. Continuing with list (a).")
            except Exception as e:
                logger.warning(f"[youtube] Error fetching News & Politics category 25: {e}. Continuing with list (a).")

            # Merge and deduplicate by video id
            merged: list[dict] = []
            seen_ids: dict[str, dict] = {}

            for item in items_a:
                vid_id = item.get("id")
                if vid_id:
                    seen_ids[vid_id] = item
                    merged.append(item)

            for item in items_b:
                vid_id = item.get("id")
                if not vid_id:
                    continue
                item["_is_news_category"] = True
                if vid_id in seen_ids:
                    seen_ids[vid_id]["_is_news_category"] = True
                else:
                    seen_ids[vid_id] = item
                    merged.append(item)

            return merged

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        for rank, raw in enumerate(raw_items, start=1):
            vid_id = raw.get("id") or str(raw.get("etag", ""))
            snippet = raw.get("snippet", {})
            stats = raw.get("statistics") or {}

            title = snippet.get("title", "").strip()
            if not title:
                continue

            desc = snippet.get("description", "")
            is_news = bool(raw.get("_is_news_category") or snippet.get("categoryId") == "25")
            if is_news:
                marker = "[Trending in News] "
                if desc:
                    desc = f"{marker}{desc}"
                else:
                    desc = marker.strip()

            channel = snippet.get("channelTitle", "Unknown Channel")
            thumb = (
                snippet.get("thumbnails", {}).get("high", {}).get("url")
                or snippet.get("thumbnails", {}).get("default", {}).get("url")
            )

            # Parse publication date
            pub_str = snippet.get("publishedAt")
            published_at = None
            if pub_str:
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            views = None
            if "viewCount" in stats:
                try:
                    views = int(stats["viewCount"])
                except (ValueError, TypeError):
                    pass

            comments = None
            if "commentCount" in stats:
                try:
                    comments = int(stats["commentCount"])
                except (ValueError, TypeError):
                    pass

            likes = None
            if "likeCount" in stats:
                try:
                    likes = int(stats["likeCount"])
                except (ValueError, TypeError):
                    pass

            # Primary engagement: views
            # Secondary engagement: comments if available, else likes
            secondary_val = comments if comments is not None else likes
            secondary_lbl = "comments" if comments is not None else ("likes" if likes is not None else None)

            raw_copy = dict(raw)
            import urllib.parse
            import re

            raw_url = raw.get("url")
            if raw_url and raw_url.startswith("http"):
                url = raw_url
            elif re.match(r"^[a-zA-Z0-9_-]{11}$", str(vid_id)):
                url = f"https://www.youtube.com/watch?v={vid_id}"
            else:
                encoded_title = urllib.parse.quote_plus(title)
                url = f"https://www.youtube.com/results?search_query={encoded_title}"

            item = TrendingItemCreate(
                external_id=str(vid_id),
                title=title,
                description=desc[:600] if desc else None,
                url=url,
                thumbnail_url=thumb,
                author=channel,
                engagement_value=views,
                engagement_label="views",
                secondary_value=secondary_val,
                secondary_label=secondary_lbl,
                rank=rank,
                region="IN",
                published_at=published_at,
                raw_json=json.dumps(raw_copy)
            )
            items.append(item)
        return items
