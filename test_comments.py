"""
test_comments.py

Comprehensive test suite verifying:
1. Comment database model creation, columns, and foreign key relationships.
2. comments_service item comment generation, persistence, and sentiment breakdown.
3. comments_service macro topic cross-platform comment aggregation.
4. Router endpoint handlers:
   - get_item_comments(item_id, limit, db)
   - get_topic_comments(topic_id, limit, db)
5. 404 HTTPException handling for non-existent items and topics.
6. Multi-platform attribution and sentiment consistency.
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
    from backend.config import settings
    orig_yt_key = settings.YOUTUBE_API_KEY
    orig_sample = settings.ENABLE_SAMPLE_COMMENTS
    settings.YOUTUBE_API_KEY = None
    settings.ENABLE_SAMPLE_COMMENTS = True

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
    src_reddit = Source(
        slug="reddit", display_name="Reddit",
        source_category="A", source_type_label="Official API",
        fetch_interval_min=15, is_enabled=True
    )
    cat_tech = Category(name="Technology", color="#3b82f6")

    session.add_all([src_yt, src_reddit, cat_tech])
    session.commit()

    # Seed test item
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

    try:
        yield session
    finally:
        settings.YOUTUBE_API_KEY = orig_yt_key
        settings.ENABLE_SAMPLE_COMMENTS = orig_sample
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
    assert first_c.is_generated is True
    assert response.is_generated is True

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


def test_sample_comments_disabled_by_config(db_session):
    from backend.config import settings
    settings.ENABLE_SAMPLE_COMMENTS = False

    item = db_session.query(TrendingItem).first()
    assert item is not None

    comments = get_or_create_item_comments(db_session, item, limit=5)
    assert len(comments) == 0

    topic = db_session.query(Topic).first()
    assert topic is not None
    topic_comments = get_or_create_topic_comments(db_session, topic, limit=5)
    assert len(topic_comments) == 0
