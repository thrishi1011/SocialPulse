import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.config import settings
from backend.models import Source, TrendingItem, FetchLog
from backend.fetchers import ALL_FETCHERS, get_fetcher
from backend.fetchers.base import FetchResult

_pipeline_lock = asyncio.Lock()
_last_run_time: datetime | None = None

async def run_pipeline(
    db: Session,
    force_live: bool = False,
    source_slug: str | None = None
) -> list[FetchResult]:
    """
    Execute fetch cycle across all enabled sources or a specific source slug.
    """
    global _last_run_time
    results: list[FetchResult] = []

    async with _pipeline_lock:
        _last_run_time = datetime.utcnow()

        if source_slug:
            fetcher = get_fetcher(source_slug)
            if not fetcher:
                results.append(FetchResult(
                    source_slug=source_slug,
                    status="error",
                    items_fetched=0,
                    items_new=0,
                    duration_ms=0,
                    error_message=f"Fetcher '{source_slug}' not recognized."
                ))
            else:
                res = await fetcher.execute(db, force_live=force_live)
                results.append(res)
        else:
            # Query enabled sources
            enabled_sources = db.query(Source).filter(Source.is_enabled == True).all()
            for src in enabled_sources:
                fetcher = get_fetcher(src.slug)
                if fetcher:
                    try:
                        res = await fetcher.execute(db, force_live=force_live)
                        results.append(res)
                    except Exception as e:
                        results.append(FetchResult(
                            source_slug=src.slug,
                            status="error",
                            items_fetched=0,
                            items_new=0,
                            duration_ms=0,
                            error_message=str(e)
                        ))

            # Run topic clustering after full pipeline fetch cycle completes
            try:
                from backend.services.clustering import run_topic_clustering
                await run_topic_clustering(db)
            except Exception as cluster_err:
                print(f"[Orchestrator] Topic clustering execution notice: {cluster_err}")

    return results

def get_pipeline_status_data(db: Session) -> dict:
    """Return runtime summary metrics for the pipeline."""
    total_items = db.query(TrendingItem).count()
    ai_processed = db.query(TrendingItem).filter(TrendingItem.ai_processed == True).count()
    ai_pending = total_items - ai_processed
    enabled_count = db.query(Source).filter(Source.is_enabled == True).count()

    return {
        "is_running": _pipeline_lock.locked(),
        "last_run_time": _last_run_time,
        "total_items_in_db": total_items,
        "total_ai_processed": ai_processed,
        "total_ai_pending": ai_pending,
        "mock_fetch_mode": settings.MOCK_FETCH_MODE,
        "mock_ai_mode": settings.MOCK_AI_MODE,
        "active_sources_count": enabled_count
    }
