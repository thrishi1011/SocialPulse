"""
backend/services/comments_service.py

Sourced Community Comments Service:
- Fetches real top-level comments for YouTube items via YouTube Data API v3.
- Sorts 100 candidate threads by likeCount descending and persists the top 10.
- Caches comments for 6 hours; purges/refreshes rows older than 7 days (policy compliance).
- Handles commentsDisabled, quotaExceeded, and missing API keys gracefully.
- Restricts comments strictly to YouTube; other sources return empty (no invented comments).
- Gated behind ENABLE_SAMPLE_COMMENTS for mock/sample items (default False).
"""
import random
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Comment, TrendingItem, Topic, Source
from backend.schemas import CommentListResponse, CommentResponse

logger = logging.getLogger("socialpulse.comments")

AVATAR_COLORS = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#8b5cf6",  # violet
    "#f59e0b",  # amber
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#6366f1",  # indigo
    "#f97316",  # orange
]


class CommentList(list):
    """A list of comments that carries an optional error/status message."""
    def __init__(self, iterable=None, error: Optional[str] = None):
        super().__init__(iterable or [])
        self.error = error


def is_sample_or_mock_item(item: TrendingItem) -> bool:
    """Detect if an item is a mock, seeded test, or synthetic sample."""
    ext = (item.external_id or "").lower()
    url = (item.url or "").lower()
    if ext.startswith(("sample_", "mock_", "test_")) or "example.com" in url or "mock" in url:
        return True
    # Seeded YouTube mock IDs from cold start
    if ext in {"dla_64yz8ss", "1kky43k5dk8", "8z1emy2fox4", "2epf9rue1ao", "fj9ruzimczq", "l_lupnjgpso", "kjqp7kiw5fk"}:
        return True
    return False


def purge_expired_comments(db: Session, max_age_days: int = 7) -> int:
    """Delete cached comment rows older than 7 days to stay well inside the 30-day policy."""
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    try:
        deleted = db.query(Comment).filter(Comment.created_at < cutoff).delete()
        if deleted > 0:
            db.commit()
            logger.info(f"Purged {deleted} comment rows older than {max_age_days} days.")
        return deleted
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to purge expired comments: {e}")
        return 0


def _extract_keywords(text: str) -> List[str]:
    """Extract clean content keywords from a title or description."""
    if not text:
        return ["topic"]
    cleaned = re.sub(r"[^\w\s]", "", text)
    stopwords = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
        "live", "breaking", "official", "highlights", "video", "news", "coverage"
    }
    words = [w for w in cleaned.split() if len(w) > 3 and w.lower() not in stopwords]
    return words[:5] if words else ["updates"]


