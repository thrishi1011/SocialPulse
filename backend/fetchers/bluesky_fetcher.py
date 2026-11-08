import json
import logging
import re
from datetime import datetime
from typing import Any
import httpx

from backend.config import settings
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

logger = logging.getLogger("socialpulse.fetchers.bluesky")

class BlueskyFetcher(AbstractFetcher):
    slug = "bluesky"
    source_category = "A"

    async def _authenticate(self, client: httpx.AsyncClient) -> str | None:
        """Authenticate with Bluesky AT Protocol XRPC session if credentials configured."""
        if not settings.BLUESKY_API_KEY or not settings.BLUESKY_IDENTIFIER:
            return None

        try:
            auth_resp = await client.post(
                "https://bsky.social/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": settings.BLUESKY_IDENTIFIER,
                    "password": settings.BLUESKY_API_KEY
                },
                timeout=8.0
            )
            if auth_resp.status_code == 200:
                return auth_resp.json().get("accessJwt")
            else:
                logger.warning(f"[bluesky] Authentication returned status {auth_resp.status_code}: {auth_resp.text[:100]}")
        except Exception as e:
            logger.warning(f"[bluesky] Authentication error: {e}")
        return None

    async def fetch_raw(self) -> list[dict]:
        """
        Fetch trending topics and top trending news posts from Bluesky.
        Uses authenticated session when BLUESY_API / BLUESKY_API_KEY is configured.
        """
        headers = {"User-Agent": "SocialPulse/1.0 (trending intelligence)"}
        combined: list[dict] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            jwt = await self._authenticate(client)
            if jwt:
                headers["Authorization"] = f"Bearer {jwt}"

            # 1. Fetch trending topics from AppView
            try:
                url_trends = "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"
                resp_trends = await client.get(url_trends, headers=headers)
                if resp_trends.status_code == 200:
                    for t in resp_trends.json().get("topics", []):
                        t["_kind"] = "topic"
                        combined.append(t)
            except Exception as e:
                logger.warning(f"[bluesky] Failed to fetch trending topics: {e}")

            # 2. Fetch top trending news posts
            try:
                base_search = "https://bsky.social" if jwt else "https://public.api.bsky.app"
                url_news = f"{base_search}/xrpc/app.bsky.feed.searchPosts"
                resp_news = await client.get(url_news, params={"q": "news", "sort": "top", "limit": 25}, headers=headers)
                if resp_news.status_code == 200:
                    for p in resp_news.json().get("posts", []):
                        p["_kind"] = "post"
                        combined.append(p)
            except Exception as e:
                logger.warning(f"[bluesky] Failed to fetch news posts: {e}")

        # Supplement with fallback mock data if few items fetched
        if len(combined) < 25:
            mock_topics = self.load_mock_data()
            seen_topics = {
                (t.get("topic") or t.get("displayName") or "").strip().lower()
                for t in combined if t.get("_kind") == "topic"
            }
            for m in mock_topics:
                t_name = (m.get("topic") or m.get("displayName") or "").strip().lower()
                if t_name and t_name not in seen_topics:
                    m["_kind"] = "topic"
                    combined.append(m)
                    seen_topics.add(t_name)
                    if len(combined) >= 25:
                        break

        return combined

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        seen_ids = set()

        for rank, raw in enumerate(raw_items, start=1):
            kind = raw.get("_kind")

            # --- CASE 1: Bluesky News / Discussion Posts ---
            if kind == "post" or "record" in raw:
                record = raw.get("record", {})
                text = (record.get("text") or "").strip()
                if not text:
                    continue

                uri = raw.get("uri", "")
                rkey = uri.split("/")[-1] if "/" in uri else ""
                author_info = raw.get("author", {})
                handle = author_info.get("handle") or "bsky.app"
                author_name = author_info.get("displayName") or handle

                ext_id = f"bsky_post_{rkey or raw.get('cid') or abs(hash(text))}"
                if ext_id in seen_ids:
                    continue
                seen_ids.add(ext_id)

                # Generate clean headline
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                first_line = lines[0] if lines else text
                sentences = re.split(r"[.!?]\s+", first_line)
                headline = sentences[0].strip() if sentences else first_line
                if len(headline) < 15:
                    headline = text[:100].strip()
                if len(headline) > 130:
                    headline = headline[:127] + "..."

                post_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else f"https://bsky.app/search?q={headline[:40]}"

                likes = int(raw.get("likeCount", 0))
                reposts = int(raw.get("repostCount", 0))
                replies = int(raw.get("replyCount", 0))
                engagement = likes + reposts

                pub_dt = None
                created_at_str = record.get("createdAt")
                if created_at_str:
                    try:
                        pub_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                # Check if post has embedded image
                thumb = None
                embed = raw.get("embed", {})
                if embed:
                    images = embed.get("images", [])
                    if images and isinstance(images, list):
                        thumb = images[0].get("thumb") or images[0].get("fullsize")

                item = TrendingItemCreate(
                    external_id=ext_id,
                    title=headline,
                    description=text,
                    url=post_url,
                    thumbnail_url=thumb,
                    author=f"{author_name} (@{handle})",
                    engagement_value=engagement if engagement > 0 else (likes if likes > 0 else None),
                    engagement_label="engagements",
                    secondary_value=replies if replies > 0 else None,
                    secondary_label="replies",
                    rank=rank,
                    region="global",
                    published_at=pub_dt or datetime.utcnow(),
                    raw_json=json.dumps(raw)
                )
                items.append(item)

            # --- CASE 2: Bluesky Trending Topics ---
            else:
                topic = raw.get("topic") or raw.get("displayName") or ""
                topic = topic.strip()
                if not topic:
                    continue

                ext_id = f"bsky_{topic.lower().replace(' ', '_')}"
                if ext_id in seen_ids:
                    continue
                seen_ids.add(ext_id)

                display_name = raw.get("displayName", topic)
                description = raw.get("description") or f"Trending conversation topic on Bluesky: {display_name}"
                link = raw.get("link") or f"https://bsky.app/search?q={topic.replace(' ', '%20')}"
                if link.startswith("/"):
                    link = f"https://bsky.app{link}"
                elif not link.startswith("http"):
                    link = f"https://bsky.app/{link.lstrip('/')}"
                count = raw.get("count")

                item = TrendingItemCreate(
                    external_id=ext_id,
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
