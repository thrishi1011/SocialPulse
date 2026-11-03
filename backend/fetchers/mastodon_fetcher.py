import json
from datetime import datetime
from typing import Any
import httpx

from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

class MastodonFetcher(AbstractFetcher):
    slug = "mastodon"
    source_category = "A"

    async def fetch_raw(self) -> list[dict]:
        """Fetch trending tags from mastodon.social public API."""
        url = "https://mastodon.social/api/v1/trends/tags"
        params = {"limit": 20}
        headers = {"User-Agent": "SocialPulse/1.0 (trending intelligence)"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        for rank, raw in enumerate(raw_items, start=1):
            tag_name = raw.get("name", "").strip()
            if not tag_name:
                continue

            tag_url = raw.get("url") or f"https://mastodon.social/tags/{tag_name}"
            history = raw.get("history", [])

            # Compute recent usage volume
            total_uses = 0
            total_accounts = 0
            if history and isinstance(history, list):
                try:
                    total_uses = int(history[0].get("uses", 0))
                    total_accounts = int(history[0].get("accounts", 0))
                except (ValueError, TypeError):
                    pass

            desc = raw.get("description") or f"Trending hashtag #{tag_name} on Mastodon with {total_uses} recent posts across {total_accounts} federated accounts."

            item = TrendingItemCreate(
                external_id=f"tag_{tag_name.lower()}",
                title=f"#{tag_name}",
                description=desc,
                url=tag_url,
                thumbnail_url=None,
                author="mastodon.social",
                engagement_value=total_uses if total_uses > 0 else None,
                engagement_label="posts today",
                secondary_value=total_accounts if total_accounts > 0 else None,
                secondary_label="accounts",
                rank=rank,
                region="global",
                published_at=None,
                raw_json=json.dumps(raw)
            )
            items.append(item)
        return items
