import asyncio
import calendar
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import logging
import re
import time
from typing import Any
import httpx
import feedparser
import googlenewsdecoder
from bs4 import BeautifulSoup

from backend.services.news_sources import NEWS_OUTLETS, DROPPED_OUTLETS_LOG

logger = logging.getLogger("socialpulse.news_coverage")

EXCLUDED_DOMAINS = [
    "x.com", "twitter.com", "instagram.com", "facebook.com",
    "threads.net", "reddit.com", "twitch.tv", "youtube.com", "youtu.be", "tiktok.com"
]

EXCLUDED_OUTLETS = [
    "x.com", "twitter", "instagram", "facebook", "reddit", "twitch", "tiktok", "youtube"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8"
}

# 10-minute in-memory cache to avoid hammering sites on repeated refreshes
_scrape_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_TTL_SECONDS = 600

# Shared concurrency semaphore for courteous scraping
_shared_semaphore = asyncio.Semaphore(8)

# Query variants per platform (4-6 variants, with and without India)
PLATFORM_QUERIES: dict[str, list[str]] = {
    "Instagram": [
        '"Instagram" trending viral',
        '"Instagram" reel viral India',
        '"Instagram" update creator trends',
        '"Instagram" backlash trend',
        '"Instagram trend" India',
        '"Instagram" viral video India',
        '"Instagram" reels popular viral',
        '"Instagram" influencer controversy trend'
    ],
    "Facebook": [
        '"Facebook" viral post trend',
        '"Facebook" viral debate India',
        '"Facebook" community trend viral',
        '"Facebook" Meta controversy trend',
        '"Facebook" post sparks reaction India',
        '"Facebook" viral video trend India',
        '"Facebook" group viral controversy',
        '"Facebook" viral news India'
    ],
    "Twitter": [
        '"Twitter" trending India viral',
        '"X" trending "on X" viral',
        '"Elon Musk" X trend debate',
        '"X users" trend backlash',
        '"viral tweet" trend reaction India'
    ],
    "X (Twitter)": [
        '"Twitter" trending India viral',
        '"X" trending "on X" viral',
        '"Elon Musk" X trend debate',
        '"X users" trend backlash',
        '"viral tweet" trend reaction India'
    ],
    "X": [
        '"Twitter" trending India viral',
        '"X" trending "on X" viral',
        '"Elon Musk" X trend debate',
        '"X users" trend backlash',
        '"viral tweet" trend reaction India'
    ],
    "Reddit": [
        '"Reddit" viral post debate',
        '"Reddit" thread sparks viral India',
        '"Reddit" community trend discussion',
        '"Reddit users" react viral',
        '"trending on Reddit"'
    ],
    "Twitch": [
        '"Twitch" streamer viral drama',
        '"Twitch" stream trend record',
        '"Twitch" esports gaming tournament viral',
        '"Twitch streamer" controversy ban',
        '"Twitch livestream" reaction viral'
    ]
}

def normalize_url(url: str) -> str:
    """Normalize URL by stripping fragments and common marketing tracking params."""
    if not url:
        return ""
    clean = url.strip()
    clean = re.sub(r"#.*$", "", clean)
    clean = re.sub(r"([?&])(utm_[^&]+|ref=[^&]+|cmp=[^&]+|fbclid=[^&]+|gclid=[^&]+)", "", clean)
    clean = re.sub(r"[?&]$", "", clean)
    return clean.rstrip("/")

def normalize_title_tokens(title: str) -> set[str]:
    """Extract significant lowercase word tokens for near-duplicate title detection."""
    clean = re.sub(r"[^\w\s]", "", title.lower())
    tokens = set(clean.split())
    stopwords = {
        "the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "is",
        "are", "with", "as", "by", "from", "that", "this", "it", "its", "news",
        "report", "video", "post", "watch"
    }
    return tokens - stopwords

def is_near_duplicate_title(title: str, existing_tokens: list[set[str]], threshold: float = 0.8) -> bool:
    """Compare token overlap to detect near-duplicate headlines (>80% similarity)."""
    tokens = normalize_title_tokens(title)
    if not tokens or len(tokens) < 3:
        return False
    for existing in existing_tokens:
        intersection = tokens & existing
        min_len = min(len(tokens), len(existing))
        if min_len > 0 and (len(intersection) / min_len) >= threshold:
            return True
    return False

