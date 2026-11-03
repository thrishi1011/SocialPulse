from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

# ============================================================
# Source Schemas
# ============================================================

class SourceResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    source_category: str = Field(..., description="'A' for Direct Platform API, 'B' for Derived/Journalistic Signal")
    source_type_label: str = Field(..., description="E.g. 'Official API', 'Search Interest', 'News Coverage'")
    icon_filename: str | None = None
    is_enabled: bool
    fetch_interval_min: int

    class Config:
        from_attributes = True

class LastFetchInfo(BaseModel):
    status: str
    items_fetched: int
    items_new: int
    duration_ms: int
    completed_at: datetime | None = None
    error_message: str | None = None

class SourceStatusResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    source_category: str
    source_type_label: str
    icon_filename: str | None = None
    is_enabled: bool
    fetch_interval_min: int
    last_fetch: LastFetchInfo | None = None
    total_items_24h: int = 0

    class Config:
        from_attributes = True

class SourceListResponse(BaseModel):
    total_sources: int
    sources: list[SourceResponse]


# ============================================================
# Source Health Observatory Schemas
# ============================================================

class SourceLastFetchDetail(BaseModel):
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int
    items_fetched: int
    items_new: int
    error_message: str | None = None

class SourceHealthItem(BaseModel):
    slug: str
    display_name: str
    source_category: str
    is_enabled: bool
    fetch_interval_min: int
    last_fetch: SourceLastFetchDetail | None = None
    success_rate_24h: float
    avg_duration_ms_24h: int
    items_24h: int
    health_state: str  # "healthy" | "stale" | "degraded" | "error" | "disabled" | "never_run"

class SourceHealthResponse(BaseModel):
    sources: list[SourceHealthItem]
    total_sources: int
    healthy_count: int
    degraded_count: int
    error_count: int

class FetchLogItemResponse(BaseModel):
    id: int
    source_id: int
    status: str
    items_fetched: int
    items_new: int
    error_message: str | None = None
    duration_ms: int
    started_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True

class SourceLogsResponse(BaseModel):
    source_slug: str
    logs: list[FetchLogItemResponse]


# ============================================================
# Category Schemas
# ============================================================

class CategoryResponse(BaseModel):
    id: int
    name: str
    color: str | None = None
    item_count: int = 0

    class Config:
        from_attributes = True

class CategoryListResponse(BaseModel):
    total_categories: int
    categories: list[CategoryResponse]


# ============================================================
# Engagement & Trending Item Schemas
# ============================================================

class EngagementMetric(BaseModel):
    value: int | None = None
    label: str | None = None

class TrendRegion(BaseModel):
    label: str
    scope: str  # "local" | "country" | "global"
    basis: str

class TrendMomentumInfo(BaseModel):
    state: str  # "surging", "cooling", "peaking", "steady", "new", "tracking"
    rank_delta: int | None = None
    growth_per_hour: float | None = None
    points: list[int] = []

class TrendItemResponse(BaseModel):
    id: int
    source_id: int
    external_id: str
    title: str
    description: str | None = None
    url: str
    thumbnail_url: str | None = None
    author: str | None = None
    engagement: EngagementMetric
    secondary_engagement: EngagementMetric | None = None
    rank: int | None = None
    region: str = "global"
    trending_region: TrendRegion | None = None
    source_category: str = Field(..., description="'A' = Direct API, 'B' = Derived Signal")
    published_at: datetime | None = None
    fetched_at: datetime
    category: CategoryResponse | None = None
    ai_summary: str | None = None
    location_india: str | None = None
    ai_processed: bool = False
    raw_json: str | None = None
    topic_id: int | None = None
    topic_title: str | None = None
    momentum: TrendMomentumInfo | None = None
    source: SourceResponse

    class Config:
        from_attributes = True

class FilterMetadata(BaseModel):
    source: list[str] | None = None
    source_category: str | None = None
    recency: str = "24h"
    region_scope: str | None = None
    category: str | None = None
    sort: str = "recency"

class TrendListResponse(BaseModel):
    items: list[TrendItemResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
    filters_applied: FilterMetadata


# ============================================================
# Pipeline & System Schemas
# ============================================================

class PipelineFetchSummary(BaseModel):
    source_slug: str
    status: str
    items_fetched: int
    items_new: int
    duration_ms: int
    error_message: str | None = None

class PipelineRunResponse(BaseModel):
    status: str
    message: str
    total_sources_attempted: int
    total_items_fetched: int
    total_items_new: int
    details: list[PipelineFetchSummary]

class PipelineStatusResponse(BaseModel):
    is_running: bool = False
    last_run_time: datetime | None = None
    total_items_in_db: int = 0
    total_ai_processed: int = 0
    total_ai_pending: int = 0
    mock_fetch_mode: bool = True
    mock_ai_mode: bool = True
    active_sources_count: int = 0

class AIProcessResponse(BaseModel):
    status: str
    items_processed: int
    items_succeeded: int
    items_failed: int
    mock_mode: bool

class HealthResponse(BaseModel):
    status: str
    project: str
    version: str
    mock_fetch_mode: bool
    mock_ai_mode: bool
    database_connected: bool
    sources_enabled: int


# ============================================================
# Analytics Schemas
# ============================================================

class CategoryBreakdownItem(BaseModel):
    name: str
    color: str | None = None
    count: int

class PlatformShareItem(BaseModel):
    slug: str
    display_name: str
    source_category: str
    item_count: int

class TopLocationItem(BaseModel):
    location: str
    count: int

class HourlyVolumeItem(BaseModel):
    hour: str
    count: int

class AICoverageStats(BaseModel):
    processed: int
    pending: int
    percent: float

class AnalyticsTotals(BaseModel):
    total_items: int
    active_sources: int
    last_pipeline_run_time: datetime | None = None

class AnalyticsOverviewResponse(BaseModel):
    category_breakdown: list[CategoryBreakdownItem]
    platform_share: list[PlatformShareItem]
    source_category_ratio: dict[str, int]
    top_locations: list[TopLocationItem]
    hourly_volume: list[HourlyVolumeItem]
    ai_coverage: AICoverageStats
    totals: AnalyticsTotals
    recency: str


# ============================================================
# Macro Topics (Cross-Platform Clustering) Schemas
# ============================================================

class TopicListItemResponse(BaseModel):
    id: int
    title: str
    summary: str | None = None
    source_count: int
    item_count: int
    sources: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TopicDetailResponse(BaseModel):
    id: int
    title: str
    summary: str | None = None
    source_count: int
    item_count: int
    sources: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    items: list[TrendItemResponse]

class TopicListResponse(BaseModel):
    total_topics: int
    topics: list[TopicListItemResponse]


# ============================================================
# Trend History & Snapshots Schemas
# ============================================================

class TrendSnapshotPoint(BaseModel):
    captured_at: datetime
    rank: int | None = None
    engagement_value: int | None = None
    secondary_value: int | None = None

    class Config:
        from_attributes = True

class TrendHistoryResponse(BaseModel):
    item_id: int
    title: str
    source_slug: str
    total_snapshots: int
    snapshots: list[TrendSnapshotPoint]


# ============================================================
# Community Comments & Reactions Schemas
# ============================================================

class CommentResponse(BaseModel):
    id: int
    item_id: int | None = None
    topic_id: int | None = None
    author: str
    author_handle: str
    author_avatar_color: str | None = "#3b82f6"
    platform: str
    content: str
    upvotes: int = 0
    sentiment: str = "neutral"
    published_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    total: int
    sentiment_breakdown: dict[str, int] = {}
    comments: list[CommentResponse] = []

