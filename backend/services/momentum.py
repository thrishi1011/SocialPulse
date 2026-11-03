"""
backend/services/momentum.py

Trend Velocity & Momentum Analysis Engine:
Computes mathematical velocity vectors, rank delta dynamics, and growth curves
across time-series snapshot captures.

States & Rules:
- "new": exactly 1-2 snapshots and first seen less than 60 minutes ago
- "surging": rank_delta >= 3 OR relative_growth >= 0.25 per hour
- "cooling": rank_delta <= -3 OR relative_growth <= -0.05 per hour
- "peaking": otherwise, if rank <= 5 or top 20% by engagement within source
- "steady": otherwise
- "tracking": fewer than 3 snapshots or observation span < 30 minutes (not enough data)
"""
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models import TrendSnapshot, TrendingItem
from backend.schemas import TrendMomentumInfo

# ============================================================
# Named Algorithmic Thresholds
# ============================================================
SURGING_RANK_DELTA = 3          # Climbing 3+ positions (e.g. rank 6 -> rank 3 = delta +3)
SURGING_GROWTH_RATE = 0.25      # >= 25% relative engagement growth per hour
COOLING_RANK_DELTA = -3         # Falling 3+ positions (e.g. rank 2 -> rank 5 = delta -3)
COOLING_GROWTH_RATE = -0.05     # <= -5% engagement decline per hour
PEAKING_RANK_THRESHOLD = 5      # Top 5 rank in its respective platform
MIN_SNAPSHOTS_FOR_MOMENTUM = 3  # Minimum snapshots required for velocity calculation
MIN_SPAN_MINUTES = 30           # Minimum observation time required
NEW_MAX_AGE_MINUTES = 60        # First observed within 60 minutes


def calculate_momentum_metrics(
    snapshots: list[tuple[datetime, int | None, int | None]],
    now: datetime | None = None,
    is_top_20_percent: bool = False
) -> TrendMomentumInfo | None:
    """
    Pure, testable mathematical calculation of momentum state from an ordered snapshot sequence.

    Args:
        snapshots: list of (captured_at, rank, engagement_value) ordered oldest to newest.
        now: reference timestamp for freshness checks (defaults to UTC now).
        is_top_20_percent: whether the current item is in the top 20% of engagement for its source.

    Returns:
        TrendMomentumInfo or None if no snapshots exist.
    """
    if not snapshots:
        return None

    if now is None:
        now = datetime.utcnow()

    # Determine points series for inline sparkline (prefer engagement, fallback to rank)
    eng_points = [s[2] for s in snapshots if s[2] is not None]
    rank_points = [s[1] for s in snapshots if s[1] is not None]
    points = eng_points if eng_points else rank_points
    # Take most recent 15 points
    recent_points = points[-15:] if points else []

    first_time, first_rank, first_eng = snapshots[0]
    last_time, last_rank, last_eng = snapshots[-1]

    first_seen_age_minutes = (now - first_time).total_seconds() / 60.0
    elapsed_seconds = (last_time - first_time).total_seconds()
    elapsed_hours = elapsed_seconds / 3600.0

    # Case 1: Insufficient snapshots (< 3)
    if len(snapshots) < MIN_SNAPSHOTS_FOR_MOMENTUM:
        if first_seen_age_minutes <= NEW_MAX_AGE_MINUTES:
            return TrendMomentumInfo(
                state="new",
                rank_delta=None,
                growth_per_hour=None,
                points=recent_points
            )
        return TrendMomentumInfo(
            state="tracking",
            rank_delta=None,
            growth_per_hour=None,
            points=recent_points
        )

    # Case 2: Snapshots exist but time span is too narrow (< 30 minutes)
    if elapsed_seconds < (MIN_SPAN_MINUTES * 60):
        if first_seen_age_minutes <= NEW_MAX_AGE_MINUTES:
            return TrendMomentumInfo(
                state="new",
                rank_delta=None,
                growth_per_hour=None,
                points=recent_points
            )
        return TrendMomentumInfo(
            state="tracking",
            rank_delta=None,
            growth_per_hour=None,
            points=recent_points
        )

    # Calculate rank delta (positive = climbing up in rank)
    rank_delta: int | None = None
    if first_rank is not None and last_rank is not None:
        rank_delta = first_rank - last_rank

    # Calculate engagement growth rate per hour
    relative_growth: float | None = None
    if first_eng is not None and last_eng is not None and elapsed_hours > 0:
        eng_rate_per_hour = (last_eng - first_eng) / elapsed_hours
        relative_growth = round(eng_rate_per_hour / max(first_eng, 1), 3)

    # State evaluation hierarchy
    state: str = "steady"

    # 1. Surging (either rising in rank or rapid engagement growth)
    if (rank_delta is not None and rank_delta >= SURGING_RANK_DELTA) or (
        relative_growth is not None and relative_growth >= SURGING_GROWTH_RATE
    ):
        state = "surging"
    # 2. Cooling (falling in rank or losing engagement)
    elif (rank_delta is not None and rank_delta <= COOLING_RANK_DELTA) or (
        relative_growth is not None and relative_growth <= COOLING_GROWTH_RATE
    ):
        state = "cooling"
    # 3. Peaking (sustained top position or top quintile engagement)
    elif (last_rank is not None and last_rank <= PEAKING_RANK_THRESHOLD) or is_top_20_percent:
        state = "peaking"
    else:
        state = "steady"

    return TrendMomentumInfo(
        state=state,
        rank_delta=rank_delta,
        growth_per_hour=relative_growth,
        points=recent_points
    )