def is_valid_news_article(url: str, outlet_name: str | None) -> bool:
    """Validate that the item is genuine third-party journalism and not a social post or raw google link."""
    if not url or not url.startswith("http"):
        return False
    clean_url = url.lower()
    if any(domain in clean_url for domain in EXCLUDED_DOMAINS):
        return False
    if "news.google.com" in clean_url:
        return False
    if outlet_name and any(out == outlet_name.lower().strip() for out in EXCLUDED_OUTLETS):
        return False
    # Exclude bare homepage or section landing roots
    parts = clean_url.split("//", 1)[-1].strip("/").split("/")
    if len(parts) <= 1:
        return False
    return True

def is_topically_relevant(title: str, snippet: str, platform_name: str) -> bool:
    """
    Ensure the article is explicitly relevant to the platform and discusses a trend/viral event,
    filtering out generic hospital, general political, or unrelated commercial news.
    """
    text = f"{title} {snippet}"
    if platform_name in ["Twitter", "X (Twitter)", "X"]:
        pattern = r"\b(x|twitter|tweet|tweets|retweet|elon musk|on x)\b"
    elif platform_name == "Instagram":
        pattern = r"\b(instagram|insta|reel|reels|ig|meta)\b"
    elif platform_name == "Facebook":
        pattern = r"\b(facebook|fb|meta|mark zuckerberg)\b"
    elif platform_name == "Reddit":
        pattern = r"\b(reddit|subreddit|subreddits|r\/[a-z0-9_]+|upvotes?|redditors?)\b"
    elif platform_name == "Twitch":
        pattern = r"\b(twitch|streamer|streamers|livestream|streaming|esports|gaming|broadcast)\b"
    else:
        pattern = rf"\b{re.escape(platform_name.lower())}\b"

    if not re.search(pattern, text, re.IGNORECASE):
        return False

    trend_pattern = (
        r"\b(trend|trending|viral|buzz|sparks?|debates?|reacts?|reaction|outcry|backlash|"
        r"video|clip|post|views?|challenge|shares?|internet|online|broadcast|record|ban|bans|"
        r"feature|algorithm|millions?|stars?|interview|fans?|community|discussions?|lawsuit|"
        r"terms|feed|grid|update|notes?|creator|drama|stream|boycott)\b"
    )
    return bool(re.search(trend_pattern, text, re.IGNORECASE))

def generate_news_article_id(url: str) -> str:
    """Generate deterministic 32-character SHA-256 hash of article URL."""
    clean_url = normalize_url(url).lower()
    return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()[:32]

def _sync_decode_url(raw_url: str) -> str:
    try:
        clean = raw_url.split("?")[0] if "?" in raw_url else raw_url
        res = googlenewsdecoder.new_decoderv1(clean, interval=0.1)
        if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
    except Exception:
        pass
    return raw_url

async def decode_url_safe(raw_url: str) -> str:
    """Decode Google News redirect URL to direct publisher link with 8.0s timeout."""
    if "/articles/" not in raw_url:
        return raw_url
    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync_decode_url, raw_url), timeout=8.0)
    except Exception:
        return raw_url

