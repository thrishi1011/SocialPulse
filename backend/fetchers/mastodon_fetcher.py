import json
import logging
import re
from datetime import datetime
from typing import Any
import httpx
from bs4 import BeautifulSoup

from backend.config import settings
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

logger = logging.getLogger("socialpulse.fetchers.mastodon")

class MastodonFetcher(AbstractFetcher):
    slug = "mastodon"
    source_category = "A"

    async def fetch_raw(self) -> list[dict]:
        """
        Fetch trending news links, hashtags, and statuses from Mastodon API.
        Uses MASTODON_API_KEY when configured.
        """
        base_url = settings.MASTODON_BASE_URL or "https://mastodon.social"
        headers = {"User-Agent": "SocialPulse/1.0 (trending intelligence)"}
        if settings.MASTODON_API_KEY:
            headers["Authorization"] = f"Bearer {settings.MASTODON_API_KEY}"

        merged: list[dict] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Fetch trending news links (curated news stories shared across Mastodon)
            try:
                resp_links = await client.get(f"{base_url}/api/v1/trends/links", params={"limit": 20}, headers=headers)
                if resp_links.status_code == 200:
                    links_data = resp_links.json()
                    for item in links_data:
                        item["_kind"] = "link"
                        merged.append(item)
                else:
                    logger.warning(f"[mastodon] links endpoint returned status {resp_links.status_code}")
            except Exception as e:
                logger.warning(f"[mastodon] Failed to fetch trending links: {e}")

            # 2. Fetch trending tags
            try:
                resp_tags = await client.get(f"{base_url}/api/v1/trends/tags", params={"limit": 20}, headers=headers)
                if resp_tags.status_code == 200:
                    tags_data = resp_tags.json()
                    for item in tags_data:
                        item["_kind"] = "tag"
                        merged.append(item)
                else:
                    logger.warning(f"[mastodon] tags endpoint returned status {resp_tags.status_code}")
            except Exception as e:
                logger.warning(f"[mastodon] Failed to fetch trending tags: {e}")

            # 3. Fetch trending statuses (viral federated posts)
            try:
                resp_statuses = await client.get(f"{base_url}/api/v1/trends/statuses", params={"limit": 20}, headers=headers)
                if resp_statuses.status_code == 200:
                    statuses_data = resp_statuses.json()
                    for item in statuses_data:
                        item["_kind"] = "status"
                        merged.append(item)
            except Exception as e:
                logger.warning(f"[mastodon] Failed to fetch trending statuses: {e}")

        # If live fetch returned nothing, raise so base fetcher triggers fallback
        if not merged:
            raise RuntimeError("Mastodon API returned no items across links, tags, and statuses.")

        return merged

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        seen_urls = set()

        for rank, raw in enumerate(raw_items, start=1):
            kind = raw.get("_kind")

            # --- CASE 1: Trending News Links ---
            if kind == "link" or ("url" in raw and "title" in raw and "name" not in raw and "content" not in raw):
                url = raw.get("url", "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = raw.get("title", "").strip()
                if not title:
                    continue

                provider = raw.get("provider_name") or raw.get("author_name") or "Mastodon Network"
                description = raw.get("description") or f"Trending news article shared on Mastodon via {provider}."
                image = raw.get("image") or None

                history = raw.get("history", [])
                total_uses = 0
                total_accounts = 0
                if history and isinstance(history, list):
                    try:
                        total_uses = int(history[0].get("uses", 0))
                        total_accounts = int(history[0].get("accounts", 0))
                    except (ValueError, TypeError):
                        pass

                item = TrendingItemCreate(
                    external_id=f"mastodon_link_{abs(hash(url))}",
                    title=title,
                    description=description,
                    url=url,
                    thumbnail_url=image,
                    author=provider,
                    engagement_value=total_uses if total_uses > 0 else (total_accounts if total_accounts > 0 else None),
                    engagement_label="shares today",
                    secondary_value=total_accounts if total_accounts > 0 else None,
                    secondary_label="accounts",
                    rank=rank,
                    region="global",
                    published_at=datetime.utcnow(),
                    raw_json=json.dumps(raw)
                )
                items.append(item)

            # --- CASE 2: Trending Hashtags ---
            elif kind == "tag" or ("name" in raw and "history" in raw):
                tag_name = raw.get("name", "").strip()
                if not tag_name:
                    continue

                tag_url = raw.get("url") or f"https://mastodon.social/tags/{tag_name}"
                if tag_url in seen_urls:
                    continue
                seen_urls.add(tag_url)

                history = raw.get("history", [])
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

            # --- CASE 3: Trending Statuses (Posts) ---
            elif kind == "status" or "content" in raw:
                status_id = raw.get("id")
                status_url = raw.get("url") or (f"https://mastodon.social/@unknown/{status_id}" if status_id else None)
                if not status_url or status_url in seen_urls:
                    continue
                seen_urls.add(status_url)

                # Clean HTML body
                content_html = raw.get("content", "")
                soup = BeautifulSoup(content_html, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                if not text:
                    continue

                # Title is first sentence or up to 100 chars
                first_sentence = re.split(r"[.!?\n]", text)[0].strip()
                title = first_sentence if 10 <= len(first_sentence) <= 120 else text[:100].strip() + "..."

                account = raw.get("account", {})
                author = account.get("display_name") or account.get("username") or "Mastodon User"

                media = raw.get("media_attachments", [])
                thumb = media[0].get("preview_url") if media and isinstance(media, list) else None

                reblogs = int(raw.get("reblogs_count", 0))
                favs = int(raw.get("favourites_count", 0))
                replies = int(raw.get("replies_count", 0))
                engagement = reblogs + favs

                pub_dt = None
                created_str = raw.get("created_at")
                if created_str:
                    try:
                        pub_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                item = TrendingItemCreate(
                    external_id=f"mastodon_status_{status_id}",
                    title=title,
                    description=text,
                    url=status_url,
                    thumbnail_url=thumb,
                    author=author,
                    engagement_value=engagement if engagement > 0 else None,
                    engagement_label="engagements",
                    secondary_value=replies if replies > 0 else None,
                    secondary_label="replies",
                    rank=rank,
                    region="global",
                    published_at=pub_dt or datetime.utcnow(),
                    raw_json=json.dumps(raw)
                )
                items.append(item)

        return items
