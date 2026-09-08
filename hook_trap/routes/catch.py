import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from hook_trap.config import settings
from hook_trap.services.ingestion import webhook_ingestion_service

logger = logging.getLogger("hook_trap.catch")

router = APIRouter(tags=["Ingestion"])


@router.api_route(
    "/catch/{channel_id}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def catch_root(
    channel_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Capture webhook sent to channel root."""
    return await webhook_ingestion_service.ingest(
        channel_id=channel_id,
        subpath="",
        request=request,
        background_tasks=background_tasks,
        db_path=settings.db_path,
        default_auto_forward_url=settings.default_auto_forward_url,
        replay_timeout=settings.replay_timeout,
    )


@router.api_route(
    "/catch/{channel_id}/{subpath:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def catch_subpath(
    channel_id: str,
    subpath: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Capture webhook sent to channel with arbitrary subpath."""
    return await webhook_ingestion_service.ingest(
        channel_id=channel_id,
        subpath=subpath,
        request=request,
        background_tasks=background_tasks,
        db_path=settings.db_path,
        default_auto_forward_url=settings.default_auto_forward_url,
        replay_timeout=settings.replay_timeout,
    )
