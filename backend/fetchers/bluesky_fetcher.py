import json
from datetime import datetime
from typing import Any
import httpx

from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

class BlueskyFetcher(AbstractFetcher):
    slug = "bluesky"
    source_category = "A"

    async def fetch_raw(self) -> list[dict]:
        """Fetch trending topics from Bluesky public AppView (no auth required)."""
        url = "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"
        headers = {"User-Agent": "SocialPulse/1.0 (trending intelligence)"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("topics", [])

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        for rank, raw in enumerate(raw_items, start=1):
            topic = raw.get("topic") or raw.get("displayName") or ""
            topic = topic.strip()
            if not topic:
                continue

            display_name = raw.get("displayName", topic)
            description = raw.get("description") or f"Trending conversation topic on Bluesky: {display_name}"
            link = raw.get("link") or f"https://bsky.app/search?q={topic.replace(' ', '%20')}"
            if link.startswith("/"):
                link = f"https://bsky.app{link}"
            elif not link.startswith("http"):
                link = f"https://bsky.app/{link.lstrip('/')}"
            count = raw.get("count")

            item = TrendingItemCreate(
                external_id=f"bsky_{topic.lower().replace(' ', '_')}",
                title=display_name,
                description=description,
                url=link,
                thumbnail_url=None,
                author="Bluesky Network",
                engagement_value=int(count) if count is not None else None,
                engagement_label="posts",
                secondary_value=None,
                secondary_label=None,
                rank=rank,
                region="global",
                published_at=None,
                raw_json=json.dumps(raw)
            )
            items.append(item)
        return items
