import math
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_, and_

from backend.database import get_db
from backend.models import TrendingItem, Source, Category, TrendSnapshot
from backend.schemas import (
    TrendListResponse, TrendItemResponse, EngagementMetric,
    FilterMetadata, CategoryResponse, SourceResponse, TrendRegion,
    TrendHistoryResponse, TrendSnapshotPoint, CommentListResponse
)
from backend.services.momentum import batch_calculate_momentum
from backend.services.comments_service import get_or_create_item_comments, format_comments_response

router = APIRouter(prefix="/api/v1/trends", tags=["trends"])

def resolve_trending_region(item: TrendingItem) -> TrendRegion:
    """
    Resolve trending region with an honest fallback chain:
    1. If location_india is set and not "India" -> label=that value, scope="local", basis="Location detected from the story content".
    2. If location_india == "India" -> label="India", scope="country", basis="Nationwide Indian story".
    3. If the source is queried with an India filter (google_trends, youtube) -> label="India", scope="country", basis="This source is queried for India (geo/region = IN)".
    4. Otherwise -> label="Global", scope="global", basis="No regional filter available for this source".
    """
    loc = (item.location_india or "").strip()
    slug = item.source.slug if item.source else ""

    if loc and loc.lower() != "india":
        return TrendRegion(
            label=loc,
            scope="local",
            basis="Location detected from the story content"
        )

    if loc.lower() == "india":
        return TrendRegion(
            label="India",
            scope="country",
            basis="Nationwide Indian story"
        )

    if slug in ("google_trends", "youtube") or (item.region and item.region.upper() == "IN"):
        return TrendRegion(
            label="India",
            scope="country",
            basis="This source is queried for India (geo/region = IN)"
        )

    return TrendRegion(
        label="Global",
        scope="global",
        basis="No regional filter available for this source"
    )

def format_trend_item(item: TrendingItem, momentum_map: dict[int, Any] | None = None) -> TrendItemResponse:
    """Helper to convert SQLAlchemy TrendingItem model to Pydantic TrendItemResponse."""
    cat_response = None
    if item.category:
        cat_response = CategoryResponse(
            id=item.category.id,
            name=item.category.name,
            color=item.category.color,
            item_count=0
        )

    return TrendItemResponse(
        id=item.id,
        source_id=item.source_id,
        external_id=item.external_id,
        title=item.title,
        description=item.description,
        url=item.url,
        thumbnail_url=item.thumbnail_url,
        author=item.author,
        engagement=EngagementMetric(
            value=item.engagement_value,
            label=item.engagement_label
        ),
        secondary_engagement=EngagementMetric(
            value=item.secondary_value,
            label=item.secondary_label
        ) if item.secondary_value is not None else None,
        rank=item.rank,
        region=item.region or "global",
        trending_region=resolve_trending_region(item),
        source_category=item.source_category,
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        category=cat_response,
        ai_summary=item.ai_summary,
        location_india=item.location_india,
        ai_processed=item.ai_processed,
        raw_json=item.raw_json,
        topic_id=item.topic_id,
        topic_title=item.topic.title if getattr(item, "topic", None) else None,
        momentum=momentum_map.get(item.id) if momentum_map else None,
        source=SourceResponse.model_validate(item.source)
    )

