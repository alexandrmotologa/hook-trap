import os

import aiosqlite
import pytest

from hook_trap.database import (
    delete_channel_requests,
    get_channel_config,
    get_replay_logs_for_request,
    get_webhook_request_detail,
    get_webhook_requests,
    init_db,
    insert_replay_log,
    insert_webhook_request,
    upsert_channel_config,
)


@pytest.fixture
async def temp_db(tmp_path):
    db_path = str(tmp_path / "test_hook_trap.db")
    await init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_init_db_and_tables(temp_db):
    async with aiosqlite.connect(temp_db) as db, db.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ) as cursor:
        tables = [row[0] for row in await cursor.fetchall()]
        assert "webhook_requests" in tables
        assert "replay_logs" in tables
        assert "channels" in tables


@pytest.mark.asyncio
async def test_insert_and_get_request(temp_db):
    req_data = {
        "channel_id": "chan_abc",
        "method": "POST",
        "path": "/catch/chan_abc/v1/checkout",
        "query_params": {"foo": "bar"},
        "headers": {"Stripe-Signature": "t=123,v1=abc"},
        "body_raw": '{"amount": 1500}',
        "body_json": {"amount": 1500},
        "content_type": "application/json",
        "client_ip": "192.168.1.1",
    }
    req_id = await insert_webhook_request(temp_db, req_data)
    assert req_id is not None

    items, total = await get_webhook_requests(temp_db, "chan_abc")
    assert total == 1
    assert items[0]["id"] == req_id
    assert items[0]["method"] == "POST"
    assert items[0]["body_size"] == len(req_data["body_raw"])

    detail = await get_webhook_request_detail(temp_db, "chan_abc", req_id)
    assert detail is not None
    assert detail["headers"]["Stripe-Signature"] == "t=123,v1=abc"
    assert detail["query_params"]["foo"] == "bar"
    assert detail["body_json"]["amount"] == 1500


@pytest.mark.asyncio
async def test_filter_and_search(temp_db):
    for i in range(5):
        await insert_webhook_request(
            temp_db,
            {
                "channel_id": "test_filter",
                "method": "POST" if i % 2 == 0 else "GET",
                "path": f"/catch/test_filter/item-{i}",
                "body_raw": f"payload contents {i}",
            },
        )

    # Filter POST
    posts, count = await get_webhook_requests(temp_db, "test_filter", method="POST")
    assert count == 3
    assert all(p["method"] == "POST" for p in posts)

    # Search
    search_res, search_cnt = await get_webhook_requests(
        temp_db, "test_filter", search="item-3"
    )
    assert search_cnt == 1
    assert search_res[0]["path"] == "/catch/test_filter/item-3"


@pytest.mark.asyncio
async def test_replay_log_and_channel_config(temp_db):
    req_id = await insert_webhook_request(
        temp_db,
        {
            "channel_id": "replay_chan",
            "method": "POST",
            "path": "/catch/replay_chan",
            "body_raw": "data",
        },
    )

    log_id = await insert_replay_log(
        temp_db,
        {
            "request_id": req_id,
            "target_url": "http://localhost:3000/api",
            "status_code": 200,
            "response_headers": {"content-type": "application/json"},
            "response_body": '{"ok": true}',
            "latency_ms": 34.5,
        },
    )
    assert log_id is not None

    logs = await get_replay_logs_for_request(temp_db, req_id)
    assert len(logs) == 1
    assert logs[0]["status_code"] == 200
    assert logs[0]["latency_ms"] == 34.5

    # Channel config upsert
    cfg = await upsert_channel_config(
        temp_db, "replay_chan", auto_forward_url="http://localhost:3000/hook"
    )
    assert cfg["auto_forward_url"] == "http://localhost:3000/hook"

    loaded_cfg = await get_channel_config(temp_db, "replay_chan")
    assert loaded_cfg["auto_forward_url"] == "http://localhost:3000/hook"


@pytest.mark.asyncio
async def test_clear_channel_requests(temp_db):
    await insert_webhook_request(
        temp_db,
        {"channel_id": "to_clear", "method": "GET", "path": "/catch/to_clear"},
    )
    deleted = await delete_channel_requests(temp_db, "to_clear")
    assert deleted == 1

    items, total = await get_webhook_requests(temp_db, "to_clear")
    assert total == 0


@pytest.mark.asyncio
async def test_prune_channel_requests(temp_db):
    from hook_trap.database import get_all_channel_requests_for_export, prune_channel_requests

    # Insert 10 requests into prune_test channel
    for i in range(10):
        await insert_webhook_request(
            temp_db,
            {
                "channel_id": "prune_test",
                "method": "POST",
                "path": f"/catch/prune_test/{i}",
                "body_raw": f"body {i}",
            },
        )

    # Prune to keep only latest 4
    deleted = await prune_channel_requests(temp_db, "prune_test", max_count=4)
    assert deleted == 6

    _remaining, total = await get_webhook_requests(temp_db, "prune_test")
    assert total == 4

    exported = await get_all_channel_requests_for_export(temp_db, "prune_test")
    assert len(exported) == 4
    assert all(r["channel_id"] == "prune_test" for r in exported)