def _generate_synthetic_item_comments(item: TrendingItem, count: int = 10) -> List[Dict[str, Any]]:
    """Generate clearly labelled sample comments for mock/sample items when ENABLE_SAMPLE_COMMENTS is on."""
    title = item.title or "Trending Story"
    category_name = item.category.name if item.category else "General"
    keywords = _extract_keywords(title)
    kw1 = keywords[0] if keywords else "this"
    kw2 = keywords[1] if len(keywords) > 1 else "the development"

    seed_val = (item.id or 0) * 31 + len(title)
    rng = random.Random(seed_val)

    templates = [
        {"sentiment": "excited", "text": f"Huge milestone for {kw1}! The scale and execution here is genuinely impressive.", "upvotes": (350, 2400)},
        {"sentiment": "positive", "text": f"Really well explained. Seeing {kw2} gain this much traction across platforms is well deserved.", "upvotes": (120, 1100)},
        {"sentiment": "curious", "text": f"Interesting approach. Does anyone know how this compares to what we saw earlier this year with {kw1}?", "upvotes": (45, 680)},
        {"sentiment": "critical", "text": f"Promising headline, but let's wait to see sustained results before jumping to conclusions on {kw2}.", "upvotes": (60, 890)},
        {"sentiment": "neutral", "text": f"The broader implications for {category_name.lower()} here are worth watching closely over the next few weeks.", "upvotes": (80, 750)},
        {"sentiment": "positive", "text": f"Shared this with my team this morning. The discussion around {kw1} is already opening a lot of eyes.", "upvotes": (95, 920)},
        {"sentiment": "excited", "text": f"Incredible momentum for {kw1}! This is definitely one of the top stories right now.", "upvotes": (310, 1850)},
        {"sentiment": "neutral", "text": f"Following the updates on {kw2} closely. Looking forward to official statements later this week.", "upvotes": (50, 510)},
        {"sentiment": "positive", "text": f"Solid breakdown of {kw1}. Glad to see key community voices highlighting this.", "upvotes": (140, 1050)},
        {"sentiment": "critical", "text": f"We need more transparent data before celebrating {kw1}. There are still valid unanswered questions.", "upvotes": (85, 940)},
    ]

    personas = [
        ("Arjun Mehta", "ArjunMehtaTech", "#3b82f6"),
        ("Aarav Sharma", "AaravS_Official", "#10b981"),
        ("Tech Pulse India", "TechPulseIN", "#ec4899"),
        ("Pooja Nair", "PoojaExplores", "#8b7cf6"),
        ("Rohan Desai", "RohanReviews", "#f59e0b"),
        ("Science Lens", "ScienceLensIN", "#06b6d4"),
        ("Ananya Verma", "AnanyaV_Tech", "#6366f1"),
        ("Vikram Aditya", "VikramAdityaMedia", "#f97316"),
        ("Deepa Menon", "DeepaAnalyst", "#10b981"),
        ("Kavita Rao", "KavitaRaoVlogs", "#3b82f6"),
    ]

    comments_data = []
    base_time = item.published_at or item.fetched_at or datetime.utcnow()
    selected_templates = rng.sample(templates, min(count, len(templates)))

    for idx, tmpl in enumerate(selected_templates):
        author_name, author_handle, color = personas[idx % len(personas)]
        offset_minutes = rng.randint(15, 240)
        comment_time = max(datetime.utcnow() - timedelta(days=1), base_time + timedelta(minutes=offset_minutes))
        if comment_time > datetime.utcnow():
            comment_time = datetime.utcnow() - timedelta(minutes=rng.randint(5, 45))

        comments_data.append({
            "author": author_name,
            "author_handle": f"@{author_handle}",
            "author_avatar_color": color,
            "platform": "youtube",
            "content": tmpl["text"],
            "upvotes": rng.randint(tmpl["upvotes"][0], tmpl["upvotes"][1]),
            "sentiment": tmpl["sentiment"],
            "is_generated": True,
            "url": f"https://www.youtube.com/watch?v={item.external_id}&lc=sample_{idx}",
            "published_at": comment_time,
        })

    return comments_data


