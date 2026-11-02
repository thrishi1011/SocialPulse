from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from backend.database import get_db
from backend.models import Source, FetchLog, TrendingItem
from backend.schemas import (
    SourceListResponse, SourceResponse, SourceStatusResponse, LastFetchInfo,
    SourceHealthResponse, SourceHealthItem, SourceLastFetchDetail,
    SourceLogsResponse, FetchLogItemResponse
)

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])

@router.get("", response_model=SourceListResponse)
def list_sources(db: Session = Depends(get_db)):
    """Retrieve all available data sources with their category, enablement status, and item counts."""
    sources = db.query(Source).order_by(Source.source_category.asc(), Source.id.asc()).all()
    # Compute per-source item counts
    counts = dict(db.query(TrendingItem.source_id, func.count(TrendingItem.id)).group_by(TrendingItem.source_id).all())
    result_sources = []
    for s in sources:
        sr = SourceResponse.model_validate(s)
        sr.item_count = counts.get(s.id, 0)
        result_sources.append(sr)

    return SourceListResponse(
        total_sources=len(sources),
        sources=result_sources
    )

@router.get("/health", response_model=SourceHealthResponse)
def get_sources_health(db: Session = Depends(get_db)):
    """
    Source Health Observatory: computes operational telemetry, 24-hour success rates,
    average latency, and derived health states for all ingestion sources.
    Must be defined before /{slug} to avoid route collision.
    """
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    sources = db.query(Source).order_by(Source.source_category.asc(), Source.id.asc()).all()

    health_items: list[SourceHealthItem] = []
    healthy_cnt = 0
    degraded_cnt = 0
    error_cnt = 0

    for src in sources:
        # Latest fetch log
        latest_log = (
            db.query(FetchLog)
            .filter(FetchLog.source_id == src.id)
            .order_by(FetchLog.started_at.desc())
            .first()
        )

        # 24h logs aggregate
        logs_24h = (
            db.query(FetchLog)
            .filter(FetchLog.source_id == src.id, FetchLog.started_at >= cutoff_24h)
            .all()
        )
        total_logs_24h = len(logs_24h)
        successful_logs_24h = sum(1 for l in logs_24h if l.status == "success")
        success_rate_24h = (
            round((successful_logs_24h / total_logs_24h) * 100.0, 1)
            if total_logs_24h > 0
            else 100.0
        )
        avg_dur_24h = (
            int(sum(l.duration_ms for l in logs_24h) / total_logs_24h)
            if total_logs_24h > 0
            else 0
        )

        # Items in last 24h
        items_24h = (
            db.query(TrendingItem)
            .filter(TrendingItem.source_id == src.id, TrendingItem.fetched_at >= cutoff_24h)
            .count()
        )

        last_fetch_detail = None
        if latest_log:
            last_fetch_detail = SourceLastFetchDetail(
                status=latest_log.status,
                started_at=latest_log.started_at,
                completed_at=latest_log.completed_at,
                duration_ms=latest_log.duration_ms,
                items_fetched=latest_log.items_fetched,
                items_new=latest_log.items_new,
                error_message=latest_log.error_message
            )

        # Derived health state computation
        health_state: str
        if not src.is_enabled:
            health_state = "disabled"
        elif not latest_log:
            health_state = "never_run"
        elif latest_log.status == "error":
            health_state = "error"
            error_cnt += 1
        elif (
            latest_log.status in ("fallback_mock", "mock_fallback")
            or (total_logs_24h > 0 and success_rate_24h < 80.0)
        ):
            health_state = "degraded"
            degraded_cnt += 1
        else:
            # Check staleness threshold (2x fetch interval)
            ref_time = latest_log.completed_at or latest_log.started_at
            stale_threshold = timedelta(minutes=2 * src.fetch_interval_min)
            if (now - ref_time) > stale_threshold:
                health_state = "stale"
            else:
                health_state = "healthy"
                healthy_cnt += 1

        health_items.append(
            SourceHealthItem(
                slug=src.slug,
                display_name=src.display_name,
                source_category=src.source_category,
                is_enabled=src.is_enabled,
                fetch_interval_min=src.fetch_interval_min,
                last_fetch=last_fetch_detail,
                success_rate_24h=success_rate_24h,
                avg_duration_ms_24h=avg_dur_24h,
                items_24h=items_24h,
                health_state=health_state
            )
        )

    return SourceHealthResponse(
        sources=health_items,
        total_sources=len(sources),
        healthy_count=healthy_cnt,
        degraded_count=degraded_cnt,
        error_count=error_cnt
    )

@router.get("/{slug}/logs", response_model=SourceLogsResponse)
def get_source_logs(
    slug: str,
    limit: int = Query(20, ge=1, le=100, description="Number of recent fetch logs to return"),
    db: Session = Depends(get_db)
):
    """Retrieve recent fetch logs for a source to inspect execution history and errors."""
    source = db.query(Source).filter(Source.slug == slug).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source with slug '{slug}' not found.")

    logs = (
        db.query(FetchLog)
        .filter(FetchLog.source_id == source.id)
        .order_by(FetchLog.started_at.desc())
        .limit(limit)
        .all()
    )

    return SourceLogsResponse(
        source_slug=source.slug,
        logs=[FetchLogItemResponse.model_validate(l) for l in logs]
    )

@router.get("/{slug}/status", response_model=SourceStatusResponse)
def get_source_status(slug: str, db: Session = Depends(get_db)):
    """Retrieve detailed operational status, latest fetch log, and 24-hour item volume for a source."""
    source = db.query(Source).filter(Source.slug == slug).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source with slug '{slug}' not found.")

    # Get latest fetch log
    latest_log = db.query(FetchLog).filter(
        FetchLog.source_id == source.id
    ).order_by(FetchLog.started_at.desc()).first()

    last_fetch = None
    if latest_log:
        last_fetch = LastFetchInfo(
            status=latest_log.status,
            items_fetched=latest_log.items_fetched,
            items_new=latest_log.items_new,
            duration_ms=latest_log.duration_ms,
            completed_at=latest_log.completed_at,
            error_message=latest_log.error_message
        )

    # Calculate items in past 24 hours
    cutoff = datetime.utcnow() - timedelta(hours=24)
    total_24h = db.query(TrendingItem).filter(
        TrendingItem.source_id == source.id,
        TrendingItem.fetched_at >= cutoff
    ).count()

    return SourceStatusResponse(
        id=source.id,
        slug=source.slug,
        display_name=source.display_name,
        source_category=source.source_category,
        source_type_label=source.source_type_label,
        icon_filename=source.icon_filename,
        is_enabled=source.is_enabled,
        fetch_interval_min=source.fetch_interval_min,
        last_fetch=last_fetch,
        total_items_24h=total_24h
    )