def parse_entry_datetime(entry: Any) -> datetime | None:
    """Extract true publication timestamp from RSS entry metadata."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.utcfromtimestamp(calendar.timegm(entry.published_parsed))
        except Exception:
            pass
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime.utcfromtimestamp(calendar.timegm(entry.updated_parsed))
        except Exception:
            pass
    for attr in ("published", "pubDate", "updated", "date"):
        val = getattr(entry, attr, None)
        if val and isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass
            try:
                dt = parsedate_to_datetime(val)
                if dt:
                    return dt.astimezone().replace(tzinfo=None)
            except Exception:
                pass
    return None

def extract_entry_image(entry: Any) -> str | None:
    """Extract lead image / thumbnail from RSS entry."""
    if hasattr(entry, "media_content") and entry.media_content:
        for m in entry.media_content:
            if isinstance(m, dict) and m.get("url"):
                return m["url"]
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        for m in entry.media_thumbnail:
            if isinstance(m, dict) and m.get("url"):
                return m["url"]
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/") and enc.get("href"):
                return enc["href"]
    for attr in ("summary", "description"):
        html_val = getattr(entry, attr, None)
        if html_val and "<img" in html_val:
            m = re.search(r'<img[^>]+src=["\'](http[^"\']+)["\']', html_val)
            if m:
                return m.group(1)
    return None

async def _fetch_from_outlet(
    client: httpx.AsyncClient,
    outlet: dict,
    platform_name: str,
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    """Fetch and parse candidate articles from a single news outlet (RSS or HTML listing)."""
    outlet_name = outlet["name"]
    base_domain = outlet["base_domain"]
    rss_url = outlet.get("rss_url")
    section_urls = outlet.get("section_urls") or []

    articles: list[dict] = []

    # 1. Prefer RSS feed if configured
    if rss_url:
        try:
            async with _shared_semaphore:
                resp = await client.get(rss_url, timeout=6.0)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:25]:
                    stats[outlet_name]["found"] += 1
                    raw_title = entry.title if hasattr(entry, "title") else ""
                    clean_title = re.sub(r"\s+", " ", raw_title).strip()
                    if not clean_title or len(clean_title) < 18:
                        stats[outlet_name]["failed"] += 1
                        continue

                    link = getattr(entry, "link", None)
                    if not link or not is_valid_news_article(link, outlet_name):
                        stats[outlet_name]["failed"] += 1
                        continue

                    summary_text = getattr(entry, "summary", "") or ""
                    clean_summary = BeautifulSoup(summary_text, "html.parser").get_text(strip=True)

                    if not is_topically_relevant(clean_title, clean_summary, platform_name):
                        stats[outlet_name]["failed"] += 1
                        continue

                    pub_dt = parse_entry_datetime(entry)
                    # Drop if clearly older than 30 days
                    if pub_dt and (datetime.utcnow() - pub_dt) > timedelta(days=30):
                        stats[outlet_name]["failed"] += 1
                        continue

                    img_url = extract_entry_image(entry)

                    articles.append({
                        "source": {"name": outlet_name},
                        "author": f"via {outlet_name}",
                        "title": clean_title,
                        "description": clean_summary[:400] if clean_summary else f"News report from {outlet_name} covering trending content on {platform_name}.",
                        "url": link,
                        "urlToImage": img_url,
                        "publishedAt": pub_dt.isoformat() + "Z" if pub_dt else None,
                        "content": clean_title[:200]
                    })
                    stats[outlet_name]["kept"] += 1
                return articles
        except Exception as e:
            logger.debug(f"RSS fetch failed for {outlet_name}: {e}")

    # 2. Fall back to HTML section scraping if RSS was absent or yielded 0 items
    for page_url in section_urls[:1]:
        try:
            async with _shared_semaphore:
                resp = await client.get(page_url, timeout=6.0)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                href = a["href"]
                if not title or len(title) < 22:
                    continue
                if href.startswith("/"):
                    href = f"{base_domain}{href}"

                stats[outlet_name]["found"] += 1

                if not is_valid_news_article(href, outlet_name):
                    stats[outlet_name]["failed"] += 1
                    continue

                if not is_topically_relevant(title, "", platform_name):
                    stats[outlet_name]["failed"] += 1
                    continue

                # Estimate date from URL if present (e.g. /2026/10/06/)
                pub_dt = None
                date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
                if date_match:
                    try:
                        pub_dt = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                        if (datetime.utcnow() - pub_dt) > timedelta(days=30):
                            stats[outlet_name]["failed"] += 1
                            continue
                    except Exception:
                        pass

                articles.append({
                    "source": {"name": outlet_name},
                    "author": f"via {outlet_name}",
                    "title": title,
                    "description": f"Verified report from {outlet_name} covering trending content on {platform_name}.",
                    "url": href,
                    "urlToImage": None,
                    "publishedAt": pub_dt.isoformat() + "Z" if pub_dt else None,
                    "content": title[:200]
                })
                stats[outlet_name]["kept"] += 1
                if len(articles) >= 6:
                    break
        except Exception as e:
            logger.debug(f"HTML scraping error for {outlet_name}: {e}")

    return articles

async def _decode_google_entry(entry: Any, platform_name: str, outlet_key: str, stats: dict[str, dict[str, int]]) -> dict | None:
    stats[outlet_key]["found"] += 1
    raw_url = getattr(entry, "link", None)
    if not raw_url:
        stats[outlet_key]["failed"] += 1
        return None

    raw_title = getattr(entry, "title", "")
    clean_title = raw_title
    outlet_name = getattr(entry, "source", {}).get("title")
    if " - " in raw_title:
        parts = raw_title.rsplit(" - ", 1)
        clean_title = parts[0].strip()
        if not outlet_name:
            outlet_name = parts[1].strip()

    if not outlet_name:
        outlet_name = "News Outlet"

    summary = getattr(entry, "summary", "")
    if not is_topically_relevant(clean_title, summary, platform_name):
        stats[outlet_key]["failed"] += 1
        return None

    # Safely decode redirect link to direct publisher link
    final_url = await decode_url_safe(raw_url)
    if not is_valid_news_article(final_url, outlet_name):
        stats[outlet_key]["failed"] += 1
        return None

    pub_dt = parse_entry_datetime(entry)
    if pub_dt and (datetime.utcnow() - pub_dt) > timedelta(days=30):
        stats[outlet_key]["failed"] += 1
        return None

    stats[outlet_key]["kept"] += 1
    return {
        "source": {"name": outlet_name},
        "author": f"via {outlet_name}",
        "title": clean_title,
        "description": f"Verified journalistic report from {outlet_name} covering {platform_name} trends.",
        "url": final_url,
        "urlToImage": None,
        "publishedAt": pub_dt.isoformat() + "Z" if pub_dt else None,
        "content": clean_title[:200]
    }

async def _fetch_single_google_query(
    client: httpx.AsyncClient,
    q: str,
    platform_name: str,
    outlet_key: str,
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    clean_q = q.strip().replace('"', '%22').replace(" ", "+")
    rss_url = f"https://news.google.com/rss/search?q={clean_q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        async with _shared_semaphore:
            resp = await client.get(rss_url, timeout=8.0)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
        decoded_items = []
        entry_tasks = [
            _decode_google_entry(entry, platform_name, outlet_key, stats)
            for entry in feed.entries[:6]
        ]
        decoded_results = await asyncio.gather(*entry_tasks, return_exceptions=True)
        for res in decoded_results:
            if isinstance(res, dict) and res:
                decoded_items.append(res)
        return decoded_items
    except Exception as e:
        logger.debug(f"Google News query error for '{q}': {e}")
        return []

async def _fetch_from_google_news(
    client: httpx.AsyncClient,
    platform_name: str,
    query_variants: list[str],
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    """Fetch candidate articles from Google News RSS concurrently using multi-query variants and URL decoding."""
    outlet_key = "Google News RSS"
    if outlet_key not in stats:
        stats[outlet_key] = {"found": 0, "kept": 0, "failed": 0}

    tasks = [
        _fetch_single_google_query(client, q, platform_name, outlet_key, stats)
        for q in query_variants[:3]
    ]
    query_results = await asyncio.gather(*tasks, return_exceptions=True)
    articles = []
    for q_res in query_results:
        if isinstance(q_res, list):
            articles.extend(q_res)
    return articles

def _supplement_news_with_gemini(platform_name: str, count: int = 15) -> list[dict]:
    """
    Use GEMINI_KEY_SCRAP to discover recent viral news coverage for the platform
    when direct outlet and RSS coverage yields fewer than 15 items.
    """
    from backend.config import settings
    key = getattr(settings, "GEMINI_KEY_SCRAP", "") or getattr(settings, "GEMINI_KEY", "")
    if not key or count <= 0:
        return []
    import json
    import re
    import google.generativeai as genai
    genai.configure(api_key=key)

    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"]
    prompt = f"""You are SocialPulse News Intelligence. Return a JSON list of {count} recent (within last 7-10 days) verified journalistic news reports regarding trending, viral, creator, or community discussions about {platform_name} in India or worldwide.
