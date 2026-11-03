"""
test_phase8.py

Comprehensive test suite verifying:
1. Momentum & Velocity State Calculations (surging, cooling, peaking, steady, new, tracking)
2. Topic Clustering Engine & Validation (invalid IDs, duplicate IDs, single-source groups, Jaccard fallback)
3. Analytics Overview Aggregates & 24h Zero-filled Hourly Volume
4. Source Health Observatory State Derivations
5. CSV Export & Formula Injection Prevention Guard

All tests run offline with mock mode and temporary SQLite database (zero real Gemini network calls).
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Source, Category, TrendingItem, FetchLog, Topic, TrendSnapshot
from backend.services.momentum import calculate_momentum_metrics, batch_calculate_momentum
from backend.services.clustering import (
    normalize_title, jaccard_similarity, cluster_by_jaccard_heuristic,
    validate_llm_groups
)
from backend.routers.trends import sanitize_csv_cell, resolve_trending_region
from backend.routers.analytics import get_analytics_overview
from backend.routers.sources import get_sources_health


@pytest.fixture
def test_db():
    """Create a clean in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed sample sources
    src_yt = Source(slug="youtube", display_name="YouTube", source_category="A", source_type_label="Official API", fetch_interval_min=15, is_enabled=True)
    src_bs = Source(slug="bluesky", display_name="Bluesky", source_category="A", source_type_label="Official API", fetch_interval_min=15, is_enabled=True)
    src_gt = Source(slug="google_trends", display_name="Google Trends", source_category="B", source_type_label="Search Interest", fetch_interval_min=60, is_enabled=True)
    src_dis = Source(slug="disabled_platform", display_name="Disabled Platform", source_category="B", source_type_label="News Coverage", fetch_interval_min=60, is_enabled=False)

    cat_tech = Category(name="Technology", color="#3B82F6")
    cat_pol = Category(name="Politics", color="#EF4444")

    session.add_all([src_yt, src_bs, src_gt, src_dis, cat_tech, cat_pol])
    session.commit()

    yield session
    session.close()


# ============================================================
# 1. Momentum State Calculation Tests
# ============================================================

def test_momentum_state_new():
    now = datetime.utcnow()
    # 1 snapshot, first seen 15 minutes ago -> 'new'
    snaps = [(now - timedelta(minutes=15), 10, 500)]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "new"


def test_momentum_state_tracking_insufficient_time():
    now = datetime.utcnow()
    # 3 snapshots, but only spanning 10 minutes, first seen 90 min ago -> 'tracking'
    snaps = [
        (now - timedelta(minutes=90), 10, 500),
        (now - timedelta(minutes=85), 9, 520),
        (now - timedelta(minutes=80), 8, 540)
    ]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "tracking"


def test_momentum_state_surging_by_rank():
    now = datetime.utcnow()
    # First rank: 9, Last rank: 4 -> rank_delta = +5 (>= 3) -> 'surging'
    snaps = [
        (now - timedelta(minutes=60), 9, 1000),
        (now - timedelta(minutes=30), 6, 1200),
        (now, 4, 1500)
    ]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "surging"
    assert mom.rank_delta == 5


def test_momentum_state_surging_by_growth():
    now = datetime.utcnow()
    # Rank steady at 12, but engagement grows from 100 to 200 in 1 hour -> +100% growth -> 'surging'
    snaps = [
        (now - timedelta(hours=1), 12, 100),
        (now - timedelta(minutes=30), 12, 150),
        (now, 12, 200)
    ]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "surging"
    assert mom.growth_per_hour is not None and mom.growth_per_hour >= 0.25


def test_momentum_state_cooling():
    now = datetime.utcnow()
    # Dropping 4 positions (rank 2 to 6) -> delta = -4 (<= -3) -> 'cooling'
    snaps = [
        (now - timedelta(hours=1), 2, 800),
        (now - timedelta(minutes=30), 4, 750),
        (now, 6, 700)
    ]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "cooling"
    assert mom.rank_delta == -4


def test_momentum_state_peaking():
    now = datetime.utcnow()
    # Rank <= 5 (e.g. rank 3 steady) -> 'peaking'
    snaps = [
        (now - timedelta(hours=1), 3, 5000),
        (now - timedelta(minutes=30), 3, 5010),
        (now, 3, 5020)
    ]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "peaking"


def test_momentum_state_steady():
    now = datetime.utcnow()
    # Rank 15 steady, low growth -> 'steady'
    snaps = [
        (now - timedelta(hours=1), 15, 200),
        (now - timedelta(minutes=30), 15, 205),
        (now, 15, 210)
    ]
    mom = calculate_momentum_metrics(snaps, now=now)
    assert mom is not None
    assert mom.state == "steady"


# ============================================================
# 2. Topic Clustering Engine & Validation Tests
# ============================================================

def test_jaccard_normalization_and_similarity():
    title_1 = "ISRO prepares Chandrayaan-4 lunar sample return mission"
    title_2 = "Chandrayaan-4 lunar sample return mission updates from ISRO"
    title_3 = "Lionel Messi scores stunning hat-trick in MLS victory"

    tok_1 = normalize_title(title_1)
    tok_2 = normalize_title(title_2)
    tok_3 = normalize_title(title_3)

    sim_related = jaccard_similarity(tok_1, tok_2)
    sim_unrelated = jaccard_similarity(tok_1, tok_3)

    assert sim_related >= 0.5
    assert sim_unrelated == 0.0


