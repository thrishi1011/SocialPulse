import json
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

class PinterestFetcher(AbstractFetcher):
    slug = "pinterest"
    source_category = "A"

    async def fetch_raw(self) -> list[dict]:
        """Pinterest official API does not provide a public global trending endpoint."""
        return []

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        return []