@router.get("", response_model=TrendListResponse)
def get_trends(
    source: Optional[List[str]] = Query(None, description="Filter by source slug(s), e.g. ?source=youtube&source=reddit"),
    source_category: Optional[str] = Query(None, pattern="^(A|B)$", description="Filter by category type: 'A' (Direct API) or 'B' (Derived Signal)"),
    recency: str = Query("24h", pattern="^(6h|12h|24h|all)$", description="Time window based on best timestamp (6h, 12h, 24h, all)"),
    region_scope: Optional[str] = Query(None, pattern="^(all|india|global|local)$", description="Filter by regional scope: 'all', 'india', 'global', 'local'"),
    category: Optional[str] = Query(None, description="Filter by category name (e.g. Technology, Science)"),
    sort: str = Query("recency", pattern="^(recency|engagement|momentum)$", description="Sort order: recency, engagement, or momentum"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    Retrieve trending items with dynamic filtering across sources, categories, time recency, and sorting.
    """
    query = db.query(TrendingItem).join(TrendingItem.source).options(
        joinedload(TrendingItem.source),
        joinedload(TrendingItem.category)
    )

    # 1. Source filtering
    if source and not hasattr(source, "default"):
        # Handle comma-separated slugs if passed as single string
        slugs = []
        source_list = [source] if isinstance(source, str) else list(source)
        for s in source_list:
            slugs.extend([part.strip() for part in s.split(",") if part.strip()])
        if slugs:
            query = query.filter(Source.slug.in_(slugs))

    # 2. Source Category filtering ('A' vs 'B')
    if source_category:
        query = query.filter(TrendingItem.source_category == source_category.upper())

    # 3. Category filtering
    if category:
        query = query.join(TrendingItem.category).filter(func.lower(Category.name) == category.strip().lower())

    # 3b. Region Scope filtering ('india', 'global', 'local')
    if region_scope == "global":
        query = query.filter(
            (TrendingItem.location_india.is_(None) | (TrendingItem.location_india == "")) &
            (~Source.slug.in_(["google_trends", "youtube"])) &
            (TrendingItem.region != "IN")
        )
    elif region_scope == "india":
        query = query.filter(
            ((TrendingItem.location_india.isnot(None)) & (TrendingItem.location_india != "")) |
            Source.slug.in_(["google_trends", "youtube"]) |
            (TrendingItem.region == "IN")
        )
    elif region_scope == "local":
        query = query.filter(
            TrendingItem.location_india.isnot(None),
            TrendingItem.location_india != "",
            func.lower(TrendingItem.location_india) != "india"
        )

    # 4. Recency filtering
    # Chart-style sources (current chart snapshot) base recency on fetched_at.
    # News coverage sources base recency on actual published date (coalesce with fetched_at if missing).
    from sqlalchemy import case
    chart_sources = ["youtube", "google_trends", "mastodon", "bluesky"]
    effective_time = case(
        (Source.slug.in_(chart_sources), TrendingItem.fetched_at),
        else_=func.coalesce(TrendingItem.published_at, TrendingItem.fetched_at)
    )

    now = datetime.utcnow()
    hours_map = {"6h": 6, "12h": 12, "24h": 24}
    if recency in hours_map:
        cutoff = now - timedelta(hours=hours_map[recency])
        recent_query = query.filter(effective_time >= cutoff)
        # If recency filter yields 0 items, relax cutoff so stored news is always preserved and displayed
        if recent_query.count() == 0:
            pass
        else:
            query = recent_query

    # 5. Sorting & Pagination
    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))
    offset = (page - 1) * per_page

    if sort == "momentum":
        # For momentum sort: calculate momentum across candidate items and order by relative growth then rank delta
        candidates = query.limit(300).all()
        mom_map = batch_calculate_momentum(db, candidates)
        def momentum_sort_key(it):
            m = mom_map.get(it.id)
            growth = m.growth_per_hour if (m and m.growth_per_hour is not None) else -999.0
            r_delta = m.rank_delta if (m and m.rank_delta is not None) else -999
            return (growth, r_delta, it.engagement_value or 0)

        sorted_candidates = sorted(candidates, key=momentum_sort_key, reverse=True)
        items = sorted_candidates[offset : offset + per_page]
        momentum_map = batch_calculate_momentum(db, items)
    elif sort == "engagement":
        # Engagement metric descending, nulls last
        query = query.order_by(
            TrendingItem.engagement_value.desc().nullslast(),
            effective_time.desc()
        )
        items = query.offset(offset).limit(per_page).all()
        momentum_map = batch_calculate_momentum(db, items)
    else:
        # Default: recency descending
        query = query.order_by(
            effective_time.desc(),
            TrendingItem.rank.asc().nullslast()
        )
        items = query.offset(offset).limit(per_page).all()
        momentum_map = batch_calculate_momentum(db, items)

    formatted_items = [format_trend_item(it, momentum_map=momentum_map) for it in items]

    return TrendListResponse(
        items=formatted_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        filters_applied=FilterMetadata(
            source=source,
            source_category=source_category,
            recency=recency,
            region_scope=region_scope,
            category=category,
            sort=sort
        )
    )

def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitize cell value to protect against CSV / formula injection (CWE-1236).
    Prefixes values starting with '=', '+', '-', or '@' with a single apostrophe.
    """
    if value is None:
        return ""
    val_str = str(value).replace("\r", " ").replace("\n", " ").strip()
    if val_str and val_str[0] in ("=", "+", "-", "@"):
        return f"'{val_str}"
    return val_str

@router.get("/export.csv")
def export_trends_csv(
    source: Optional[List[str]] = Query(None),
    source_category: Optional[str] = Query(None, pattern="^(A|B)$"),
    recency: str = Query("24h", pattern="^(6h|12h|24h|all)$"),
    region_scope: Optional[str] = Query(None, pattern="^(all|india|global|local)$"),
    category: Optional[str] = Query(None),
    sort: str = Query("recency", pattern="^(recency|engagement|momentum)$"),
    db: Session = Depends(get_db)
):
    """
    Export filtered trends to CSV (capped at 5000 rows).
    Applies formula-injection sanitization to all textual columns.
    """
    from sqlalchemy import case
    query = db.query(TrendingItem).join(TrendingItem.source).options(
        joinedload(TrendingItem.source),
        joinedload(TrendingItem.category)
    )

    if source and not hasattr(source, "default"):
        slugs = []
        source_list = [source] if isinstance(source, str) else list(source)
        for s in source_list:
            slugs.extend([part.strip() for part in s.split(",") if part.strip()])
        if slugs:
            query = query.filter(Source.slug.in_(slugs))

    if source_category:
        query = query.filter(TrendingItem.source_category == source_category.upper())

    if category:
        query = query.join(TrendingItem.category).filter(func.lower(Category.name) == category.strip().lower())

    if region_scope == "global":
        query = query.filter(
            (TrendingItem.location_india.is_(None) | (TrendingItem.location_india == "")) &
            (~Source.slug.in_(["google_trends", "youtube"])) &
            (TrendingItem.region != "IN")
        )
    elif region_scope == "india":
        query = query.filter(
            ((TrendingItem.location_india.isnot(None)) & (TrendingItem.location_india != "")) |
            Source.slug.in_(["google_trends", "youtube"]) |
            (TrendingItem.region == "IN")
        )
    elif region_scope == "local":
        query = query.filter(
            TrendingItem.location_india.isnot(None),
            TrendingItem.location_india != "",
            func.lower(TrendingItem.location_india) != "india"
        )

    chart_sources = ["youtube", "google_trends", "mastodon", "bluesky"]
    effective_time = case(
        (Source.slug.in_(chart_sources), TrendingItem.fetched_at),
        else_=func.coalesce(TrendingItem.published_at, TrendingItem.fetched_at)
    )

    now = datetime.utcnow()
    hours_map = {"6h": 6, "12h": 12, "24h": 24}
    if recency in hours_map:
        cutoff = now - timedelta(hours=hours_map[recency])
        recent_query = query.filter(effective_time >= cutoff)
        if not (source and recent_query.count() == 0):
            query = recent_query

    if sort == "engagement":
        query = query.order_by(TrendingItem.engagement_value.desc().nullslast(), effective_time.desc())
    else:
        query = query.order_by(effective_time.desc(), TrendingItem.rank.asc().nullslast())

    items = query.limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    writer.writerow([
        "id", "source", "source_category", "title", "url", "author",
        "published_at", "fetched_at", "category", "location",
        "trending_region", "ai_summary", "engagement_value", "engagement_label"
    ])

    for it in items:
        reg = resolve_trending_region(it)
        writer.writerow([
            sanitize_csv_cell(it.id),
            sanitize_csv_cell(it.source.display_name if it.source else ""),
            sanitize_csv_cell(it.source_category),
            sanitize_csv_cell(it.title),
            sanitize_csv_cell(it.url),
            sanitize_csv_cell(it.author),
            sanitize_csv_cell(it.published_at.isoformat() if it.published_at else ""),
            sanitize_csv_cell(it.fetched_at.isoformat() if it.fetched_at else ""),
            sanitize_csv_cell(it.category.name if it.category else ""),
            sanitize_csv_cell(it.location_india),
            sanitize_csv_cell(reg.label if reg else ""),
            sanitize_csv_cell(it.ai_summary),
            sanitize_csv_cell(it.engagement_value),
            sanitize_csv_cell(it.engagement_label)
        ])

    csv_data = output.getvalue()
    filename = f"socialpulse_trends_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/{item_id}/history", response_model=TrendHistoryResponse)
def get_trend_history(item_id: int, db: Session = Depends(get_db)):
    """Retrieve historical snapshot metrics (rank and engagement over time) for an item."""
    item = db.query(TrendingItem).options(
        joinedload(TrendingItem.source)
    ).filter(TrendingItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail=f"Trending item with ID {item_id} not found.")

    snapshots = (
        db.query(TrendSnapshot)
        .filter(TrendSnapshot.item_id == item_id)
        .order_by(TrendSnapshot.captured_at.asc())
        .all()
    )

    return TrendHistoryResponse(
        item_id=item.id,
        title=item.title,
        source_slug=item.source.slug if item.source else "",
        total_snapshots=len(snapshots),
        snapshots=[TrendSnapshotPoint.model_validate(s) for s in snapshots]
    )

@router.get("/{item_id}", response_model=TrendItemResponse)
def get_trend_by_id(item_id: int, db: Session = Depends(get_db)):
    """Retrieve full details of a single trending item by its primary ID."""
    item = db.query(TrendingItem).options(
        joinedload(TrendingItem.source),
        joinedload(TrendingItem.category),
        joinedload(TrendingItem.topic)
    ).filter(TrendingItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail=f"Trending item with ID {item_id} not found.")

    momentum_map = batch_calculate_momentum(db, [item])
    return format_trend_item(item, momentum_map=momentum_map)


@router.get("/{item_id}/comments", response_model=CommentListResponse)
def get_item_comments(
    item_id: int,
    limit: int = Query(10, ge=1, le=20, description="Max comments to retrieve"),
    db: Session = Depends(get_db)
):
    """
    Retrieve sourced community comments and reactions for a specific trending item.
    """
    item = db.query(TrendingItem).options(
        joinedload(TrendingItem.source),
        joinedload(TrendingItem.category)
    ).filter(TrendingItem.id == item_id).first()

    if hasattr(limit, "default"):
        limit = limit.default
    elif not isinstance(limit, int):
        try:
            limit = int(limit)
        except Exception:
            limit = 10

    if not item:
        raise HTTPException(status_code=404, detail=f"Trending item with ID {item_id} not found.")

    if not item.source or item.source.slug not in ("youtube", "mastodon", "bluesky"):
        return format_comments_response([])

    comments = get_or_create_item_comments(db, item, limit=limit)
    return format_comments_response(comments)

