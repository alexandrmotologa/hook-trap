"""
Database facade providing backward-compatible functional interfaces for data access.
Internally delegates to object-oriented Repository classes.
"""

from typing import Any

from hook_trap.repositories import (
    ChannelRepository,
    DatabaseManager,
    ReplayLogRepository,
    ScenarioRepository,
    WebhookRequestRepository,
    utc_now_iso,
)

# Private alias to maintain backwards-compatibility with internal imports
_utc_now_iso = utc_now_iso

# Global repository cache by db_path to avoid redundant manager instantiations
_repo_cache: dict[
    str,
    tuple[
        DatabaseManager,
        WebhookRequestRepository,
        ReplayLogRepository,
        ChannelRepository,
        ScenarioRepository,
    ],
] = {}


def _get_repos(
    db_path: str,
) -> tuple[
    DatabaseManager,
    WebhookRequestRepository,
    ReplayLogRepository,
    ChannelRepository,
    ScenarioRepository,
]:
    if db_path not in _repo_cache:
        mgr = DatabaseManager(db_path)
        webhook_repo = WebhookRequestRepository(mgr)
        replay_repo = ReplayLogRepository(mgr)
        channel_repo = ChannelRepository(mgr)
        scenario_repo = ScenarioRepository(mgr)
        _repo_cache[db_path] = (mgr, webhook_repo, replay_repo, channel_repo, scenario_repo)
    return _repo_cache[db_path]



async def init_db(db_path: str) -> None:
    """Initialize SQLite database tables and indexes."""
    mgr, _, _, _, _ = _get_repos(db_path)
    await mgr.initialize()


async def insert_webhook_request(db_path: str, data: dict[str, Any]) -> str:
    """Insert a captured webhook request record."""
    _, webhook_repo, _, _, _ = _get_repos(db_path)
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
    _, webhook_repo, _, _, _ = _get_repos(db_path)
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
    _, webhook_repo, _, _, _ = _get_repos(db_path)
    return await webhook_repo.get_by_id(channel_id, request_id)


async def delete_channel_requests(db_path: str, channel_id: str) -> int:
    """Delete all requests and associated logs for a channel."""
    _, webhook_repo, _, _, _ = _get_repos(db_path)
    return await webhook_repo.delete_by_channel(channel_id)


async def increment_replay_count(db_path: str, request_id: str) -> None:
    """Increment replay counter for a request."""
    _, webhook_repo, _, _, _ = _get_repos(db_path)
    await webhook_repo.increment_replay_count(request_id)


async def insert_replay_log(db_path: str, data: dict[str, Any]) -> str:
    """Log an HTTP replay execution."""
    _, _, replay_repo, _, _ = _get_repos(db_path)
    return await replay_repo.insert(data)


async def get_replay_logs_for_request(db_path: str, request_id: str) -> list[dict[str, Any]]:
    """Get replay attempts for a specific webhook request."""
    _, _, replay_repo, _, _ = _get_repos(db_path)
    return await replay_repo.list_by_request_id(request_id)


async def prune_channel_requests(db_path: str, channel_id: str, max_count: int = 500) -> int:
    """Delete oldest requests for a channel if total count exceeds max_count."""
    _, webhook_repo, _, _, _ = _get_repos(db_path)
    return await webhook_repo.prune(channel_id, max_count)


async def get_channel_config(db_path: str, channel_id: str) -> dict[str, Any] | None:
    """Retrieve persisted channel configuration."""
    _, _, _, channel_repo, _ = _get_repos(db_path)
    return await channel_repo.get(channel_id)


async def upsert_channel_config(
    db_path: str,
    channel_id: str,
    name: str | None = None,
    auto_forward_url: str | None = None,
    max_requests: int | None = None,
) -> dict[str, Any]:
    """Create or update channel configuration."""
    _, _, _, channel_repo, _ = _get_repos(db_path)
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
    _, webhook_repo, _, _, _ = _get_repos(db_path)
    return await webhook_repo.get_all_for_export(channel_id)


# --- Scenario Sequence Runner Database Operations ---


async def create_scenario(
    db_path: str,
    scenario_data: dict[str, Any],
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new webhook scenario with optional steps."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.create(scenario_data, steps=steps)


async def get_scenario(db_path: str, scenario_id: str) -> dict[str, Any] | None:
    """Retrieve scenario detail including all ordered steps."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.get(scenario_id)


async def list_scenarios_by_channel(db_path: str, channel_id: str) -> list[dict[str, Any]]:
    """Retrieve all scenarios configured for a channel."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.list_by_channel(channel_id)


async def update_scenario(
    db_path: str,
    scenario_id: str,
    data: dict[str, Any],
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Update scenario fields and optionally replace steps."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.update(scenario_id, data, steps=steps)


async def delete_scenario(db_path: str, scenario_id: str) -> bool:
    """Delete scenario and all associated steps."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.delete(scenario_id)


async def add_scenario_step(
    db_path: str, scenario_id: str, step_data: dict[str, Any]
) -> dict[str, Any]:
    """Append a step to a scenario."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.add_step(scenario_id, step_data)


async def delete_scenario_step(db_path: str, scenario_id: str, step_id: str) -> bool:
    """Delete a step from a scenario."""
    _, _, _, _, scenario_repo = _get_repos(db_path)
    return await scenario_repo.delete_step(scenario_id, step_id)

