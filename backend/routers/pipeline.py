from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import (
    PipelineStatusResponse, PipelineRunResponse, PipelineFetchSummary,
    AIProcessResponse
)
from backend.services.orchestrator import run_pipeline, get_pipeline_status_data
from backend.services.ai_processor import process_unprocessed_items
from backend.config import settings

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(db: Session = Depends(get_db)):
    """Retrieve runtime pipeline health, mode flags, item volume, and processing metrics."""
    data = get_pipeline_status_data(db)
    return PipelineStatusResponse(**data)

@router.post("/run", response_model=PipelineRunResponse)
async def trigger_full_pipeline_run(
    force_live: bool = Query(False, description="Force live API call instead of mock mode"),
    db: Session = Depends(get_db)
):
    """Trigger a full fetch ingestion cycle across all active sources."""
    results = await run_pipeline(db, force_live=force_live)

    total_fetched = sum(r.items_fetched for r in results)
    total_new = sum(r.items_new for r in results)

    details = [
        PipelineFetchSummary(
            source_slug=r.source_slug,
            status=r.status,
            items_fetched=r.items_fetched,
            items_new=r.items_new,
            duration_ms=r.duration_ms,
            error_message=r.error_message
        )
        for r in results
    ]

    return PipelineRunResponse(
        status="completed",
        message=f"Pipeline run completed across {len(results)} sources. Retrieved {total_fetched} items ({total_new} new).",
        total_sources_attempted=len(results),
        total_items_fetched=total_fetched,
        total_items_new=total_new,
        details=details
    )

@router.post("/run/{slug}", response_model=PipelineRunResponse)
async def trigger_single_source_fetch(
    slug: str,
    force_live: bool = Query(False, description="Force live API call instead of mock mode"),
    db: Session = Depends(get_db)
):
    """Trigger an ingestion fetch cycle for a specific source slug."""
    results = await run_pipeline(db, force_live=force_live, source_slug=slug)
    if not results:
        raise HTTPException(status_code=404, detail=f"Source '{slug}' not found.")

    res = results[0]
    return PipelineRunResponse(
        status=res.status,
        message=f"Fetch completed for '{slug}': {res.items_fetched} items fetched, {res.items_new} new.",
        total_sources_attempted=1,
        total_items_fetched=res.items_fetched,
        total_items_new=res.items_new,
        details=[
            PipelineFetchSummary(
                source_slug=res.source_slug,
                status=res.status,
                items_fetched=res.items_fetched,
                items_new=res.items_new,
                duration_ms=res.duration_ms,
                error_message=res.error_message
            )
        ]
    )

@router.post("/process-ai", response_model=AIProcessResponse)
async def trigger_ai_processing(
    limit: int = Query(50, ge=1, le=200, description="Max items to process"),
    db: Session = Depends(get_db)
):
    """Process un-summarized trending items with Gemini or mock heuristic AI."""
    total, succeeded, failed = await process_unprocessed_items(db, limit=limit)
    return AIProcessResponse(
        status="completed",
        items_processed=total,
        items_succeeded=succeeded,
        items_failed=failed,
        mock_mode=settings.MOCK_AI_MODE
    )