def _fetch_real_youtube_comment_threads(item: TrendingItem, limit: int = 10) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch up to 100 comment threads via YouTube Data API v3 with order=relevance & textFormat=plainText,
    take the 10 with the highest likeCount, and format direct YouTube links.
    """
    if not settings.YOUTUBE_API_KEY:
        return [], "YouTube API key is not configured."

    video_id = item.external_id
    if not video_id:
        return [], "Missing YouTube video ID."

    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",
        "maxResults": 100,
        "textFormat": "plainText",
        "key": settings.YOUTUBE_API_KEY
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)

            if resp.status_code == 200:
                data = resp.json()
                raw_items = data.get("items", [])
                if not raw_items:
                    return [], None

                parsed = []
                for it in raw_items:
                    top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    comment_id = it.get("id")
                    author = top.get("authorDisplayName", "YouTube User")
                    text = top.get("textDisplay") or top.get("textOriginal", "")
                    likes = int(top.get("likeCount", 0))
                    pub_str = top.get("publishedAt")
                    pub_dt = datetime.utcnow()
                    if pub_str:
                        try:
                            pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            pass

                    clean_text = text.strip()
                    if not clean_text:
                        continue

                    # Lightweight sentiment derivation
                    lower_t = clean_text.lower()
                    if any(w in lower_t for w in ["great", "awesome", "love", "amazing", "best", "brilliant", "super", "proud", "fire", "badhiya", "shandar", "banger"]):
                        sentiment = "positive"
                    elif any(w in lower_t for w in ["why", "how", "what", "question", "does", "can", "when"]):
                        sentiment = "curious"
                    elif any(w in lower_t for w in ["bad", "wrong", "fake", "hate", "terrible", "worst", "disagree", "bakwaas", "ghatiya"]):
                        sentiment = "critical"
                    else:
                        sentiment = "neutral"

                    # Direct link to comment on YouTube
                    comment_url = f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"

                    parsed.append({
                        "author": author,
                        "author_handle": f"@{re.sub(r'[^a-zA-Z0-9_]', '', author)[:20]}",
                        "author_avatar_color": random.choice(AVATAR_COLORS),
                        "platform": "youtube",
                        "content": clean_text,
                        "upvotes": likes,
                        "sentiment": sentiment,
                        "is_generated": False,
                        "url": comment_url,
                        "published_at": pub_dt
                    })

                # Sort by likeCount descending and take top 10
                parsed.sort(key=lambda x: x["upvotes"], reverse=True)
                return parsed[:limit], None

            elif resp.status_code == 403:
                data = resp.json().get("error", {})
                reasons = [e.get("reason", "") for e in data.get("errors", [])]
                raw_msg = data.get("message", "").lower()
                if "commentsdisabled" in reasons or "disabled comments" in raw_msg:
                    return [], "Comments are turned off for this video."
                elif "quotaexceeded" in reasons or "quota" in raw_msg:
                    return [], "YouTube API daily quota exceeded. Please check back later."
                else:
                    return [], f"YouTube API access denied: {data.get('message', 'Forbidden')}"

            elif resp.status_code == 404:
                return [], "YouTube video not found or comments unavailable."

            else:
                return [], f"YouTube API returned status {resp.status_code}."

    except Exception as e:
        logger.warning(f"Error fetching real YouTube comments for {video_id}: {e}")
        return [], f"Failed to retrieve comments: {str(e)}"


def get_or_create_item_comments(db: Session, item: TrendingItem, limit: int = 10) -> CommentList:
    """
    Retrieve top 10 comments for a YouTube TrendingItem.
    - Strictly restricts comments to YouTube items (other sources return empty).
    - Checks 6-hour cache; purges rows older than 7 days.
    - If stale/missing, fetches real data from YouTube API, taking top 10 by likeCount.
    - If sample/mock item, only shows generated comments if ENABLE_SAMPLE_COMMENTS is True.
    """
    # 1. Non-YouTube items show nothing (no invented comments)
    if not item.source or item.source.slug != "youtube":
        return CommentList([], error=None)

    # 2. Routine compliance cleanup (purge cached comments older than 7 days)
    purge_expired_comments(db, max_age_days=7)

    # 3. Check for Sample / Mock items
    if is_sample_or_mock_item(item):
        if not settings.ENABLE_SAMPLE_COMMENTS:
            return CommentList([], error=None)

        # Return existing cached sample comments if available
        existing = db.query(Comment).filter(Comment.item_id == item.id).order_by(Comment.upvotes.desc()).limit(limit).all()
        if existing:
            return CommentList(existing, error=None)

        raw_comments = _generate_synthetic_item_comments(item, count=limit)
        new_comments = []
        for c_data in raw_comments:
            c = Comment(
                item_id=item.id,
                topic_id=item.topic_id,
                author=c_data["author"],
                author_handle=c_data["author_handle"],
                author_avatar_color=c_data["author_avatar_color"],
                platform=c_data["platform"],
                content=c_data["content"],
                upvotes=c_data["upvotes"],
                sentiment=c_data["sentiment"],
                is_generated=True,
                url=c_data.get("url"),
                published_at=c_data["published_at"],
                created_at=datetime.utcnow()
            )
            db.add(c)
            new_comments.append(c)
        try:
            db.commit()
        except Exception:
            db.rollback()
        new_comments.sort(key=lambda x: x.upvotes, reverse=True)
        return CommentList(new_comments, error=None)

    # 4. Check 6-hour cache for real YouTube comments
    existing = db.query(Comment).filter(Comment.item_id == item.id).all()
    if existing:
        cache_age = datetime.utcnow() - max(c.created_at for c in existing)
        if cache_age < timedelta(hours=6):
            sorted_comments = sorted(existing, key=lambda x: x.upvotes, reverse=True)[:limit]
            return CommentList(sorted_comments, error=None)

    # 5. Fetch fresh real comments from YouTube Data API
    raw_comments, err_msg = _fetch_real_youtube_comment_threads(item, limit=limit)
    if err_msg or not raw_comments:
        # If fetch failed but we have stale cache, return stale cache with notice
        if existing:
            return CommentList(sorted(existing, key=lambda x: x.upvotes, reverse=True)[:limit], error=None)
        return CommentList([], error=err_msg)

    # Delete stale comments before persisting fresh ones
    try:
        db.query(Comment).filter(Comment.item_id == item.id).delete()
        new_comments = []
        for c_data in raw_comments:
            c = Comment(
                item_id=item.id,
                topic_id=item.topic_id,
                author=c_data["author"],
                author_handle=c_data["author_handle"],
                author_avatar_color=c_data["author_avatar_color"],
                platform="youtube",
                content=c_data["content"],
                upvotes=c_data["upvotes"],
                sentiment=c_data["sentiment"],
                is_generated=False,
                url=c_data.get("url"),
                published_at=c_data["published_at"],
                created_at=datetime.utcnow()
            )
            db.add(c)
            new_comments.append(c)
        db.commit()
        return CommentList(new_comments, error=None)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist real YouTube comments for item {item.id}: {e}")
        return CommentList([], error="Failed to store comments.")


def get_or_create_topic_comments(db: Session, topic: Topic, limit: int = 8) -> CommentList:
    """
    Retrieve comments for a Macro Topic:
    - Collects authentic YouTube comments from member items.
    - Never invents topic comments if ENABLE_SAMPLE_COMMENTS is False.
    """
    # 1. Prune expired comments
    purge_expired_comments(db, max_age_days=7)

    # 2. Check existing topic comments
    existing = db.query(Comment).filter(Comment.topic_id == topic.id).order_by(Comment.upvotes.desc()).limit(limit).all()
    if existing:
        return CommentList(existing, error=None)

    # 3. Collect from member YouTube items
    member_items = topic.items or []
    collected_comments: List[Comment] = []

    for m in member_items:
        if m.source and m.source.slug == "youtube":
            m_comments = get_or_create_item_comments(db, m, limit=2)
            for mc in m_comments:
                if mc not in collected_comments:
                    collected_comments.append(mc)

    if collected_comments:
        for c in collected_comments:
            if not c.topic_id:
                c.topic_id = topic.id
        try:
            db.commit()
        except Exception:
            db.rollback()
        return CommentList(collected_comments[:limit], error=None)

    # 4. If no real comments from member stories:
    # If ENABLE_SAMPLE_COMMENTS is False, return empty (no invented comments)
    if not settings.ENABLE_SAMPLE_COMMENTS:
        return CommentList([], error=None)

    # Fallback to generated cross-platform sample reactions when sample comments are explicitly enabled
    title = topic.title or "Cross-Platform Macro Story"
    keywords = _extract_keywords(title)
    kw = keywords[0] if keywords else "this event"

    multi_platform_reactions = [
        {
            "author": "Tech Pulse India", "author_handle": "TechPulseIN", "author_avatar_color": "#3b82f6",
            "platform": "youtube", "content": f"The video breakdowns coming out on {kw} show remarkable detail. Definitely the biggest story of the day.",
            "upvotes": 1840, "sentiment": "excited", "published_at": datetime.utcnow() - timedelta(minutes=40)
        },
        {
            "author": "Reddit Discussions", "author_handle": "u/macro_analyst", "author_avatar_color": "#f97316",
            "platform": "reddit", "content": f"The multi-source convergence on this is telling. Notice how both technical subreddits and mainstream outlets are confirming the same timeline.",
            "upvotes": 2490, "sentiment": "positive", "published_at": datetime.utcnow() - timedelta(minutes=75)
        },
        {
            "author": "Maya Chen", "author_handle": "mayachen.bsky.social", "author_avatar_color": "#06b6d4",
            "platform": "bluesky", "content": f"Fascinating to see how fast discussions around {kw} propagated from developer channels into public news.",
            "upvotes": 620, "sentiment": "curious", "published_at": datetime.utcnow() - timedelta(minutes=110)
        },
        {
            "author": "Sanjay Verma", "author_handle": "@sanjay_dispatch", "author_avatar_color": "#8b7cf6",
            "platform": "twitter", "content": f"Key question now is whether the initial momentum behind {kw} holds up once official press statements are released tomorrow.",
            "upvotes": 890, "sentiment": "critical", "published_at": datetime.utcnow() - timedelta(minutes=150)
        },
        {
            "author": "Open News Guild", "author_handle": "@openguild@mastodon.social", "author_avatar_color": "#10b981",
            "platform": "mastodon", "content": f"Independent analysis corroborates the early reports. Solid documentation across all reporting outlets.",
            "upvotes": 430, "sentiment": "positive", "published_at": datetime.utcnow() - timedelta(minutes=180)
        },
    ]

    new_topic_comments = []
    for r in multi_platform_reactions:
        c = Comment(
            topic_id=topic.id,
            author=r["author"],
            author_handle=r["author_handle"],
            author_avatar_color=r["author_avatar_color"],
            platform=r["platform"],
            content=r["content"],
            upvotes=r["upvotes"],
            sentiment=r["sentiment"],
            is_generated=True,
            published_at=r["published_at"],
            created_at=datetime.utcnow()
        )
        db.add(c)
        new_topic_comments.append(c)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist topic comments: {e}")
        return CommentList([], error=None)

    new_topic_comments.sort(key=lambda x: x.upvotes, reverse=True)
    return CommentList(new_topic_comments, error=None)

    new_topic_comments.sort(key=lambda x: x.upvotes, reverse=True)
    return new_topic_comments, None


def calculate_sentiment_breakdown(comments: List[Comment]) -> Dict[str, int]:
    """Compute counts of each sentiment classification across comments."""
    breakdown = {"positive": 0, "neutral": 0, "critical": 0, "curious": 0, "excited": 0}
    for c in comments:
        s = (c.sentiment or "neutral").lower()
        if s in breakdown:
            breakdown[s] += 1
        else:
            breakdown["neutral"] += 1
    return breakdown


def format_comments_response(comments: List[Comment], error: Optional[str] = None) -> CommentListResponse:
    """Format SQLAlchemy Comment models into a CommentListResponse schema."""
    breakdown = calculate_sentiment_breakdown(comments)
    is_generated = any(getattr(c, "is_generated", False) for c in comments) if comments else False
    comment_responses = [
        CommentResponse(
            id=c.id,
            item_id=c.item_id,
            topic_id=c.topic_id,
            author=c.author,
            author_handle=c.author_handle,
            author_avatar_color=c.author_avatar_color or "#3b82f6",
            platform=c.platform,
            content=c.content,
            upvotes=c.upvotes or 0,
            sentiment=c.sentiment or "neutral",
            is_generated=getattr(c, "is_generated", False),
            url=getattr(c, "url", None),
            published_at=c.published_at,
            created_at=c.created_at
        )
        for c in comments
    ]
    return CommentListResponse(
        total=len(comment_responses),
        is_generated=is_generated,
        error=error,
        message=error,
        sentiment_breakdown=breakdown,
        comments=comment_responses
    )
