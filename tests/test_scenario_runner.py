import os
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from hook_trap.database import (
    add_scenario_step,
    create_scenario,
    delete_scenario,
    delete_scenario_step,
    get_scenario,
    init_db,
    list_scenarios_by_channel,
    update_scenario,
)
from hook_trap.models import ScenarioRunResult
from hook_trap.server import create_app
from hook_trap.services.scenario_runner import ScenarioRunner, scenario_runner


@pytest.fixture
async def temp_db(tmp_path):
    db_path = str(tmp_path / "test_scenarios.db")
    await init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_scenario_repository_crud(temp_db):
    scenario_data = {
        "channel_id": "chan_scen_1",
        "name": "E-Commerce Checkout",
        "description": "Multi-step checkout flow",
        "target_url": "http://localhost:8000/api",
        "delay_between_steps_ms": 100,
    }
    steps = [
        {
            "name": "Create Order",
            "method": "POST",
            "path_suffix": "orders",
            "headers": {"Content-Type": "application/json"},
            "payload_raw": '{"item": "book"}',
            "expected_status": 201,
        },
        {
            "name": "Process Payment",
            "method": "POST",
            "path_suffix": "payments",
            "headers": {"Content-Type": "application/json"},
            "payload_raw": '{"amount": 2500}',
            "expected_status": 200,
        },
    ]

    created = await create_scenario(temp_db, scenario_data, steps=steps)
    assert created["id"] is not None
    assert created["name"] == "E-Commerce Checkout"
    assert len(created["steps"]) == 2
    assert created["steps"][0]["expected_status"] == 201

    # Fetch
    fetched = await get_scenario(temp_db, created["id"])
    assert fetched is not None
    assert fetched["name"] == "E-Commerce Checkout"
    assert len(fetched["steps"]) == 2
    assert fetched["steps"][0]["name"] == "Create Order"

    # List by channel
    channel_list = await list_scenarios_by_channel(temp_db, "chan_scen_1")
    assert len(channel_list) == 1
    assert channel_list[0]["id"] == created["id"]

    # Add Step
    new_step = await add_scenario_step(
        temp_db,
        created["id"],
        {
            "name": "Send Receipt",
            "method": "POST",
            "path_suffix": "receipts",
            "payload_raw": '{"send_email": true}',
            "expected_status": 200,
        },
    )
    assert new_step["id"] is not None
    assert new_step["step_order"] == 3

    updated_sc = await get_scenario(temp_db, created["id"])
    assert len(updated_sc["steps"]) == 3

    # Delete single step
    deleted_step = await delete_scenario_step(temp_db, created["id"], new_step["id"])
    assert deleted_step is True

    # Update scenario
    updated = await update_scenario(
        temp_db,
        created["id"],
        {"name": "Updated Checkout Flow", "delay_between_steps_ms": 200},
    )
    assert updated["name"] == "Updated Checkout Flow"
    assert updated["delay_between_steps_ms"] == 200

    # Delete scenario
    deleted = await delete_scenario(temp_db, created["id"])
    assert deleted is True

    assert await get_scenario(temp_db, created["id"]) is None