def batch_calculate_momentum(
    db: Session,
    items: list[TrendingItem],
    now: datetime | None = None
) -> dict[int, TrendMomentumInfo]:
    """
    Fetch historical snapshots for all items on the current page in ONE single SQL query
    (strictly preventing N+1 overhead) and calculate momentum vectors.
    """
    if not items:
        return {}

    if now is None:
        now = datetime.utcnow()

    item_ids = [it.id for it in items]

    # Pre-calculate 80th percentile engagement thresholds per source
    source_ids = {it.source_id for it in items}
    top_20_thresholds = {}
    for s_id in source_ids:
        # Approximate 80th percentile threshold
        vals = (
            db.query(TrendingItem.engagement_value)
            .filter(
                TrendingItem.source_id == s_id,
                TrendingItem.engagement_value.isnot(None),
                TrendingItem.engagement_value > 0
            )
            .order_by(TrendingItem.engagement_value.desc())
            .all()
        )
        if vals:
            idx = max(0, int(len(vals) * 0.20) - 1)
            top_20_thresholds[s_id] = vals[idx][0]
        else:
            top_20_thresholds[s_id] = float("inf")

    # Single batch query for snapshots
    cutoff_7d = now - timedelta(days=7)
    snapshots = (
        db.query(TrendSnapshot)
        .filter(
            TrendSnapshot.item_id.in_(item_ids),
            TrendSnapshot.captured_at >= cutoff_7d
        )
        .order_by(TrendSnapshot.item_id.asc(), TrendSnapshot.captured_at.asc())
        .all()
    )

    # Group snapshots by item_id
    grouped_snaps: dict[int, list[tuple[datetime, int | None, int | None]]] = {}
    for snap in snapshots:
        grouped_snaps.setdefault(snap.item_id, []).append(
            (snap.captured_at, snap.rank, snap.engagement_value)
        )

    results: dict[int, TrendMomentumInfo] = {}
    for it in items:
        item_snaps = grouped_snaps.get(it.id, [])
        is_top = (
            it.engagement_value is not None
            and it.engagement_value >= top_20_thresholds.get(it.source_id, float("inf"))
        )
        mom = calculate_momentum_metrics(item_snaps, now=now, is_top_20_percent=is_top)
        if mom:
            results[it.id] = mom

    return results
