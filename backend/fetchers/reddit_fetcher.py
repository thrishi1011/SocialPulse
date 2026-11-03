import json
from datetime import datetime
from typing import Any

from backend.config import settings
from backend.fetchers.base import AbstractFetcher, TrendingItemCreate

class RedditFetcher(AbstractFetcher):
    slug = "reddit"
    source_category = "A"

    async def fetch_raw(self) -> list[dict]:
        """Fetch hot posts across curated subreddits using PRAW or OAuth."""
        if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
            raise ValueError("Reddit API credentials (REDDIT_CLIENT_ID/SECRET) are not configured.")

        import praw
        reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT
        )

        all_raw = []
        # Query r/all first, then key subreddits
        for sub_name in settings.REDDIT_SUBREDDITS:
            try:
                sub = reddit.subreddit(sub_name)
                limit = 25 if sub_name in ("all", "popular") else 10
                for post in sub.hot(limit=limit):
                    all_raw.append({
                        "id": post.id,
                        "title": post.title,
                        "subreddit": post.subreddit.display_name,
                        "author": str(post.author) if post.author else "[deleted]",
                        "ups": post.ups,
                        "num_comments": post.num_comments,
                        "url": post.url,
                        "permalink": post.permalink,
                        "created_utc": post.created_utc,
                        "selftext": post.selftext,
                        "thumbnail": post.thumbnail if post.thumbnail and post.thumbnail.startswith("http") else None
                    })
            except Exception as e:
                print(f"Error fetching subreddit r/{sub_name}: {e}")
        return all_raw

    def normalize(self, raw_items: list[dict]) -> list[TrendingItemCreate]:
        items: list[TrendingItemCreate] = []
        seen_ids = set()

        for rank, raw in enumerate(raw_items, start=1):
            post_id = str(raw.get("id", "")).strip()
            if not post_id or post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            title = raw.get("title", "").strip()
            if not title:
                continue

            subreddit = raw.get("subreddit", "reddit")
            author = raw.get("author", "reddit_user")
            ups = raw.get("ups")
            comments = raw.get("num_comments")
            selftext = raw.get("selftext", "")
            thumb = raw.get("thumbnail")

            permalink = raw.get("permalink", "")
            if permalink.startswith("/"):
                url = f"https://reddit.com{permalink}"
            else:
                url = raw.get("url") or f"https://reddit.com/comments/{post_id}"

            # Convert created_utc timestamp
            pub_ts = raw.get("created_utc")
            published_at = None
            if pub_ts:
                try:
                    published_at = datetime.utcfromtimestamp(float(pub_ts))
                except Exception:
                    pass

            item = TrendingItemCreate(
                external_id=post_id,
                title=title,
                description=selftext[:500] if selftext else f"Posted by u/{author} in r/{subreddit}",
                url=url,
                thumbnail_url=thumb if (thumb and thumb.startswith("http")) else None,
                author=f"r/{subreddit}",
                engagement_value=int(ups) if ups is not None else None,
                engagement_label="upvotes",
                secondary_value=int(comments) if comments is not None else None,
                secondary_label="comments",
                rank=rank,
                region="global",
                published_at=published_at,
                raw_json=json.dumps(raw)
            )
            items.append(item)
        return items
