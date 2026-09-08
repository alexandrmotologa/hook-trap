import pytest

from hook_trap.repositories import (
    ChannelRepository,
    DatabaseManager,
    ReplayLogRepository,
    WebhookRequestRepository,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_repo.db")


@pytest.fixture
async def db_manager(db_path):
    mgr = DatabaseManager(db_path)
    await mgr.initialize()
    return mgr


@pytest.mark.asyncio
async def test_webhook_request_repository(db_manager):
    repo = WebhookRequestRepository(db_manager)

    # Insert request
    req_data = {
        "channel_id": "chan_repo_test",
        "method": "POST",
        "path": "/catch/chan_repo_test/webhook",
        "headers": {"content-type": "application/json", "x-test": "1"},
        "query_params": {"foo": "bar"},
        "body_raw": '{"hello": "world"}',
        "body_json": {"hello": "world"},
        "content_type": "application/json",
        "client_ip": "10.0.0.1",
    }
    req_id = await repo.insert(req_data)
    assert req_id is not None

    # Get by ID
    detail = await repo.get_by_id("chan_repo_test", req_id)
    assert detail is not None
    assert detail["id"] == req_id
    assert detail["method"] == "POST"
    assert detail["query_params"] == {"foo": "bar"}
    assert detail["headers"]["x-test"] == "1"
    assert detail["body_json"] == {"hello": "world"}

    # List
    items, total = await repo.list_by_channel("chan_repo_test")
    assert total == 1
    assert len(items) == 1
    assert items[0]["id"] == req_id

    # Filter with method
    items, total = await repo.list_by_channel("chan_repo_test", method="GET")
    assert total == 0
    assert len(items) == 0

    # Increment replay
    await repo.increment_replay_count(req_id)
    updated = await repo.get_by_id("chan_repo_test", req_id)
    assert updated["replay_count"] == 1

    # Export
    exports = await repo.get_all_for_export("chan_repo_test")
    assert len(exports) == 1

    # Prune
    pruned = await repo.prune("chan_repo_test", max_count=1)
    assert pruned == 0

    # Delete
    deleted = await repo.delete_by_channel("chan_repo_test")
    assert deleted == 1
    items_after, total_after = await repo.list_by_channel("chan_repo_test")
    assert total_after == 0


@pytest.mark.asyncio
async def test_replay_log_repository(db_manager):
    webhook_repo = WebhookRequestRepository(db_manager)
    replay_repo = ReplayLogRepository(db_manager)

    # Insert parent webhook request first to satisfy foreign key constraint
    req_id = await webhook_repo.insert(
        {
            "id": "req-123",
            "channel_id": "test-chan",
            "method": "POST",
            "path": "/catch/test-chan",
        }
    )

    log_id = await replay_repo.insert(
        {
            "request_id": req_id,
            "target_url": "http://localhost:3000/webhook",
            "status_code": 200,
            "response_headers": {"content-type": "text/plain"},
            "response_body": "OK",
            "latency_ms": 42.5,
            "error": None,
        }
    )
    assert log_id is not None

    logs = await replay_repo.list_by_request_id(req_id)
    assert len(logs) == 1
    assert logs[0]["id"] == log_id
    assert logs[0]["target_url"] == "http://localhost:3000/webhook"
    assert logs[0]["status_code"] == 200
    assert logs[0]["latency_ms"] == 42.5


@pytest.mark.asyncio
async def test_channel_repository(db_manager):
    repo = ChannelRepository(db_manager)

    # Initial get non-existent
    cfg = await repo.get("chan_non_existent")
    assert cfg is None

    # Upsert new channel
    created = await repo.upsert(
        channel_id="chan_abc",
        name="Production Webhooks",
        auto_forward_url="https://api.example.com/hooks",
        max_requests=250,
    )
    assert created["channel_id"] == "chan_abc"
    assert created["name"] == "Production Webhooks"
    assert created["max_requests"] == 250

    # Get created
    fetched = await repo.get("chan_abc")
    assert fetched is not None
    assert fetched["name"] == "Production Webhooks"
    assert fetched["auto_forward_url"] == "https://api.example.com/hooks"

    # Update existing
    updated = await repo.upsert(
        channel_id="chan_abc",
        name="Updated Name",
        max_requests=100,
    )
    assert updated["name"] == "Updated Name"
    assert updated["max_requests"] == 100
    assert updated["auto_forward_url"] == "https://api.example.com/hooks"
