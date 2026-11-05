import asyncio
import json
import logging
from datetime import datetime
from typing import Any
import httpx
import feedparser

from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

logger = logging.getLogger("socialpulse.fetchers.google_trends")

class GoogleTrendsFetcher(AbstractFetcher):
    slug = "google_trends"
    source_category = "B"

    async def fetch_raw(self) -> list[dict]:
        """Fetch daily search trends from Google Trends live RSS feeds (IN and US for multi-region depth), optionally enriched with state-level regional interest."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        items = []
        seen_queries = set()

        async with httpx.AsyncClient(timeout=8.0) as client:
            for geo in ["IN", "US"]:
                try:
                    rss_url = f"https://trends.google.com/trending/rss?geo={geo}"
                    resp = await client.get(rss_url, headers=headers)
                    if resp.status_code == 200:
                        feed = feedparser.parse(resp.text)
                        for entry in feed.entries:
                            query = getattr(entry, "title", "").strip()
                            if not query or query.lower() in seen_queries:
                                continue
                            seen_queries.add(query.lower())
                            traffic = getattr(entry, "ht_approx_traffic", getattr(entry, "approx_traffic", "1K+"))
                            link = getattr(entry, "link", None) or f"https://trends.google.com/trends/explore?q={query.replace(' ', '%20')}"
                            items.append({
                                "query": query,
                                "formatted_traffic": traffic,
                                "url": link,
                                "snippet": getattr(entry, "summary", f"Search interest detected for '{query}'."),
                                "published": getattr(entry, "published", "")
                            })
                            if len(items) >= 25:
                                break
                except Exception as e:
                    logger.debug(f"Google Trends RSS fetch error for {geo}: {e}")
                if len(items) >= 25:
                    break

            # Translate any non-English trending queries to English Latin script
            non_eng_queries = [it["query"] for it in items if it.get("query")]
            if non_eng_queries:
                try:
                    from backend.utils.translator import translate_trends_to_english
                    translations = await translate_trends_to_english(non_eng_queries)
                    for it in items:
                        orig = it.get("query")
                        if orig and orig in translations:
                            it["original_query"] = orig
                            it["query"] = translations[orig]
                            if orig != translations[orig]:
                                it["snippet"] = f"Trending Google Search topic: {translations[orig]} (Original: {orig})."
                except Exception as e:
                    logger.warning(f"Error during Google Trends translation: {e}")

            # Optionally enrich top 3 trends with state-level data via pytrends in worker thread
            def _enrich_pytrends(subset):
                try:
                    from pytrends.request import TrendReq
                    pt = TrendReq(hl="en-US", tz=330, timeout=(3, 3))
                    for it in subset:
                        q = it.get("query")
                        if not q:
                            continue
                        try:
                            pt.build_payload([q], geo="IN")
                            df = pt.interest_by_region(resolution="REGION")
                            if not df.empty and q in df.columns:
                                pos_df = df[df[q] > 0].sort_values(by=q, ascending=False)
                                if not pos_df.empty:
                                    top_states = pos_df.head(3).index.tolist()
                                    if top_states:
                                        it["location_india"] = ", ".join(top_states)
                        except Exception:
                            break
                except Exception:
                    pass

            try:
                await asyncio.wait_for(asyncio.to_thread(_enrich_pytrends, items[:3]), timeout=4.0)
            except Exception:
                pass

            return items

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        for rank, raw in enumerate(raw_items, start=1):
            query = (raw.get("query") or raw.get("title", "")).strip()
            if not query:
                continue

            traffic_str = str(raw.get("formatted_traffic") or "High")
            url = raw.get("url") or f"https://trends.google.com/trends/explore?q={query.replace(' ', '%20')}"
            snippet = raw.get("snippet") or f"High search interest detected for '{query}' across Google Search."

            # Parse numeric approx traffic
            approx_val = raw.get("approx_traffic")
            if not approx_val and "+" in traffic_str:
                clean_t = traffic_str.replace("+", "").replace(",", "").replace("K", "000").replace("M", "000000")
                try:
                    approx_val = int(clean_t)
                except ValueError:
                    approx_val = None

            pub_date = None
            if "published" in raw and raw["published"]:
                try:
                    pub_date = datetime.fromisoformat(raw["published"].replace("Z", "+00:00"))
                except Exception:
                    pass

            item = TrendingItemCreate(
                external_id=f"gtrend_{query.lower().replace(' ', '_')}",
                title=query,
                description=f"Search Interest: {traffic_str}. {snippet}",
                url=url,
                thumbnail_url=None,
                author="Google Search Interest",
                engagement_value=approx_val,
                engagement_label="searches",
                secondary_value=None,
                secondary_label=None,
                rank=raw.get("rank") or rank,
                region="IN",
                location_india=raw.get("location_india"),
                published_at=pub_date,
                raw_json=json.dumps(raw)
            )
            items.append(item)
        return items
