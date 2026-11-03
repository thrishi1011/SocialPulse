"""
backend/routers/topics.py

Macro Topics (Cross-Platform Stories) endpoints:
- List aggregated cross-platform topics with source convergence metrics
- Inspect full story details with all member items across disparate sources
"""
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc

from backend.database import get_db
from backend.models import Topic, TrendingItem, Source
from backend.schemas import (
    TopicListResponse, TopicListItemResponse, TopicDetailResponse, CommentListResponse
)
from backend.routers.trends import format_trend_item
from backend.services.comments_service import get_or_create_topic_comments, format_comments_response

router = APIRouter(prefix="/api/v1/topics", tags=["topics"])


@router.get("", response_model=TopicListResponse)
def list_topics(
    min_sources: int = Query(2, ge=1, description="Minimum distinct sources required (default 2 for cross-platform convergence)"),
    recency: Literal["6h", "12h", "24h", "all"] = Query("24h", description="Recency window for topic updates"),
    db: Session = Depends(get_db)
):
    """
    Retrieve macro stories grouped across platforms.
    By default filters to stories appearing on at least 2 distinct sources (source_count >= 2).
    """
    query = (
        db.query(Topic)
        .options(joinedload(Topic.items).joinedload(TrendingItem.source))
        .filter(Topic.is_active == True)
        .filter(Topic.source_count >= min_sources)
    )

    now = datetime.utcnow()
    hours_map = {"6h": 6, "12h": 12, "24h": 24}
    if recency in hours_map:
        cutoff = now - timedelta(hours=hours_map[recency])
        query = query.filter(Topic.updated_at >= cutoff)

    topics = query.order_by(Topic.source_count.desc(), Topic.item_count.desc()).all()

    items_res = []
    for t in topics:
        source_names = list({
            item.source.display_name for item in t.items
            if item.source and item.source.display_name
        })
        items_res.append(
            TopicListItemResponse(
                id=t.id,
                title=t.title,
                summary=t.summary,
                source_count=t.source_count,
                item_count=t.item_count,
                sources=source_names,
                is_active=t.is_active,
                created_at=t.created_at,
                updated_at=t.updated_at
            )
        )

    return TopicListResponse(
        total_topics=len(items_res),
        topics=items_res
    )


@router.get("/{topic_id}", response_model=TopicDetailResponse)
def get_topic_detail(topic_id: int, db: Session = Depends(get_db)):
    """
    Retrieve full details for a topic, including all underlying multi-platform trending items.
    """
    if hasattr(limit, "default"):
        limit = limit.default
    elif not isinstance(limit, int):
        try:
            limit = int(limit)
        except Exception:
            limit = 8

    topic = (
        db.query(Topic)
        .options(
            joinedload(Topic.items).joinedload(TrendingItem.source),
            joinedload(Topic.items).joinedload(TrendingItem.category)
        )
        .filter(Topic.id == topic_id)
        .first()
    )

    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic with ID {topic_id} not found.")

    source_names = list({
        item.source.display_name for item in topic.items
        if item.source and item.source.display_name
    })

    formatted_items = [format_trend_item(item) for item in topic.items]

    return TopicDetailResponse(
        id=topic.id,
        title=topic.title,
        summary=topic.summary,
        source_count=topic.source_count,
        item_count=topic.item_count,
        sources=source_names,
        is_active=topic.is_active,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
        items=formatted_items
    )


@router.get("/{topic_id}/comments", response_model=CommentListResponse)
def get_topic_comments(
    topic_id: int,
    limit: int = Query(8, ge=1, le=25, description="Max comments to retrieve"),
    db: Session = Depends(get_db)
):
    """
    Retrieve sourced community comments and cross-platform reactions for a macro story topic.
    """
    if hasattr(limit, "default"):
        limit = limit.default
    elif not isinstance(limit, int):
        try:
            limit = int(limit)
        except Exception:
            limit = 8

    topic = (
        db.query(Topic)
        .options(
            joinedload(Topic.items).joinedload(TrendingItem.source),
            joinedload(Topic.items).joinedload(TrendingItem.category)
        )
        .filter(Topic.id == topic_id)
        .first()
    )

    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic with ID {topic_id} not found.")

    comments = get_or_create_topic_comments(db, topic, limit=limit)
    return format_comments_response(comments)