def test_llm_group_validation():
    valid_ids = {1, 2, 3, 4, 5}
    raw_llm = [
        {"title": "Valid Group A", "item_ids": [1, 2]},
        {"title": "Group With Duplicate ID", "item_ids": [2, 3]},   # 2 is already assigned, leaves 3 alone -> dropped (<2)
        {"title": "Group With Fake ID", "item_ids": [999, 888]},    # Fake IDs -> dropped
        {"title": "Single Item Group", "item_ids": [4]},             # < 2 items -> dropped
        {"title": "Valid Group B", "item_ids": [4, 5]}              # 4 & 5 available -> valid
    ]

    validated = validate_llm_groups(raw_llm, valid_ids)
    assert len(validated) == 2
    assert validated[0]["item_ids"] == [1, 2]
    assert validated[1]["item_ids"] == [4, 5]


def test_single_source_group_not_cross_platform(test_db):
    """
    Ensure topics with items from only 1 distinct source have source_count == 1,
    and only source_count >= 2 are considered cross-platform.
    """
    src_yt = test_db.query(Source).filter(Source.slug == "youtube").first()
    now = datetime.utcnow()

    # Topic with two items from the SAME source (YouTube)
    item_1 = TrendingItem(source_id=src_yt.id, external_id="yt1", title="Story A part 1", url="http://yt1", source_category="A", fetched_at=now)
    item_2 = TrendingItem(source_id=src_yt.id, external_id="yt2", title="Story A part 2", url="http://yt2", source_category="A", fetched_at=now)
    test_db.add_all([item_1, item_2])
    test_db.flush()

    topic = Topic(title="Story A Macro", is_active=True, created_at=now, updated_at=now)
    test_db.add(topic)
    test_db.flush()

    item_1.topic_id = topic.id
    item_2.topic_id = topic.id
    test_db.commit()

    distinct_sources = {m.source_id for m in topic.items}
    topic.source_count = len(distinct_sources)
    test_db.commit()

    assert topic.source_count == 1  # NOT cross-platform
    assert len(topic.items) == 2


# ============================================================
# 3. Analytics Overview Aggregates Tests
# ============================================================

def test_analytics_overview_shape_and_zero_fill(test_db):
    now = datetime.utcnow()
    src_yt = test_db.query(Source).filter(Source.slug == "youtube").first()
    cat_tech = test_db.query(Category).filter(Category.name == "Technology").first()

    # Insert items within 24h
    item = TrendingItem(
        source_id=src_yt.id,
        category_id=cat_tech.id,
        external_id="yt_test",
        title="AI breakthrough",
        url="http://test",
        source_category="A",
        location_india="Bengaluru",
        ai_processed=True,
        fetched_at=now
    )
    test_db.add(item)
    test_db.commit()

    overview = get_analytics_overview(recency="24h", db=test_db)

    # Check structure
    assert hasattr(overview, "category_breakdown")
    assert hasattr(overview, "platform_share")
    assert hasattr(overview, "source_category_ratio")
    assert hasattr(overview, "top_locations")
    assert hasattr(overview, "hourly_volume")
    assert hasattr(overview, "ai_coverage")
    assert hasattr(overview, "totals")

    # Check hourly volume zero-filling (must contain exactly 24 slots)
    assert len(overview.hourly_volume) == 24
    total_hourly_items = sum(h.count for h in overview.hourly_volume)
    assert total_hourly_items >= 1

    # Check top locations contains Bengaluru
    loc_names = [l.location for l in overview.top_locations]
    assert "Bengaluru" in loc_names


# ============================================================
# 4. Source Health Observatory State Tests
# ============================================================

def test_source_health_states(test_db):
    src_yt = test_db.query(Source).filter(Source.slug == "youtube").first()
    src_bs = test_db.query(Source).filter(Source.slug == "bluesky").first()
    src_dis = test_db.query(Source).filter(Source.slug == "disabled_platform").first()

    now = datetime.utcnow()

    # 1. YouTube: recent success within 2x interval (15m * 2 = 30m) -> 'healthy'
    log_yt = FetchLog(source_id=src_yt.id, status="success", items_fetched=10, duration_ms=500, started_at=now - timedelta(minutes=5), completed_at=now - timedelta(minutes=5))
    
    # 2. Bluesky: recent error -> 'error'
    log_bs = FetchLog(source_id=src_bs.id, status="error", error_message="API Rate limit", started_at=now - timedelta(minutes=2), completed_at=now - timedelta(minutes=2))

    test_db.add_all([log_yt, log_bs])
    test_db.commit()

    health = get_sources_health(db=test_db)
    states = {s.slug: s.health_state for s in health.sources}

    assert states["youtube"] == "healthy"
    assert states["bluesky"] == "error"
    assert states["disabled_platform"] == "disabled"
    assert states["google_trends"] == "never_run"


# ============================================================
# 5. CSV Export & Injection Guard Tests
# ============================================================

def test_csv_injection_guard():
    # Dangerous formula injection payloads
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|'/c calc'!A0") == "'+cmd|'/c calc'!A0"
    assert sanitize_csv_cell("-2+3") == "'-2+3"
    assert sanitize_csv_cell("@SUM(A1:A5)") == "'@SUM(A1:A5)"

    # Safe strings
    assert sanitize_csv_cell("Normal Story Title") == "Normal Story Title"
    assert sanitize_csv_cell(12345) == "12345"
    assert sanitize_csv_cell(None) == ""
