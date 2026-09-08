"""
Database facade providing backward-compatible functional interfaces for data access.
Internally delegates to object-oriented Repository classes.
"""

from typing import Any

from hook_trap.repositories import (
    ChannelRepository,
    DatabaseManager,
    ReplayLogRepository,
    WebhookRequestRepository,
    utc_now_iso,
)

# Private alias to maintain backwards-compatibility with internal imports
_utc_now_iso = utc_now_iso

# Global repository cache by db_path to avoid redundant manager instantiations
_repo_cache: dict[
    str,
    tuple[DatabaseManager, WebhookRequestRepository, ReplayLogRepository, ChannelRepository],
] = {}


def _get_repos(
    db_path: str,
) -> tuple[DatabaseManager, WebhookRequestRepository, ReplayLogRepository, ChannelRepository]:
    if db_path not in _repo_cache:
        mgr = DatabaseManager(db_path)
        webhook_repo = WebhookRequestRepository(mgr)
        replay_repo = ReplayLogRepository(mgr)
        channel_repo = ChannelRepository(mgr)
        _repo_cache[db_path] = (mgr, webhook_repo, replay_repo, channel_repo)
    return _repo_cache[db_path]


async def init_db(db_path: str) -> None:
    """Initialize SQLite database tables and indexes."""
    mgr, _, _, _ = _get_repos(db_path)
    await mgr.initialize()


async def insert_webhook_request(db_path: str, data: dict[str, Any]) -> str:
    """Insert a captured webhook request record."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    return await webhook_repo.insert(data)


async def get_webhook_requests(
    db_path: str,
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
    method: str | None = None,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve paginated summaries and total count for a channel."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    return await webhook_repo.list_by_channel(
        channel_id=channel_id,
        limit=limit,
        offset=offset,
        method=method,
        search=search,
    )


async def get_webhook_request_detail(
    db_path: str, channel_id: str, request_id: str
) -> dict[str, Any] | None:
    """Retrieve full detail of a specific request."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    return await webhook_repo.get_by_id(channel_id, request_id)


async def delete_channel_requests(db_path: str, channel_id: str) -> int:
    """Delete all requests and associated logs for a channel."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    return await webhook_repo.delete_by_channel(channel_id)


async def increment_replay_count(db_path: str, request_id: str) -> None:
    """Increment replay counter for a request."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    await webhook_repo.increment_replay_count(request_id)


async def insert_replay_log(db_path: str, data: dict[str, Any]) -> str:
    """Log an HTTP replay execution."""
    _, _, replay_repo, _ = _get_repos(db_path)
    return await replay_repo.insert(data)


async def get_replay_logs_for_request(db_path: str, request_id: str) -> list[dict[str, Any]]:
    """Get replay attempts for a specific webhook request."""
    _, _, replay_repo, _ = _get_repos(db_path)
    return await replay_repo.list_by_request_id(request_id)


async def prune_channel_requests(db_path: str, channel_id: str, max_count: int = 500) -> int:
    """Delete oldest requests for a channel if total count exceeds max_count."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    return await webhook_repo.prune(channel_id, max_count)


async def get_channel_config(db_path: str, channel_id: str) -> dict[str, Any] | None:
    """Retrieve persisted channel configuration."""
    _, _, _, channel_repo = _get_repos(db_path)
    return await channel_repo.get(channel_id)


async def upsert_channel_config(
    db_path: str,
    channel_id: str,
    name: str | None = None,
    auto_forward_url: str | None = None,
    max_requests: int | None = None,
) -> dict[str, Any]:
    """Create or update channel configuration."""
    _, _, _, channel_repo = _get_repos(db_path)
    return await channel_repo.upsert(
        channel_id=channel_id,
        name=name,
        auto_forward_url=auto_forward_url,
        max_requests=max_requests,
    )


async def get_all_channel_requests_for_export(
    db_path: str, channel_id: str
) -> list[dict[str, Any]]:
    """Retrieve all requests for a channel with parsed details for export."""
    _, webhook_repo, _, _ = _get_repos(db_path)
    return await webhook_repo.get_all_for_export(channel_id)
