import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from hook_trap.config import settings
from hook_trap.database import init_db
from hook_trap.routes.api import router as api_router
from hook_trap.routes.catch import router as catch_router
from hook_trap.routes.websocket import router as ws_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    # Ensure database tables exist
    db_file = Path(settings.db_path)
    if db_file.parent and not db_file.parent.exists():
        db_file.parent.mkdir(parents=True, exist_ok=True)

    await init_db(settings.db_path)
    yield


def create_app(
    db_path: str | None = None,
    default_auto_forward_url: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    if db_path:
        settings.db_path = db_path
    if default_auto_forward_url:
        settings.default_auto_forward_url = default_auto_forward_url

    app = FastAPI(
        title="hook-trap",
        description="Real-Time Webhook Inspector & Local Forwarder",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static assets
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Mount routers
    app.include_router(catch_router)
    app.include_router(api_router)
    app.include_router(ws_router)

    @app.get("/healthz")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def root_redirect() -> RedirectResponse:
        """Redirect root visitors to a fresh random channel."""
        random_channel = secrets.token_hex(4)  # 8 character hex id
        return RedirectResponse(url=f"/c/{random_channel}")

    @app.get("/c/{channel_id}")
    async def channel_page(channel_id: str) -> FileResponse:
        """Serve the inspector frontend dashboard."""
        index_file = STATIC_DIR / "index.html"
        return FileResponse(index_file)

    return app


# Default app instance
app = create_app()
