"""
test_comments.py

Comprehensive test suite verifying:
1. Comment database model creation, columns, and foreign key relationships.
2. comments_service item comment generation, persistence, and sentiment breakdown.
3. Category A support for YouTube, Mastodon, and Bluesky.
4. comments_service macro topic cross-platform comment aggregation.
5. Router endpoint handlers:
   - get_item_comments(item_id, limit, db)
   - get_topic_comments(topic_id, limit, db)
6. 404 HTTPException handling for non-existent items and topics.
7. Verification that non-supported platforms (e.g. Reddit) return 0 comments.
"""
import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Source, Category, TrendingItem, Topic, Comment
from backend.services.comments_service import (
    get_or_create_item_comments, get_or_create_topic_comments,
    calculate_sentiment_breakdown, format_comments_response
)
from backend.routers.trends import get_item_comments
from backend.routers.topics import get_topic_comments


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for test isolation."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed test sources and categories
    src_yt = Source(
        slug="youtube", display_name="YouTube",
        source_category="A", source_type_label="Official API",
        fetch_interval_min=15, is_enabled=True
    )
    src_mastodon = Source(
        slug="mastodon", display_name="Mastodon",
        source_category="A", source_type_label="Official API",
        fetch_interval_min=15, is_enabled=True
    )
    src_bluesky = Source(
        slug="bluesky", display_name="Bluesky",
        source_category="A", source_type_label="Official API",
        fetch_interval_min=15, is_enabled=True
    )
    src_reddit = Source(
        slug="reddit", display_name="Reddit",
        source_category="A", source_type_label="Official API",
        fetch_interval_min=15, is_enabled=True
    )
    cat_tech = Category(name="Technology", color="#3b82f6")

    session.add_all([src_yt, src_mastodon, src_bluesky, src_reddit, cat_tech])
    session.commit()

    # Seed test item (YouTube)
    item = TrendingItem(
        source_id=src_yt.id,
        category_id=cat_tech.id,
        external_id="test_vid_123",
        title="ISRO Space Telescope Next Milestone Mission",
        description="Comprehensive mission briefing detailing the orbital insertion.",
        url="https://youtube.com/watch?v=test_vid_123",
        source_category="A",
        fetched_at=datetime.utcnow()
    )
    session.add(item)
    session.commit()

    # Seed test topic
    topic = Topic(
        title="Breakthrough in Quantum Computing Architecture",
        summary="Multiple platforms report substantial leaps in coherence times.",
        source_count=3,
        item_count=5,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(topic)
    session.commit()

    yield session
    session.close()


def test_comment_model_and_item_generation(db_session):
    item = db_session.query(TrendingItem).first()
    assert item is not None

    # Initially zero comments
    assert len(item.comments) == 0

    comments = get_or_create_item_comments(db_session, item, limit=5)
    assert len(comments) == 5

    for c in comments:
        assert c.item_id == item.id
        assert c.author is not None
        assert c.author_handle is not None
        assert c.platform == "youtube"
        assert c.upvotes >= 0
        assert c.sentiment in ["positive", "neutral", "critical", "curious", "excited"]

    # Verify persistence: second call returns the same persisted comments
    second_call = get_or_create_item_comments(db_session, item, limit=5)
    assert len(second_call) == 5
    assert [c.id for c in second_call] == [c.id for c in comments]


def test_mastodon_item_comments(db_session):
    src_masto = db_session.query(Source).filter(Source.slug == "mastodon").first()
    cat = db_session.query(Category).first()

    item_masto = TrendingItem(
        source_id=src_masto.id,
        category_id=cat.id,
        external_id="tag_technology",
        title="#Technology",
        description="Trending technology discussions across federated servers.",
        url="https://mastodon.social/tags/technology",
        source_category="A",
        fetched_at=datetime.utcnow()
    )
    db_session.add(item_masto)
    db_session.commit()

    comments = get_or_create_item_comments(db_session, item_masto, limit=5)
    assert len(comments) > 0
    assert len(comments) <= 5
    for c in comments:
        assert c.item_id == item_masto.id
        assert c.platform == "mastodon"
        assert c.author
        assert c.content

    resp = get_item_comments(item_id=item_masto.id, db=db_session)
    assert resp.total == len(comments)
    assert len(resp.comments) == len(comments)


def test_bluesky_item_comments(db_session):
    src_bsky = db_session.query(Source).filter(Source.slug == "bluesky").first()
    cat = db_session.query(Category).first()

    item_bsky = TrendingItem(
        source_id=src_bsky.id,
        category_id=cat.id,
        external_id="bsky_artificial_intelligence",
        title="Artificial Intelligence",
        description="Trending conversations about AI breakthroughs.",
        url="https://bsky.app/search?q=Artificial%20Intelligence",
        source_category="A",
        fetched_at=datetime.utcnow()
    )
    db_session.add(item_bsky)
    db_session.commit()

    comments = get_or_create_item_comments(db_session, item_bsky, limit=5)
    assert len(comments) > 0
    assert len(comments) <= 5
    for c in comments:
        assert c.item_id == item_bsky.id
        assert c.platform == "bluesky"
        assert c.author
        assert c.content

    resp = get_item_comments(item_id=item_bsky.id, db=db_session)
    assert resp.total == len(comments)
    assert len(resp.comments) == len(comments)


def test_topic_comment_generation(db_session):
    topic = db_session.query(Topic).first()
    assert topic is not None

    comments = get_or_create_topic_comments(db_session, topic, limit=5)
    assert len(comments) >= 4

    platforms = {c.platform for c in comments}
    # Should include multiple social platforms
    assert len(platforms) >= 2

    # Verify sentiment breakdown
    breakdown = calculate_sentiment_breakdown(comments)
    total_sentiment = sum(breakdown.values())
    assert total_sentiment == len(comments)

    formatted = format_comments_response(comments)
    assert formatted.total == len(comments)
    assert len(formatted.comments) == len(comments)


def test_router_item_comments_endpoint(db_session):
    item = db_session.query(TrendingItem).first()
    assert item is not None

    response = get_item_comments(item_id=item.id, limit=6, db=db_session)
    assert response.total > 0
    assert len(response.comments) == response.total
    assert response.total <= 6

    first_c = response.comments[0]
    assert first_c.item_id == item.id
    assert first_c.author
    assert first_c.author_handle
    assert first_c.platform
    assert first_c.content
    assert first_c.sentiment in ["positive", "neutral", "critical", "curious", "excited"]

    # Check sentiment breakdown is populated
    assert isinstance(response.sentiment_breakdown, dict)
    total_in_breakdown = sum(response.sentiment_breakdown.values())
    assert total_in_breakdown == response.total


def test_router_topic_comments_endpoint(db_session):
    topic = db_session.query(Topic).first()
    assert topic is not None

    response = get_topic_comments(topic_id=topic.id, limit=8, db=db_session)
    assert response.total >= 4
    assert len(response.comments) == response.total

    # Verify cross-platform source diversity in topic comments
    platforms = {c.platform for c in response.comments}
    assert len(platforms) >= 2


def test_comments_404_handling(db_session):
    # Non-existent item
    with pytest.raises(HTTPException) as exc_info_item:
        get_item_comments(item_id=999999, limit=6, db=db_session)
    assert exc_info_item.value.status_code == 404
    assert "not found" in exc_info_item.value.detail.lower()

    # Non-existent topic
    with pytest.raises(HTTPException) as exc_info_topic:
        get_topic_comments(topic_id=999999, limit=8, db=db_session)
    assert exc_info_topic.value.status_code == 404
    assert "not found" in exc_info_topic.value.detail.lower()


def test_top_10_comments_retrieval(db_session):
    src_yt = db_session.query(Source).filter(Source.slug == 'youtube').first()
    item2 = TrendingItem(
        source_id=src_yt.id,
        external_id='yt_top10_test',
        title='Breaking News: Indian Space Program Expansion',
        description='Major developments announced.',
        url='https://youtube.com/watch?v=yt_top10_test',
        source_category='A',
        fetched_at=datetime.utcnow()
    )
    db_session.add(item2)
    db_session.commit()

    # Default call without explicit limit should return top 10 comments
    response = get_item_comments(item_id=item2.id, db=db_session)
    assert response.total == 10
    assert len(response.comments) == 10


def test_non_category_a_item_returns_zero_comments(db_session):
    src_reddit = db_session.query(Source).filter(Source.slug == 'reddit').first()
    item_reddit = TrendingItem(
        source_id=src_reddit.id,
        external_id='reddit_test_item',
        title='Discussion on tech trends',
        description='Tech commentary',
        url='https://reddit.com/r/technology',
        source_category='A',
        fetched_at=datetime.utcnow()
    )
    db_session.add(item_reddit)
    db_session.commit()

    # Comments are restricted to Category A social platforms: YouTube, Mastodon, and Bluesky
    raw_comments = get_or_create_item_comments(db_session, item_reddit, limit=10)
    assert len(raw_comments) == 0

    response = get_item_comments(item_id=item_reddit.id, db=db_session)
    assert response.total == 0
    assert len(response.comments) == 0
