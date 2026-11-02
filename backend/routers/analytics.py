"""
backend/routers/analytics.py

Analytics overview endpoints providing SQL-aggregated metrics:
- Category distribution
- Platform volume share (item counts only, without raw engagement comparison)
- Provenance ratio (Category A Official APIs vs Category B Derived Signals)
- Top detected Indian geographic locations
- 24-hour hourly ingestion timeline (zero-filled for continuity)
- AI processing pipeline coverage stats
"""
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from backend.database import get_db, is_sqlite
from backend.models import TrendingItem, Source, Category, FetchLog
from backend.schemas import (
    AnalyticsOverviewResponse,
    CategoryBreakdownItem,
    PlatformShareItem,
    TopLocationItem,
    HourlyVolumeItem,
    AICoverageStats,
    AnalyticsTotals,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

CHART_SOURCES = ["youtube", "google_trends", "mastodon", "bluesky"]


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    recency: Literal["6h", "12h", "24h", "3d", "7d", "30d", "all"] = Query(
        "24h",
        description="Recency window for analysis (6h, 12h, 24h, 3d, 7d, 30d, or all)"
    ),
    db: Session = Depends(get_db)
):
    """
    Returns SQL-aggregated metrics for the analytics dashboard using GROUP BY queries.
    Applies identical recency semantics to /trends:
    - Chart-style sources (youtube, google_trends, mastodon, bluesky) filter by fetched_at.
    - News coverage sources filter by COALESCE(published_at, fetched_at).
    """
    now = datetime.utcnow()
    window_deltas = {
        "6h": timedelta(hours=6),
        "12h": timedelta(hours=12),
        "24h": timedelta(hours=24),
        "3d": timedelta(days=3),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }

    # Recency effective timestamp expression
    effective_time = case(
        (Source.slug.in_(CHART_SOURCES), TrendingItem.fetched_at),
        else_=func.coalesce(TrendingItem.published_at, TrendingItem.fetched_at)
    )

    # Base filter criteria
    filters = []
    if recency in window_deltas:
        cutoff = now - window_deltas[recency]
        filters.append(effective_time >= cutoff)

    # 1. Category breakdown
    cat_query = (
        db.query(
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.coalesce(Category.color, "#6B7280").label("color"),
            func.count(TrendingItem.id).label("count")
        )
        .select_from(TrendingItem)
        .join(Source, TrendingItem.source_id == Source.id)
        .outerjoin(Category, TrendingItem.category_id == Category.id)
    )
    if filters:
        cat_query = cat_query.filter(*filters)
    cat_rows = (
        cat_query.group_by(Category.name, Category.color)
        .order_by(func.count(TrendingItem.id).desc())
        .all()
    )
    category_breakdown = [
        CategoryBreakdownItem(name=row.name, color=row.color, count=row.count)
        for row in cat_rows
    ]

    # 2. Platform share (Item count ONLY — no false cross-platform engagement comparison)
    plat_query = (
        db.query(
            Source.slug,
            Source.display_name,
            Source.source_category,
            func.count(TrendingItem.id).label("item_count")
        )
        .select_from(TrendingItem)
        .join(Source, TrendingItem.source_id == Source.id)
    )
    if filters:
        plat_query = plat_query.filter(*filters)
    plat_rows = (
        plat_query.group_by(Source.slug, Source.display_name, Source.source_category)
        .order_by(func.count(TrendingItem.id).desc())
        .all()
    )
    platform_share = [
        PlatformShareItem(
            slug=r.slug,
            display_name=r.display_name,
            source_category=r.source_category,
            item_count=r.item_count
        )
        for r in plat_rows
    ]

    # 3. Source Category Ratio (Category A vs Category B)
    ratio_query = (
        db.query(
            TrendingItem.source_category,
            func.count(TrendingItem.id).label("count")
        )
        .select_from(TrendingItem)
        .join(Source, TrendingItem.source_id == Source.id)
    )
    if filters:
        ratio_query = ratio_query.filter(*filters)
    ratio_rows = ratio_query.group_by(TrendingItem.source_category).all()
    ratio_dict = {"A": 0, "B": 0}
    for r in ratio_rows:
        if r.source_category in ratio_dict:
            ratio_dict[r.source_category] = r.count

    # 4. Top Locations (filtered to non-empty, top 10)
    loc_query = (
        db.query(
            TrendingItem.location_india.label("loc"),
            func.count(TrendingItem.id).label("count")
        )
        .select_from(TrendingItem)
        .join(Source, TrendingItem.source_id == Source.id)
        .filter(TrendingItem.location_india.isnot(None), TrendingItem.location_india != "")
    )
    if filters:
        loc_query = loc_query.filter(*filters)
    loc_rows = (
        loc_query.group_by(TrendingItem.location_india)
        .order_by(func.count(TrendingItem.id).desc())
        .limit(10)
        .all()
    )
    top_locations = [TopLocationItem(location=r.loc, count=r.count) for r in loc_rows]

    # 5. Hourly volume for the last 24h based on effective_time (matching recency filter)
    start_24h = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    if is_sqlite:
        hour_format = func.strftime("%Y-%m-%d %H:00", effective_time)
    else:
        hour_format = func.to_char(effective_time, "YYYY-MM-DD HH24:00")

    hour_query = (
        db.query(
            hour_format.label("hour_key"),
            func.count(TrendingItem.id).label("count")
        )
        .select_from(TrendingItem)
        .join(Source, TrendingItem.source_id == Source.id)
        .filter(effective_time >= start_24h)
        .group_by(hour_format)
        .all()
    )
    hour_counts = {r.hour_key: r.count for r in hour_query if r.hour_key}

    hourly_volume: list[HourlyVolumeItem] = []
    for i in range(24):
        slot_dt = start_24h + timedelta(hours=i)
        slot_key = slot_dt.strftime("%Y-%m-%d %H:00")
        label = slot_dt.strftime("%H:00")
        hourly_volume.append(HourlyVolumeItem(hour=label, count=hour_counts.get(slot_key, 0)))

    # 6. AI Coverage
    ai_query = (
        db.query(
            TrendingItem.ai_processed,
            func.count(TrendingItem.id).label("count")
        )
        .select_from(TrendingItem)
        .join(Source, TrendingItem.source_id == Source.id)
    )
    if filters:
        ai_query = ai_query.filter(*filters)
    ai_rows = ai_query.group_by(TrendingItem.ai_processed).all()
    processed_count = 0
    pending_count = 0
    for r in ai_rows:
        if r.ai_processed:
            processed_count += r.count
        else:
            pending_count += r.count
    ai_total = processed_count + pending_count
    ai_percent = round((processed_count / ai_total) * 100, 1) if ai_total > 0 else 0.0
    ai_coverage = AICoverageStats(
        processed=processed_count,
        pending=pending_count,
        percent=ai_percent
    )

    # 7. Totals
    total_items = ai_total
    active_sources = len(plat_rows)
    last_log_time = db.query(func.max(FetchLog.completed_at)).scalar()
    if not last_log_time:
        last_log_time = db.query(func.max(FetchLog.started_at)).scalar()

    totals = AnalyticsTotals(
        total_items=total_items,
        active_sources=active_sources,
        last_pipeline_run_time=last_log_time
    )

    return AnalyticsOverviewResponse(
        category_breakdown=category_breakdown,
        platform_share=platform_share,
        source_category_ratio=ratio_dict,
        top_locations=top_locations,
        hourly_volume=hourly_volume,
        ai_coverage=ai_coverage,
        totals=totals,
        recency=recency
    )
