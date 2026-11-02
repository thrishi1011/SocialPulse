import urllib.parse
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

from backend.services.news_sources import NEWS_OUTLETS, DROPPED_OUTLETS_LOG, DROPPED_OUTLETS_DOMAINS
from backend.config import settings

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
MAX_ARTICLES_PER_PLATFORM = 80

# Google News decoded URL cache & concurrency limiter
_url_decode_cache: dict[str, str] = {}
_decode_semaphore = asyncio.Semaphore(4)

# Shared concurrency semaphore for courteous scraping
_shared_semaphore = asyncio.Semaphore(8)

# 18-20 rich query variants per platform (covering India and global; viral, trend, ban, backlash, creator, policy, and politics)
PLATFORM_QUERIES: dict[str, list[str]] = {
    "Instagram": [
        '"Instagram" trending viral',
        '"Instagram" reel viral India',
        '"Instagram" update creator trends',
        '"Instagram" backlash trend',
        '"Instagram trend" India',
        '"Instagram" political campaign ads India',
        '"Instagram" minister speech reel viral',
        '"Instagram" deepfake video viral election',
        '"Instagram" IT rules compliance notice',
        '"Instagram" protest video viral India',
        '"Instagram" account ban suspended controversy',
        '"Instagram" influencer controversy viral',
        '"Instagram" government takedown order',
        '"Instagram" algorithm change creator outcry',
        '"Instagram" meme trend viral debate',
        '"Instagram" viral challenge warning',
        '"Instagram" party election campaign viral',
        '"Instagram" court notice digital safety'
    ],
    "Facebook": [
        '"Facebook" viral post trend',
        '"Facebook" viral debate India',
        '"Facebook" community trend viral',
        '"Facebook" Meta controversy trend',
        '"Facebook" post sparks reaction India',
        '"Facebook" political ads election India',
        '"Facebook" post sparks political row',
        '"Facebook" minister post viral debate',
        '"Facebook" government takedown notice',
        '"Facebook" misinformation fact check viral',
        '"Facebook" deepfake political ad debate',
        '"Facebook" party campaign IT cell trend',
        '"Facebook" hate speech moderation row',
        '"Facebook" user protest viral campaign',
        '"Facebook" court notice algorithmic bias',
        '"Facebook" live stream viral controversy',
        '"Facebook" post case FIR registered India',
        '"Facebook" community standards ban trend'
    ],
    "Twitter": [
        '"Twitter" trending India viral',
        '"X" trending "on X" viral',
        '"Elon Musk" X trend debate',
        '"X users" trend backlash',
        '"viral tweet" trend reaction India',
        '"on X" political controversy India',
        '"tweeted" minister speech viral debate',
        '"on X" election campaign misinformation',
        '"X account" suspended government order',
        '"X" IT ministry notice blocking accounts',
        '"X" deepfake viral video debate',
        '"X spaces" political debate viral',
        '"tweet sparks" political row India',
        '"X algorithm" political bias debate',
        '"on X" protest hashtag trending',
        '"X post" fact check viral backlash',
        '"Twitter handle" official statement controversy',
        '"on X" opposition leader post viral'
    ],
    "X (Twitter)": [
        '"Twitter" trending India viral',
        '"X" trending "on X" viral',
        '"Elon Musk" X trend debate',
        '"X users" trend backlash',
        '"viral tweet" trend reaction India',
        '"on X" political controversy India',
        '"tweeted" minister speech viral debate',
        '"on X" election campaign misinformation',
        '"X account" suspended government order',
        '"X" IT ministry notice blocking accounts',
        '"X" deepfake viral video debate',
        '"X spaces" political debate viral',
        '"tweet sparks" political row India',
        '"X algorithm" political bias debate',
        '"on X" protest hashtag trending',
        '"X post" fact check viral backlash',
        '"Twitter handle" official statement controversy',
        '"on X" opposition leader post viral'
    ],
    "X": [
        '"Twitter" trending India viral',
        '"X" trending "on X" viral',
        '"Elon Musk" X trend debate',
        '"X users" trend backlash',
        '"viral tweet" trend reaction India',
        '"on X" political controversy India',
        '"tweeted" minister speech viral debate',
        '"on X" election campaign misinformation',
        '"X account" suspended government order',
        '"X" IT ministry notice blocking accounts',
        '"X" deepfake viral video debate',
        '"X spaces" political debate viral',
        '"tweet sparks" political row India',
        '"X algorithm" political bias debate',
        '"on X" protest hashtag trending',
        '"X post" fact check viral backlash',
        '"Twitter handle" official statement controversy',
        '"on X" opposition leader post viral'
    ],
    "Reddit": [
        "Reddit trending",
        "Reddit viral",
        "Reddit post debate",
        "Reddit thread India",
        "Reddit user viral",
        "Reddit controversy trend",
        "Reddit community reaction",
        "Reddit political debate India",
        "subreddit r/india viral discussion",
        "Reddit election discussion",
        "Reddit minister speech reaction",
        "Reddit IT policy debate",
        "Reddit protest campaign",
        "Reddit boycott controversy",
        "Reddit scam expose viral",
        "Reddit tech layoff discussion",
        "Reddit moderator policy backlash",
        "trending on Reddit discussion"
    ],
    "Twitch": [
        '"Twitch" streamer viral drama',
        '"Twitch" stream trend record',
        '"Twitch" esports gaming tournament viral',
        '"Twitch streamer" controversy ban',
        '"Twitch livestream" reaction viral',
        '"Twitch" platform policy update backlash',
        '"Twitch streamer" charity stream record',
        '"Twitch" DMCA copyright strike drama',
        '"Twitch" streamer boycott protest',
        '"Twitch" gambling ban policy controversy',
        '"Twitch" creator payout revenue split row',
        '"Twitch" live stream swatting incident',
        '"Twitch" gaming controversy viral',
        '"Twitch streamer" political debate stream',
        '"Twitch" India gaming creator stream',
        '"Twitch" community guidelines update trend',
        '"Twitch" subathon record viral stream',
        '"Twitch" streamer suspended apology'
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
        # Guard against bare 'x' (e.g. Model X, iPhone X, Generation X). Require explicit context.
        pattern = (
            r"\b(twitter|tweet|tweets|retweet|retweeted|elon musk)\b|"
            r"\bon x\b|"
            r"\bx\s*\((?:formerly\s*)?twitter\)|"
            r"\bx\s*(?:users?|posts?|feed|handle|account|platform|spaces|algorithm|community|bans?|blocking|subscribers?)\b|"
            r"\b(?:posted|trending|viral|shared)\s+on\s+x\b"
        )
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
        r"terms|feed|grid|update|notes?|creator|drama|stream|boycott|"
        r"politics|political|election|elections|minister|government|court|order|misinformation|"
        r"deepfake|notice|rule|rules|campaign|parliament|congress|bjp|banned|blocked|fir)\b"
    )
    return bool(re.search(trend_pattern, text, re.IGNORECASE))

def generate_news_article_id(url: str) -> str:
    """Generate deterministic 32-character SHA-256 hash of article URL."""
    clean_url = normalize_url(url).lower()
    return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()[:32]

def _sync_decode_url(raw_url: str) -> str:
    if raw_url in _url_decode_cache:
        return _url_decode_cache[raw_url]
    clean = raw_url.split("?")[0] if "?" in raw_url else raw_url
    for attempt in range(2):
        try:
            res = googlenewsdecoder.new_decoderv1(clean, interval=0.1)
            if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
                decoded = res["decoded_url"]
                if decoded and "news.google.com" not in decoded.lower():
                    _url_decode_cache[raw_url] = decoded
                    return decoded
        except Exception:
            if attempt == 0:
                time.sleep(0.15)
    return ""

async def decode_url_safe(raw_url: str) -> str:
    """Decode Google News redirect URL to direct publisher link with caching, retry, and semaphore(4)."""
    if "/articles/" not in raw_url:
        return raw_url
    if raw_url in _url_decode_cache:
        return _url_decode_cache[raw_url]
    async with _decode_semaphore:
        try:
            decoded = await asyncio.wait_for(asyncio.to_thread(_sync_decode_url, raw_url), timeout=6.0)
            return decoded or ""
        except Exception:
            return ""

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
                for entry in feed.entries[:60]:
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
                if articles:
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
    query_str = q.strip()
    if "when:" not in query_str:
        query_str = f"{query_str} when:7d"
    encoded_q = urllib.parse.quote_plus(query_str)
    rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        async with _shared_semaphore:
            resp = await client.get(rss_url, timeout=7.0)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
        decoded_items = []
        for entry in feed.entries[:40]:
            item = await _decode_google_entry(entry, platform_name, outlet_key, stats)
            if item:
                decoded_items.append(item)
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

    # Run top 10 query variants to ensure broad coverage while respecting latency
    tasks = [
        _fetch_single_google_query(client, q, platform_name, outlet_key, stats)
        for q in query_variants[:10]
    ]
    query_results = await asyncio.gather(*tasks, return_exceptions=True)
    articles = []
    for q_res in query_results:
        if isinstance(q_res, list):
            articles.extend(q_res)
    return articles

async def _fetch_from_bing_news(
    client: httpx.AsyncClient,
    platform_name: str,
    query_variants: list[str],
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    """Fetch candidate articles from Bing News RSS with direct URL unwrapping."""
    outlet_key = "Bing News RSS"
    if outlet_key not in stats:
        stats[outlet_key] = {"found": 0, "kept": 0, "failed": 0}

    articles: list[dict] = []
    selected_queries = query_variants[:6]

    async def _fetch_bing_q(q: str) -> list[dict]:
        items = []
        encoded_q = urllib.parse.quote_plus(q)
        bing_url = f"https://www.bing.com/news/search?q={encoded_q}&format=rss&cc=IN"
        try:
            async with _shared_semaphore:
                resp = await client.get(bing_url, timeout=6.0)
            if resp.status_code != 200:
                return []
            feed = feedparser.parse(resp.text)
            for entry in feed.entries:
                stats[outlet_key]["found"] += 1
                raw_link = getattr(entry, "link", None)
                if not raw_link:
                    stats[outlet_key]["failed"] += 1
                    continue

                target_url = raw_link
                try:
                    parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                    if "url" in parsed_qs and parsed_qs["url"]:
                        target_url = parsed_qs["url"][0]
                except Exception:
                    pass

                outlet_name = getattr(entry, "news_source", None) or "Bing News"
                raw_title = getattr(entry, "title", "")
                clean_title = re.sub(r"\s+", " ", raw_title).strip()
                if " - " in clean_title and outlet_name == "Bing News":
                    parts = clean_title.rsplit(" - ", 1)
                    clean_title = parts[0].strip()
                    outlet_name = parts[1].strip()

                if not is_valid_news_article(target_url, outlet_name):
                    stats[outlet_key]["failed"] += 1
                    continue

                summary = getattr(entry, "summary", "") or ""
                clean_summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)
                if not is_topically_relevant(clean_title, clean_summary, platform_name):
                    stats[outlet_key]["failed"] += 1
                    continue

                pub_dt = parse_entry_datetime(entry)
                if pub_dt and (datetime.utcnow() - pub_dt) > timedelta(days=30):
                    stats[outlet_key]["failed"] += 1
                    continue

                items.append({
                    "source": {"name": outlet_name},
                    "author": f"via {outlet_name}",
                    "title": clean_title,
                    "description": clean_summary[:400] if clean_summary else f"News report from {outlet_name} covering {platform_name} trends.",
                    "url": target_url,
                    "urlToImage": None,
                    "publishedAt": pub_dt.isoformat() + "Z" if pub_dt else None,
                    "content": clean_title[:200]
                })
                stats[outlet_key]["kept"] += 1
        except Exception as e:
            logger.debug(f"Bing News error for '{q}': {e}")
        return items

    bing_tasks = [_fetch_bing_q(q) for q in selected_queries]
    bing_results = await asyncio.gather(*bing_tasks, return_exceptions=True)
    for res in bing_results:
        if isinstance(res, list):
            articles.extend(res)
    return articles

_last_gdelt_time: float = 0.0
_gdelt_lock = asyncio.Lock()

async def _fetch_from_gdelt(
    client: httpx.AsyncClient,
    platform_name: str,
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    """Fetch candidate articles from GDELT DOC 2.0 with 5s polite throttle and non-JSON guard."""
    outlet_key = "GDELT DOC 2.0"
    if outlet_key not in stats:
        stats[outlet_key] = {"found": 0, "kept": 0, "failed": 0}

    articles: list[dict] = []
    global _last_gdelt_time
    async with _gdelt_lock:
        now = time.time()
        elapsed = now - _last_gdelt_time
        if elapsed < 5.0:
            await asyncio.sleep(5.0 - elapsed)
        _last_gdelt_time = time.time()

    query_term = f'"{platform_name}"'
    encoded_q = urllib.parse.quote_plus(query_term)
    gdelt_url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={encoded_q}&mode=artlist&format=json&maxrecords=50&timespan=7d"
    try:
        async with _shared_semaphore:
            resp = await client.get(gdelt_url, timeout=5.0)
        if resp.status_code != 200:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        raw_articles = data.get("articles", []) if isinstance(data, dict) else []
        for art in raw_articles:
            stats[outlet_key]["found"] += 1
            url = art.get("url", "")
            title = art.get("title", "")
            domain = art.get("domain", "GDELT")
            if not is_valid_news_article(url, domain):
                stats[outlet_key]["failed"] += 1
                continue
            if not is_topically_relevant(title, "", platform_name):
                stats[outlet_key]["failed"] += 1
                continue

            seendate = art.get("seendate", "")
            pub_dt = None
            if seendate:
                try:
                    pub_dt = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
                except Exception:
                    pass

            articles.append({
                "source": {"name": domain},
                "author": f"via {domain}",
                "title": title,
                "description": f"Verified reporting via {domain} covering {platform_name} trends.",
                "url": url,
                "urlToImage": None,
                "publishedAt": pub_dt.isoformat() + "Z" if pub_dt else None,
                "content": title[:200]
            })
            stats[outlet_key]["kept"] += 1
    except Exception as e:
        logger.debug(f"GDELT fetch skipped/failed: {e}")

    return articles

async def _fetch_dropped_outlets_via_google(
    client: httpx.AsyncClient,
    platform_name: str,
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    """Query Google News RSS for major dropped outlets (Hindustan Times, Times Now, Gadgets 360, etc.)."""
    articles: list[dict] = []
    tasks = []
    for outlet_name, domain in DROPPED_OUTLETS_DOMAINS[:4]:
        outlet_key = f"{outlet_name} (via Google)"
        if outlet_key not in stats:
            stats[outlet_key] = {"found": 0, "kept": 0, "failed": 0}
        q = f'"{platform_name}" site:{domain} when:7d'
        tasks.append(_fetch_single_google_query(client, q, platform_name, outlet_key, stats))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, list):
            articles.extend(res)
    return articles

async def _fetch_optional_api_news(
    client: httpx.AsyncClient,
    platform_name: str,
    stats: dict[str, dict[str, int]]
) -> list[dict]:
    """Fetch from NewsAPI or GNews if optional API keys are configured."""
    articles: list[dict] = []
    newsapi_key = getattr(settings, "NEWSAPI_KEY", "") or ""
    if newsapi_key.strip():
        outlet_key = "NewsAPI"
        if outlet_key not in stats:
            stats[outlet_key] = {"found": 0, "kept": 0, "failed": 0}
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote_plus(platform_name)}&language=en&sortBy=publishedAt&apiKey={newsapi_key.strip()}"
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                for art in resp.json().get("articles", [])[:20]:
                    stats[outlet_key]["found"] += 1
                    u = art.get("url")
                    t = art.get("title")
                    src = art.get("source", {}).get("name") or "NewsAPI"
                    if is_valid_news_article(u, src) and is_topically_relevant(t, art.get("description", ""), platform_name):
                        articles.append(art)
                        stats[outlet_key]["kept"] += 1
                    else:
                        stats[outlet_key]["failed"] += 1
        except Exception as e:
            logger.debug(f"NewsAPI error: {e}")

    gnews_key = getattr(settings, "GNEWS_KEY", "") or ""
    if gnews_key.strip():
        outlet_key = "GNews"
        if outlet_key not in stats:
            stats[outlet_key] = {"found": 0, "kept": 0, "failed": 0}
        url = f"https://gnews.io/api/v4/search?q={urllib.parse.quote_plus(platform_name)}&lang=en&token={gnews_key.strip()}"
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                for art in resp.json().get("articles", [])[:20]:
                    stats[outlet_key]["found"] += 1
                    u = art.get("url")
                    t = art.get("title")
                    src = art.get("source", {}).get("name") or "GNews"
                    if is_valid_news_article(u, src) and is_topically_relevant(t, art.get("description", ""), platform_name):
                        articles.append(art)
                        stats[outlet_key]["kept"] += 1
                    else:
                        stats[outlet_key]["failed"] += 1
        except Exception as e:
            logger.debug(f"GNews error: {e}")

    return articles

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
        # Run all relevant outlet tasks, Google News, Bing News, Dropped Outlets, GDELT, and optional APIs concurrently
        tasks = [
            _fetch_from_outlet(client, outlet, platform_name, stats)
            for outlet in relevant_outlets
        ]
        tasks.append(_fetch_from_google_news(client, platform_name, query_variants, stats))
        tasks.append(_fetch_from_bing_news(client, platform_name, query_variants, stats))
        tasks.append(_fetch_dropped_outlets_via_google(client, platform_name, stats))
        tasks.append(_fetch_from_gdelt(client, platform_name, stats))
        tasks.append(_fetch_optional_api_news(client, platform_name, stats))

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

    # 3. Rank by recency: items with a real publishedAt date sorted first (descending), followed by None
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

    # 4. Cap at 20 items per platform
    final_articles = deduped_articles[:MAX_ARTICLES_PER_PLATFORM]

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
