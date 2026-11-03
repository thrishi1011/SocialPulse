import json
from datetime import datetime
from typing import Any
import httpx

from backend.config import settings
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

class TwitchFetcher(AbstractFetcher):
    slug = "twitch"
    source_category = "A"

    async def _get_app_access_token(self, client: httpx.AsyncClient) -> str:
        """Obtain OAuth2 Client Credentials access token from Twitch."""
        token_url = "https://id.twitch.tv/oauth2/token"
        data = {
            "client_id": settings.TWITCH_CLIENT_ID,
            "client_secret": settings.TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        return resp.json()["access_token"]

    async def fetch_raw(self) -> list[dict]:
        """Fetch top games and categories from Twitch Helix API."""
        if not settings.TWITCH_CLIENT_ID or not settings.TWITCH_CLIENT_SECRET:
            raise ValueError("Twitch credentials (TWITCH_CLIENT_ID/SECRET) not configured.")

        async with httpx.AsyncClient(timeout=10.0) as client:
            token = await self._get_app_access_token(client)
            headers = {
                "Client-Id": settings.TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {token}"
            }
            # Top games
            games_url = "https://api.twitch.tv/helix/games/top?first=30"
            resp = await client.get(games_url, headers=headers)
            resp.raise_for_status()
            games_data = resp.json().get("data", [])
            return games_data

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        for rank, raw in enumerate(raw_items, start=1):
            game_id = str(raw.get("id", "")).strip()
            name = raw.get("name", "").strip()
            if not name:
                continue

            box_art = raw.get("box_art_url", "")
            if box_art and "{width}" in box_art:
                box_art = box_art.replace("{width}", "400").replace("{height}", "533")

            viewers = raw.get("viewers")
            channels = raw.get("channels")
            clean_name = name.lower().replace(" ", "-").replace(":", "")
            url = raw.get("url") or f"https://www.twitch.tv/directory/category/{clean_name}"

            desc = f"Top trending category on Twitch: {name}."
            if viewers:
                desc += f" Currently streaming to {viewers:,} concurrent viewers."

            item = TrendingItemCreate(
                external_id=f"twitch_game_{game_id or clean_name}",
                title=name,
                description=desc,
                url=url,
                thumbnail_url=box_art if (box_art and box_art.startswith("http")) else None,
                author="Twitch Live",
                engagement_value=int(viewers) if viewers is not None else None,
                engagement_label="concurrent viewers",
                secondary_value=int(channels) if channels is not None else None,
                secondary_label="channels live",
                rank=raw.get("rank") or rank,
                region="global",
                published_at=None,
                raw_json=json.dumps(raw)
            )
            items.append(item)
        return items
