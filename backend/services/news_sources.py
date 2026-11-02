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
    },
    # 31. Indian Express Politics
    {
        "name": "Indian Express Politics",
        "base_domain": "https://indianexpress.com",
        "rss_url": "https://indianexpress.com/section/political-pulse/feed/",
        "section_urls": ["https://indianexpress.com/section/political-pulse/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 32. Indian Express India
    {
        "name": "Indian Express India",
        "base_domain": "https://indianexpress.com",
        "rss_url": "https://indianexpress.com/section/india/feed/",
        "section_urls": ["https://indianexpress.com/section/india/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 33. News18 Politics
    {
        "name": "News18 Politics",
        "base_domain": "https://www.news18.com",
        "rss_url": "https://www.news18.com/commonfeeds/v1/eng/rss/politics.xml",
        "section_urls": ["https://www.news18.com/politics/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 34. News18 India
    {
        "name": "News18 India",
        "base_domain": "https://www.news18.com",
        "rss_url": "https://www.news18.com/commonfeeds/v1/eng/rss/india.xml",
        "section_urls": ["https://www.news18.com/india/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 35. NDTV India Desk
    {
        "name": "NDTV India",
        "base_domain": "https://www.ndtv.com",
        "rss_url": "https://feeds.feedburner.com/ndtvnews-india-news",
        "section_urls": ["https://www.ndtv.com/india-news"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 36. NDTV Top Stories
    {
        "name": "NDTV Top Stories",
        "base_domain": "https://www.ndtv.com",
        "rss_url": "https://feeds.feedburner.com/ndtvnews-top-stories",
        "section_urls": ["https://www.ndtv.com/top-stories"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 37. The Hindu National
    {
        "name": "The Hindu National",
        "base_domain": "https://www.thehindu.com",
        "rss_url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "section_urls": ["https://www.thehindu.com/news/national/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 38. Mint Politics
    {
        "name": "Mint Politics",
        "base_domain": "https://www.livemint.com",
        "rss_url": "https://www.livemint.com/rss/politics",
        "section_urls": ["https://www.livemint.com/politics"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 39. Economic Times Politics
    {
        "name": "Economic Times Politics",
        "base_domain": "https://economictimes.indiatimes.com",
        "rss_url": "https://economictimes.indiatimes.com/news/politics-and-nation/rssfeeds/1052732854.cms",
        "section_urls": ["https://economictimes.indiatimes.com/news/politics-and-nation"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 40. Business Standard Politics
    {
        "name": "Business Standard Politics",
        "base_domain": "https://www.business-standard.com",
        "rss_url": "https://www.business-standard.com/rss/politics-105.rss",
        "section_urls": ["https://www.business-standard.com/politics"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 41. Business Standard Latest
    {
        "name": "Business Standard Latest",
        "base_domain": "https://www.business-standard.com",
        "rss_url": "https://www.business-standard.com/rss/latest.rss",
        "section_urls": ["https://www.business-standard.com/latest-news"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 42. Times of India National
    {
        "name": "Times of India National",
        "base_domain": "https://timesofindia.indiatimes.com",
        "rss_url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
        "section_urls": ["https://timesofindia.indiatimes.com/india"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 43. Times of India Tech Desk
    {
        "name": "Times of India Tech",
        "base_domain": "https://timesofindia.indiatimes.com",
        "rss_url": "https://timesofindia.indiatimes.com/rssfeeds/5880659.cms",
        "section_urls": ["https://timesofindia.indiatimes.com/gadgets-news"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
    },
    # 44. The Federal
    {
        "name": "The Federal",
        "base_domain": "https://thefederal.com",
        "rss_url": "https://thefederal.com/feed/",
        "section_urls": ["https://thefederal.com/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 45. The News Minute
    {
        "name": "The News Minute",
        "base_domain": "https://www.thenewsminute.com",
        "rss_url": "https://www.thenewsminute.com/feed",
        "section_urls": ["https://www.thenewsminute.com/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 46. Swarajya
    {
        "name": "Swarajya",
        "base_domain": "https://swarajyamag.com",
        "rss_url": "https://swarajyamag.com/feed",
        "section_urls": ["https://swarajyamag.com/"],
        "tags": ["Twitter", "X", "Facebook", "Instagram", "Reddit"]
    },
    # 47. ABP Live Trending
    {
        "name": "ABP Trending",
        "base_domain": "https://news.abplive.com",
        "rss_url": "https://news.abplive.com/trending/feed",
        "section_urls": ["https://news.abplive.com/trending"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 48. BBC News India Desk
    {
        "name": "BBC India",
        "base_domain": "https://www.bbc.com",
        "rss_url": "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
        "section_urls": ["https://www.bbc.com/news/world/asia/india"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 49. BBC News Technology
    {
        "name": "BBC Technology",
        "base_domain": "https://www.bbc.com",
        "rss_url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "section_urls": ["https://www.bbc.com/news/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 50. The Guardian India Desk
    {
        "name": "The Guardian India",
        "base_domain": "https://www.theguardian.com",
        "rss_url": "https://www.theguardian.com/world/india/rss",
        "section_urls": ["https://www.theguardian.com/world/india"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 51. The Guardian Technology
    {
        "name": "The Guardian Technology",
        "base_domain": "https://www.theguardian.com",
        "rss_url": "https://www.theguardian.com/technology/rss",
        "section_urls": ["https://www.theguardian.com/technology"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 52. Wired
    {
        "name": "Wired",
        "base_domain": "https://www.wired.com",
        "rss_url": "https://www.wired.com/feed/rss",
        "section_urls": ["https://www.wired.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 53. Wired Culture
    {
        "name": "Wired Culture",
        "base_domain": "https://www.wired.com",
        "rss_url": "https://www.wired.com/feed/category/culture/latest/rss",
        "section_urls": ["https://www.wired.com/category/culture/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 54. CNET
    {
        "name": "CNET",
        "base_domain": "https://www.cnet.com",
        "rss_url": "https://www.cnet.com/rss/news/",
        "section_urls": ["https://www.cnet.com/news/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit", "Twitch"]
    },
    # 55. ZDNet
    {
        "name": "ZDNet",
        "base_domain": "https://www.zdnet.com",
        "rss_url": "https://www.zdnet.com/news/rss.xml",
        "section_urls": ["https://www.zdnet.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X", "Reddit"]
    },
    # 56. Android Police
    {
        "name": "Android Police",
        "base_domain": "https://www.androidpolice.com",
        "rss_url": "https://www.androidpolice.com/feed/",
        "section_urls": ["https://www.androidpolice.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
    },
    # 57. Android Central
    {
        "name": "Android Central",
        "base_domain": "https://www.androidcentral.com",
        "rss_url": "https://www.androidcentral.com/feed",
        "section_urls": ["https://www.androidcentral.com/"],
        "tags": ["Instagram", "Facebook", "Twitter", "X"]
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

# Outlets with direct bot protection/WAF blocks whose coverage is queried via Google News RSS site:<domain>
DROPPED_OUTLETS_DOMAINS: list[tuple[str, str]] = [
    ("Hindustan Times", "hindustantimes.com"),
    ("Times Now", "timesnownews.com"),
    ("Zee News", "zeenews.india.com"),
    ("DNA India", "dnaindia.com"),
    ("Gadgets 360", "gadgets360.com"),
    ("Financial Express", "financialexpress.com"),
    ("Deccan Herald", "deccanherald.com")
]