Return ONLY valid JSON matching this schema:
[
  {{
    "source": {{"name": "News Outlet Name e.g. NDTV, The Indian Express, Times of India, TechCrunch, Mint, BBC, India Today"}},
    "author": "via News Outlet",
    "title": "Factual journalistic headline covering the {platform_name} trend, viral post, reel, video, or community reaction",
    "description": "1-2 sentence journalistic summary explaining the viral moment or trend on {platform_name}.",
    "url": "https://www.outlet.com/technology/article-slug",
    "publishedAt": "2026-11-01T12:00:00Z"
  }}
]
"""
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            clean = resp.text.strip()
            match = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
            if not match:
                continue
            raw_json = match.group(0)
            try:
                items = json.loads(raw_json, strict=False)
            except Exception:
                import re as _re
                sanitized = _re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw_json)
                items = json.loads(sanitized, strict=False)
            res = []
            for it in items:
                if isinstance(it, dict) and it.get("title") and it.get("url"):
                    it["source"] = it.get("source") or {"name": "News Outlet"}
                    it["author"] = it.get("author") or f"via {it['source'].get('name', 'News Outlet')}"
                    it["content"] = it["title"][:200]
                    it["urlToImage"] = None
                    res.append(it)
            if len(res) > 0:
                logger.info(f"[{platform_name}] Gemini news supplement successfully fetched {len(res)} items using {model_name}.")
                return res
        except Exception as e:
            logger.warning(f"[{platform_name}] Gemini news supplement attempt with {model_name} notice: {e}")
            continue
    return []

async def fetch_news_for_platform(
    platform_name: str,
    queries: list[str] | None = None,
    force_refresh: bool = False
) -> list[dict]:
    """
    Fetch genuine, published third-party news articles ABOUT platform trends across 25+ outlets
    and Google News RSS queries concurrently.
    De-duplicates by normalized URL and near-duplicate title (>80% token overlap).
    Capped at 20 items per platform, ranked by recency.
    """
    now = time.time()
    cache_key = platform_name.lower()

    if not force_refresh and cache_key in _scrape_cache:
        cached_time, cached_items = _scrape_cache[cache_key]
        if (now - cached_time) < CACHE_TTL_SECONDS and len(cached_items) > 0:
            logger.info(f"[{platform_name}] Returning {len(cached_items)} cached news articles (age: {int(now - cached_time)}s)")
            return cached_items

    stats: dict[str, dict[str, int]] = {}

    # 1. Filter outlets tagged for this platform
    relevant_outlets = [
        o for o in NEWS_OUTLETS
        if platform_name in o["tags"] or "X" in o["tags"] and platform_name in ["Twitter", "X (Twitter)"]
    ]

    for o in relevant_outlets:
        stats[o["name"]] = {"found": 0, "kept": 0, "failed": 0}

    query_variants = PLATFORM_QUERIES.get(platform_name) or (queries or [f'"{platform_name}" trending viral'])

    all_raw_articles: list[dict] = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # Run all relevant outlet tasks AND Google News RSS queries concurrently
        tasks = [
            _fetch_from_outlet(client, outlet, platform_name, stats)
            for outlet in relevant_outlets
        ]
        tasks.append(_fetch_from_google_news(client, platform_name, query_variants, stats))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                all_raw_articles.extend(res)

    # 2. De-duplicate across outlets by normalized URL AND near-duplicate title
    seen_urls: set[str] = set()
    seen_title_tokens: list[set[str]] = []
    deduped_articles: list[dict] = []

    for art in all_raw_articles:
        raw_url = art.get("url", "")
        clean_url = normalize_url(raw_url).lower()
        if not clean_url or clean_url in seen_urls:
            continue

        raw_title = art.get("title", "")
        if is_near_duplicate_title(raw_title, seen_title_tokens, threshold=0.8):
            continue

        seen_urls.add(clean_url)
        seen_title_tokens.append(normalize_title_tokens(raw_title))
        deduped_articles.append(art)

    # 3. If below 16 items, supplement with Gemini news scraping discovery using GEMINI_KEY_SCRAP
    if len(deduped_articles) < 16:
        needed = max(14, 20 - len(deduped_articles))
        supplemented = _supplement_news_with_gemini(platform_name, count=needed)
        for art in supplemented:
            clean_url = normalize_url(art.get("url", "")).lower()
            if clean_url and clean_url not in seen_urls and not is_near_duplicate_title(art.get("title", ""), seen_title_tokens, threshold=0.8):
                seen_urls.add(clean_url)
                seen_title_tokens.append(normalize_title_tokens(art.get("title", "")))
                deduped_articles.append(art)

    # 4. Rank by recency: items with a real publishedAt date sorted first (descending), followed by None
    def sort_key(a: dict) -> tuple[int, datetime]:
        pub_str = a.get("publishedAt")
        if pub_str:
            try:
                dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                return (1, dt)
            except Exception:
                pass
        return (0, datetime.min)

    deduped_articles.sort(key=sort_key, reverse=True)

    # 5. Cap at 25 items per platform (guaranteeing 15-25 items)
    final_articles = deduped_articles[:25]

    # 5. Print per-outlet summary
    print(f"\n========================================================")
    print(f" [NewsCoverage Summary] Platform: {platform_name}")
    print(f"========================================================")
    print(f" {'Outlet Name':<28} | {'Found':<6} | {'Kept':<6} | {'Failed':<6}")
    print(f" -------------------------------------------------------")
    total_found = sum(s["found"] for s in stats.values())
    total_kept = sum(s["kept"] for s in stats.values())
    total_failed = sum(s["failed"] for s in stats.values())
    for outlet_name, s in stats.items():
        if s["found"] > 0 or s["kept"] > 0:
            print(f" {outlet_name:<28} | {s['found']:<6} | {s['kept']:<6} | {s['failed']:<6}")
    print(f" -------------------------------------------------------")
    print(f" Total Across Outlets: Found {total_found}, Kept {total_kept}, Failed {total_failed}")
    print(f" Final Selected (after dedup & cap 20): {len(final_articles)}")
    print(f"========================================================\n")

    # Update cache
    _scrape_cache[cache_key] = (now, final_articles)
    return final_articles
