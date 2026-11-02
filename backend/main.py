import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import engine, SessionLocal
from backend.seed import init_db, seed_db
from backend.models import TrendingItem, Source
from backend.schemas import HealthResponse
from backend.services.orchestrator import run_pipeline
from backend.services.ai_processor import process_unprocessed_items
from backend.services.scheduler import start_scheduler, stop_scheduler
from backend.routers import (
    trends_router, sources_router, categories_router, pipeline_router, analytics_router, topics_router
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

async def _start_ipv6_proxy():
    """Bridges IPv6 [::1]:8000 to IPv4 127.0.0.1:8000 on Windows so that
    browsers navigating to 'localhost:8000' never encounter ERR_CONNECTION_REFUSED.
    """
    async def _pipe(r, w):
        try:
            while True:
                data = await r.read(65536)
                if not data:
                    break
                w.write(data)
                await w.drain()
        except Exception:
            pass
        finally:
            try:
                w.close()
            except Exception:
                pass

    async def _handle(reader_in, writer_in):
        try:
            reader_out, writer_out = await asyncio.open_connection("127.0.0.1", 8000)
            await asyncio.gather(_pipe(reader_in, writer_out), _pipe(reader_out, writer_in))
        except Exception:
            pass
        finally:
            try:
                writer_in.close()
            except Exception:
                pass

    try:
        import socket
        server = await asyncio.start_server(_handle, "::1", 8000, family=socket.AF_INET6)
        print("[IPv6 Proxy] Bridging [::1]:8000 -> 127.0.0.1:8000 for localhost browser compatibility.")
        return server
    except Exception:
        return None


async def _initial_load():
    """Fetch and run the AI sweep in the background so the server accepts requests right away."""
    db = SessionLocal()
    try:
        await run_pipeline(db, force_live=False)
        await process_unprocessed_items(db, limit=100)
        print("[Startup] Initial load finished.")
    except Exception as e:
        print(f"[Startup] Initial load failed: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Initialize and seed database
    init_db()
    db = SessionLocal()
    try:
        seed_db(db)

        from datetime import datetime, timedelta
        # Freshness check: ensure all enabled platforms have recent items within the last 12 hours
        now = datetime.utcnow()
        recent_cutoff = now - timedelta(hours=12)
        enabled_sources = db.query(Source).filter(Source.is_enabled == True).all()

        needs_refresh = False
        for s in enabled_sources:
            s_count = db.query(TrendingItem).filter(
                TrendingItem.source_id == s.id,
                TrendingItem.fetched_at >= recent_cutoff
            ).count()
            if s_count == 0:
                needs_refresh = True
                break

        if needs_refresh or db.query(TrendingItem).count() == 0:
            print("[Startup] Feeds missing or stale. Loading data in the background...")
            app.state.initial_task = asyncio.create_task(_initial_load())
    finally:
        db.close()

    # 2. Start APScheduler background jobs
    start_scheduler()
    proxy_server = await _start_ipv6_proxy()

    yield

    # 3. Shutdown
    stop_scheduler()
    if proxy_server:
        proxy_server.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(trends_router)
app.include_router(sources_router)
app.include_router(categories_router)
app.include_router(pipeline_router)
app.include_router(analytics_router)
app.include_router(topics_router)

# Mount static frontend directory if it exists
if not FRONTEND_DIR.exists():
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check():
    """System health check endpoint."""
    db = SessionLocal()
    sources_enabled = 0
    db_connected = False
    try:
        sources_enabled = db.query(Source).filter(Source.is_enabled == True).count()
        db_connected = True
    except Exception:
        db_connected = False
    finally:
        db.close()

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        mock_fetch_mode=settings.MOCK_FETCH_MODE,
        mock_ai_mode=settings.MOCK_AI_MODE,
        database_connected=db_connected,
        sources_enabled=sources_enabled
    )

@app.get("/", tags=["system"])
def read_root():
    """Serve frontend index.html if present, else return API root info."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "api_v1": {
            "trends": "/api/v1/trends",
            "sources": "/api/v1/sources",
            "categories": "/api/v1/categories",
            "pipeline": "/api/v1/pipeline/status",
            "analytics": "/api/v1/analytics/overview",
            "topics": "/api/v1/topics"
        }
    })


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
