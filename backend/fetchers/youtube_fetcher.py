import json
import logging
from datetime import datetime
from typing import Any

from backend.config import settings
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

logger = logging.getLogger("socialpulse.fetchers.youtube")

class YouTubeFetcher(AbstractFetcher):
    slug = "youtube"
    source_category = "A"

    def _fetch_youtube_sync(self) -> list[dict]:
        """Fetch multi-page popular and news videos synchronously in worker thread using urllib (fast and immune to Windows IPv6 DNS hang)."""
        import urllib.request
        import urllib.parse

        base_url = "https://www.googleapis.com/youtube/v3/videos"
        base_params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": "IN",
            "maxResults": "50",
            "key": settings.YOUTUBE_API_KEY
        }

        def _get_json(params: dict) -> dict:
            query = urllib.parse.urlencode(params)
            req = urllib.request.Request(f"{base_url}?{query}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

        # 1. Fetch general mostPopular list (Page 1 and Page 2 -> up to 100 items)
        d_a = _get_json(base_params)
        items_a = list(d_a.get("items", []))
        token_a = d_a.get("nextPageToken")
        if token_a:
            try:
                p_a2 = dict(base_params, pageToken=token_a)
                d_a2 = _get_json(p_a2)
                items_a.extend(d_a2.get("items", []))
            except Exception as e:
                logger.warning(f"[youtube] General page 2 fetch notice: {e}")

        # 2. Fetch News and Politics list (videoCategoryId=25, Page 1 and Page 2 -> up to 100 items)
        items_b = []
        try:
            params_b = dict(base_params, videoCategoryId="25")
            d_b = _get_json(params_b)
            items_b = list(d_b.get("items", []))
            token_b = d_b.get("nextPageToken")
            if token_b:
                try:
                    p_b2 = dict(params_b, pageToken=token_b)
                    d_b2 = _get_json(p_b2)
                    items_b.extend(d_b2.get("items", []))
                except Exception as e:
                    logger.warning(f"[youtube] News page 2 fetch notice: {e}")
        except Exception as e:
            logger.warning(f"[youtube] Error fetching News and Politics category 25: {e}.")

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

    async def fetch_raw(self) -> list[dict]:
        """Fetch most popular videos and trending news videos in India via YouTube Data API v3 (multi-page)."""
        if not settings.YOUTUBE_API_KEY:
            logger.error("[youtube] Missing required configuration: YOUTUBE_API_KEY is not set or empty.")
            raise ValueError("YOUTUBE_API_KEY is not configured or is empty. Please set a valid YouTube Data API key in .env.")

        import asyncio
        return await asyncio.to_thread(self._fetch_youtube_sync)

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
