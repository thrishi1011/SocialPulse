import json
from datetime import datetime
from typing import Any

from backend.fetchers.base import AbstractFetcher, TrendingItemCreate
from backend.services.news_coverage import fetch_news_for_platform, generate_news_article_id
from backend.services.mock_ai import detect_indian_location_heuristic

class FacebookNewsFetcher(AbstractFetcher):
    slug = "facebook_news"
    source_category = "B"

    QUERIES = [
        '"trending on Facebook"',
        '"viral Facebook post"',
        '"Facebook trending topic"',
        '"Facebook groups viral"'
    ]

    async def fetch_raw(self) -> list[dict]:
        """Fetch journalistic news coverage regarding Facebook trends."""
        return await fetch_news_for_platform("Facebook", self.QUERIES)

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        for rank, raw in enumerate(raw_items, start=1):
            title = raw.get("title", "").strip()
            url = raw.get("url", "").strip()
            if not title or not url:
                continue

            outlet_name = raw.get("source", {}).get("name") if isinstance(raw.get("source"), dict) else "News Outlet"
            author = raw.get("author") or outlet_name
            desc = raw.get("description") or f"News report from {outlet_name} covering trending content on Facebook."
            image = raw.get("urlToImage") or raw.get("image")

            pub_str = raw.get("publishedAt")
            published_at = None
            if pub_str:
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            loc_india = detect_indian_location_heuristic(f"{title} {desc}")
            item = TrendingItemCreate(
                external_id=generate_news_article_id(url),
                title=title,
                description=desc,
                url=url,
                thumbnail_url=image if (image and image.startswith("http")) else None,
                author=f"via {outlet_name}",
                engagement_value=None,
                engagement_label=None,
                secondary_value=None,
                secondary_label=None,
                rank=rank,
                region="global",
                location_india=loc_india,
                published_at=published_at,
                raw_json=json.dumps(raw)
            )
            items.append(item)
        return items
