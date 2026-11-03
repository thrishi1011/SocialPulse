"""
news_sources.py
Curated and verified news outlets for Category B news coverage scraping.
Covers major Indian national journalism desks, technology desks, digital culture publications,
and specialized international gaming/streaming desks.
"""

from typing import TypedDict

class NewsOutletConfig(TypedDict):
    name: str
    base_domain: str
    rss_url: str | None
    section_urls: list[str]
    tags: list[str]

# Curated list of outlets verified to return HTTP 200 with active articles / feeds
NEWS_OUTLETS: list[NewsOutletConfig] = [
    # 1. The Indian Express
    {
        "name": "The Indian Express",
        "base_domain": "https://indianexpress.com",
        "rss_url": "https://indianexpress.com/section/trending/feed/",
        "section_urls": ["https://indianexpress.com/section/trending/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 2. News18
    {
        "name": "News18",
        "base_domain": "https://www.news18.com",
        "rss_url": "https://www.news18.com/commonfeeds/v1/eng/rss/buzz.xml",
        "section_urls": ["https://www.news18.com/buzz/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 3. India Today
    {
        "name": "India Today",
        "base_domain": "https://www.indiatoday.in",
        "rss_url": "https://www.indiatoday.in/rss/1206577",
        "section_urls": ["https://www.indiatoday.in/trending-news"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 4. NDTV
    {
        "name": "NDTV",
        "base_domain": "https://www.ndtv.com",
        "rss_url": "https://feeds.feedburner.com/ndtvnews-trending-news",
        "section_urls": ["https://www.ndtv.com/trends"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 5. The Hindu
    {
        "name": "The Hindu",
        "base_domain": "https://www.thehindu.com",
        "rss_url": "https://www.thehindu.com/sci-tech/technology/feeder/default.rss",
        "section_urls": ["https://www.thehindu.com/sci-tech/technology/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 6. Livemint / Mint
    {
        "name": "Mint",
        "base_domain": "https://www.livemint.com",
        "rss_url": "https://www.livemint.com/rss/technology",
        "section_urls": ["https://www.livemint.com/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 7. Times of India
    {
        "name": "Times of India",
        "base_domain": "https://timesofindia.indiatimes.com",
        "rss_url": "https://timesofindia.indiatimes.com/rssfeeds/66949542.cms",
        "section_urls": ["https://timesofindia.indiatimes.com/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 8. Firstpost
    {
        "name": "Firstpost",
        "base_domain": "https://www.firstpost.com",
        "rss_url": "https://www.firstpost.com/commonfeeds/v1/mfp/rss/tech.xml",
        "section_urls": ["https://www.firstpost.com/tech"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 9. Economic Times
    {
        "name": "Economic Times",
        "base_domain": "https://economictimes.indiatimes.com",
        "rss_url": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
        "section_urls": ["https://economictimes.indiatimes.com/tech"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 10. Telangana Today
    {
        "name": "Telangana Today",
        "base_domain": "https://telanganatoday.com",
        "rss_url": "https://telanganatoday.com/feed",
        "section_urls": ["https://telanganatoday.com/entertainment"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 11. Business Standard
    {
        "name": "Business Standard",
        "base_domain": "https://www.business-standard.com",
        "rss_url": "https://www.business-standard.com/rss/technology-108.rss",
        "section_urls": ["https://www.business-standard.com/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 12. ABP Live
    {
        "name": "ABP Live",
        "base_domain": "https://news.abplive.com",
        "rss_url": "https://news.abplive.com/technology/feed",
        "section_urls": ["https://news.abplive.com/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 13. Moneycontrol
    {
        "name": "Moneycontrol",
        "base_domain": "https://www.moneycontrol.com",
        "rss_url": "https://www.moneycontrol.com/rss/technology.xml",
        "section_urls": ["https://www.moneycontrol.com/news/technology/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
    },
    # 14. Scroll.in
    {
        "name": "Scroll",
        "base_domain": "https://scroll.in",
        "rss_url": None,
        "section_urls": ["https://scroll.in/tag/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 15. Deccan Chronicle
    {
        "name": "Deccan Chronicle",
        "base_domain": "https://www.deccanchronicle.com",
        "rss_url": None,
        "section_urls": ["https://www.deccanchronicle.com/technology/gadgets"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
    },
    # 16. MediaNama (Indian internet & digital policy)
    {
        "name": "MediaNama",
        "base_domain": "https://www.medianama.com",
        "rss_url": "https://www.medianama.com/feed/",
        "section_urls": ["https://www.medianama.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 17. Inc42 (Indian digital platforms & tech trends)
    {
        "name": "Inc42",
        "base_domain": "https://inc42.com",
        "rss_url": "https://inc42.com/feed/",
        "section_urls": ["https://inc42.com/buzz/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 18. YourStory
    {
        "name": "YourStory",
        "base_domain": "https://yourstory.com",
        "rss_url": "https://yourstory.com/feed",
        "section_urls": ["https://yourstory.com/stories"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
    },
    # 19. Digit
    {
        "name": "Digit",
        "base_domain": "https://www.digit.in",
        "rss_url": "https://www.digit.in/feed/",
        "section_urls": ["https://www.digit.in/news/technology/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Twitch"]
    },
    # 20. TechCrunch (International social desk)
    {
        "name": "TechCrunch",
        "base_domain": "https://techcrunch.com",
        "rss_url": "https://techcrunch.com/feed/",
        "section_urls": ["https://techcrunch.com/category/social/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 21. The Verge
    {
        "name": "The Verge",
        "base_domain": "https://www.theverge.com",
        "rss_url": "https://www.theverge.com/rss/index.xml",
        "section_urls": ["https://www.theverge.com/tech"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 22. Social Media Today
    {
        "name": "Social Media Today",
        "base_domain": "https://www.socialmediatoday.com",
        "rss_url": "https://www.socialmediatoday.com/feeds/news/",
        "section_urls": ["https://www.socialmediatoday.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 23. Engadget
    {
        "name": "Engadget",
        "base_domain": "https://www.engadget.com",
        "rss_url": "https://www.engadget.com/rss.xml",
        "section_urls": ["https://www.engadget.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Twitch"]
    },
    # 24. Mashable
    {
        "name": "Mashable",
        "base_domain": "https://mashable.com",
        "rss_url": "https://mashable.com/feeds/rss/all",
        "section_urls": ["https://mashable.com/category/social-media"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 25. 9to5Mac
    {
        "name": "9to5Mac",
        "base_domain": "https://9to5mac.com",
        "rss_url": "https://9to5mac.com/feed/",
        "section_urls": ["https://9to5mac.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
    },
    # 26. 9to5Google
    {
        "name": "9to5Google",
        "base_domain": "https://9to5google.com",
        "rss_url": "https://9to5google.com/feed/",
        "section_urls": ["https://9to5google.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 27. Ars Technica
    {
        "name": "Ars Technica",
        "base_domain": "https://arstechnica.com",
        "rss_url": "https://feeds.arstechnica.com/arstechnica/index",
        "section_urls": ["https://arstechnica.com/tech-policy/"],
        "tags": ["Twitter", "X", "Reddit", "Facebook"]
    },
    # 28. Polygon (Gaming & streaming culture)
    {
        "name": "Polygon",
        "base_domain": "https://www.polygon.com",
        "rss_url": "https://www.polygon.com/rss/index.xml",
        "section_urls": ["https://www.polygon.com/"],
        "tags": ["Twitch", "Reddit"]
    },
    # 29. Esports Insider (Twitch & streamer industry)
    {
        "name": "Esports Insider",
        "base_domain": "https://esportsinsider.com",
        "rss_url": "https://esportsinsider.com/feed",
        "section_urls": ["https://esportsinsider.com/"],
        "tags": ["Twitch"]
    },
    # 30. GamesRadar (Twitch & gaming community trends)
    {
        "name": "GamesRadar",
        "base_domain": "https://www.gamesradar.com",
        "rss_url": "https://www.gamesradar.com/rss/",
        "section_urls": ["https://www.gamesradar.com/news/"],
        "tags": ["Twitch"]
    }
]

# Tracked outlets that were tested and dropped due to HTTP 403, 404, or certificate issues
DROPPED_OUTLETS_LOG: list[dict[str, str]] = [
    {"name": "Hindustan Times", "reason": "HTTP 403 (Cloudflare bot protection blocks automated scrapers)"},
    {"name": "Times Now", "reason": "HTTP 403 (Access forbidden for automated requests)"},
    {"name": "Zee News", "reason": "HTTP 403 (WAF blocking request)"},
    {"name": "DNA India", "reason": "HTTP 403 (WAF blocking request)"},
    {"name": "Gadgets 360", "reason": "HTTP 403 (Forbidden)"},
    {"name": "Financial Express", "reason": "HTTP 410 (RSS feed permanently gone)"},
    {"name": "Deccan Herald", "reason": "HTTP 500 (Internal server error on feed)"},
    {"name": "Hans India", "reason": "HTTP 404 (Feed endpoint not found)"},
    {"name": "Republic World", "reason": "HTTP 404 (Tech feed endpoint missing)"},
    {"name": "The New Indian Express", "reason": "HTTP 404 (Tech feed endpoint missing)"},
    {"name": "India TV News", "reason": "HTTP 404 (Feed endpoint missing)"},
    {"name": "OneIndia", "reason": "HTTP 404 (Feed endpoint missing)"},
    {"name": "CNBC TV18", "reason": "HTTP 400 (Bad request on RSS endpoint)"},
    {"name": "Dot Esports", "reason": "HTTP 403 (Cloudflare block on direct scraping)"},
    {"name": "Dexerto", "reason": "SSL Certificate verification failure"},
    {"name": "Kotaku", "reason": "SSL Certificate verification failure"}
]
