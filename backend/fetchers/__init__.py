from backend.fetchers.base import AbstractFetcher, TrendingItemCreate, FetchResult

# Category A: Direct Official APIs (3 sources)
from backend.fetchers.youtube_fetcher import YouTubeFetcher
from backend.fetchers.mastodon_fetcher import MastodonFetcher
from backend.fetchers.bluesky_fetcher import BlueskyFetcher

# Category B: Derived / Journalistic Signals (6 sources)
from backend.fetchers.google_trends_fetcher import GoogleTrendsFetcher
from backend.fetchers.instagram_news_fetcher import InstagramNewsFetcher
from backend.fetchers.facebook_news_fetcher import FacebookNewsFetcher
from backend.fetchers.twitter_news_fetcher import TwitterNewsFetcher
from backend.fetchers.reddit_news_fetcher import RedditNewsFetcher
from backend.fetchers.twitch_news_fetcher import TwitchNewsFetcher

ALL_FETCHERS: dict[str, AbstractFetcher] = {
    # Category A (3 sources)
    "youtube": YouTubeFetcher(),
    "mastodon": MastodonFetcher(),
    "bluesky": BlueskyFetcher(),

    # Category B (6 sources)
    "google_trends": GoogleTrendsFetcher(),
    "instagram_news": InstagramNewsFetcher(),
    "facebook_news": FacebookNewsFetcher(),
    "twitter_news": TwitterNewsFetcher(),
    "reddit_news": RedditNewsFetcher(),
    "twitch_news": TwitchNewsFetcher(),
}

def get_fetcher(slug: str) -> AbstractFetcher | None:
    return ALL_FETCHERS.get(slug)