@pytest.mark.asyncio
async def test_scenario_runner_successful_execution(temp_db):
    """Test 3-step sequence running against a dummy HTTP receiver."""
    received_requests: list[dict[str, Any]] = []

    async def step_one_handler(request):
        body = await request.body()
        received_requests.append({"path": "/orders", "body": body.decode()})
        return JSONResponse({"order_id": "ord_123"}, status_code=201)

    async def step_two_handler(request):
        body = await request.body()
        received_requests.append({"path": "/payments", "body": body.decode()})
        return JSONResponse({"status": "succeeded"}, status_code=200)

    async def step_three_handler(request):
        body = await request.body()
        received_requests.append({"path": "/invoices", "body": body.decode()})
        return JSONResponse({"invoice_id": "inv_999"}, status_code=200)

    app = Starlette(
        routes=[
            Route("/orders", step_one_handler, methods=["POST"]),
            Route("/payments", step_two_handler, methods=["POST"]),
            Route("/invoices", step_three_handler, methods=["POST"]),
        ]
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testreceiver") as client:
        # Create scenario in DB
        scenario_data = {
            "channel_id": "chan_exec_test",
            "name": "Order Fulfillment Sequence",
            "target_url": "http://testreceiver",
            "delay_between_steps_ms": 10,
        }
        steps = [
            {
                "name": "Create Order",
                "method": "POST",
                "path_suffix": "orders",
                "payload_raw": '{"customer": "alex"}',
                "expected_status": 201,
            },
            {
                "name": "Charge Customer",
                "method": "POST",
                "path_suffix": "payments",
                "payload_raw": '{"amount": 5000}',
                "expected_status": 200,
            },
            {
                "name": "Generate Invoice",
                "method": "POST",
                "path_suffix": "invoices",
                "payload_raw": '{"format": "pdf"}',
                "expected_status": 200,
            },
        ]

        created = await create_scenario(temp_db, scenario_data, steps=steps)

        # Mock WebSocket manager to verify broadcast calls
        mock_ws = AsyncMock()
        runner = ScenarioRunner(connection_manager=mock_ws)

        result: ScenarioRunResult = await runner.run(
            db_path=temp_db,
            scenario_id=created["id"],
            client=client,
        )

        assert result.success is True
        assert result.total_steps == 3
        assert result.passed_steps == 3
        assert result.failed_steps == 0
        assert len(result.step_results) == 3

        for step_res in result.step_results:
            assert step_res.passed is True
            assert step_res.actual_status == step_res.expected_status
            assert step_res.latency_ms >= 0

        # Verify all 3 routes received the requests in order
        assert len(received_requests) == 3
        assert received_requests[0]["path"] == "/orders"
        assert received_requests[1]["path"] == "/payments"
        assert received_requests[2]["path"] == "/invoices"

        # Verify WebSocket events
        event_names = [call.args[1]["event"] for call in mock_ws.broadcast.call_args_list]
        assert "scenario_run_started" in event_names
        assert event_names.count("scenario_step_completed") == 3
        assert "scenario_run_completed" in event_names


@pytest.mark.asyncio
async def test_scenario_runner_assertion_failure(temp_db):
    """Test scenario step failure when receiver returns unexpected status code."""

    async def fail_handler(request):
        return JSONResponse({"error": "Bad Request"}, status_code=400)

    app = Starlette(
        routes=[
            Route("/broken", fail_handler, methods=["POST"]),
        ]
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testreceiver") as client:
        scenario = await create_scenario(
            temp_db,
            {
                "channel_id": "chan_fail",
                "name": "Failing Sequence",
                "target_url": "http://testreceiver",
                "delay_between_steps_ms": 0,
            },
            steps=[
                {
                    "name": "Expect 200 but Get 400",
                    "method": "POST",
                    "path_suffix": "broken",
                    "payload_raw": "{}",
                    "expected_status": 200,
                }
            ],
        )

        result = await scenario_runner.run(
            db_path=temp_db,
            scenario_id=scenario["id"],
            client=client,
        )

        assert result.success is False
        assert result.passed_steps == 0
        assert result.failed_steps == 1
        assert result.step_results[0].passed is False
        assert result.step_results[0].actual_status == 400
        assert result.step_results[0].expected_status == 200


@pytest.mark.asyncio
async def test_scenarios_api_endpoints(temp_db):
    """Test REST API routes for scenarios management and execution."""
    app = create_app(db_path=temp_db)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create scenario
        create_resp = await client.post(
            "/api/scenarios",
            json={
                "channel_id": "api_test_channel",
                "name": "API Scenario",
                "description": "Created via REST API",
                "target_url": "http://example.com/api",
                "delay_between_steps_ms": 50,
                "steps": [
                    {
                        "name": "Step One",
                        "method": "POST",
                        "path_suffix": "v1/step",
                        "payload_raw": '{"test": 1}',
                        "expected_status": 200,
                    }
                ],
            },
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        scen_id = data["id"]
        assert data["name"] == "API Scenario"
        assert len(data["steps"]) == 1

        # 2. Get scenario
        get_resp = await client.get(f"/api/scenarios/{scen_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == scen_id

        # 3. List scenarios
        list_resp = await client.get("/api/scenarios", params={"channel_id": "api_test_channel"})
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1

        # 4. Add Step
        add_step_resp = await client.post(
            f"/api/scenarios/{scen_id}/steps",
            json={
                "name": "Step Two",
                "method": "POST",
                "path_suffix": "v1/step2",
                "payload_raw": '{"test": 2}',
                "expected_status": 200,
            },
        )
        assert add_step_resp.status_code == 201
        step_id = add_step_resp.json()["id"]

        # 5. Delete Step
        del_step_resp = await client.delete(f"/api/scenarios/{scen_id}/steps/{step_id}")
        assert del_step_resp.status_code == 200

        # 6. Delete scenario
        del_resp = await client.delete(f"/api/scenarios/{scen_id}")
        assert del_resp.status_code == 200

        # 7. Confirm 404 after delete
        not_found = await client.get(f"/api/scenarios/{scen_id}")
        assert not_found.status_code == 404
