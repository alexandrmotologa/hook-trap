import json
import os

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from hook_trap.database import init_db, insert_webhook_request
from hook_trap.models import (
    FuzzingConfig,
    FuzzMutationType,
    FuzzResilienceGrade,
)
from hook_trap.server import create_app
from hook_trap.services.payload_fuzzer import payload_fuzzer


@pytest.fixture
async def temp_db(tmp_path):
    db_path = str(tmp_path / "test_fuzzer.db")
    await init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_payload_fuzzer_mutation_generation():
    raw_payload = json.dumps(
        {
            "event": "payment_intent.succeeded",
            "amount": 1000,
            "data": {
                "customer_id": "cus_123",
                "is_active": True,
            },
        }
    )
    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": "t=1600000000,v1=9999888877776666555544443333222211110000",
    }

    config = FuzzingConfig(
        enabled_mutations=[
            FuzzMutationType.MISSING_KEY,
            FuzzMutationType.NULL_INJECTION,
            FuzzMutationType.TYPE_CONFUSION,
            FuzzMutationType.CORRUPTED_SIGNATURE,
            FuzzMutationType.MALFORMED_JSON,
        ],
        max_mutations=30,
    )

    cases = payload_fuzzer.generate_mutations(raw_payload, headers, config)
    assert len(cases) > 5

    types_generated = {c.mutation_type for c in cases}
    assert FuzzMutationType.MISSING_KEY in types_generated
    assert FuzzMutationType.NULL_INJECTION in types_generated
    assert FuzzMutationType.TYPE_CONFUSION in types_generated
    assert FuzzMutationType.CORRUPTED_SIGNATURE in types_generated
    assert FuzzMutationType.MALFORMED_JSON in types_generated

    # Check missing key mutation
    missing_key_case = next(c for c in cases if c.mutation_type == FuzzMutationType.MISSING_KEY)
    mutated_obj = json.loads(missing_key_case.mutated_payload)
    # At least one key should be missing compared to original 3 top-level keys + 2 nested keys
    assert (
        "event" not in mutated_obj
        or "amount" not in mutated_obj
        or "customer_id" not in mutated_obj.get("data", {})
    )

    # Check corrupted signature mutation
    sig_case = next(c for c in cases if c.mutation_type == FuzzMutationType.CORRUPTED_SIGNATURE)
    corrupted_sig = sig_case.mutated_headers["Stripe-Signature"]
    assert corrupted_sig != headers["Stripe-Signature"]


def test_payload_fuzzer_resilience_grading():
    # 400 / 422 Graceful validation
    grade, passed, _ = payload_fuzzer.evaluate_resilience(400)
    assert grade == FuzzResilienceGrade.PASSED
    assert passed is True

    grade, passed, _ = payload_fuzzer.evaluate_resilience(422)
    assert grade == FuzzResilienceGrade.PASSED
    assert passed is True

    # 500 / 502 Unhandled Server Error
    grade, passed, _ = payload_fuzzer.evaluate_resilience(500)
    assert grade == FuzzResilienceGrade.VULNERABLE
    assert passed is False

    grade, passed, _ = payload_fuzzer.evaluate_resilience(502)
    assert grade == FuzzResilienceGrade.VULNERABLE
    assert passed is False

    # 200 Accepted invalid/mutated
    grade, passed, _ = payload_fuzzer.evaluate_resilience(200)
    assert grade == FuzzResilienceGrade.ACCEPTED
    assert passed is False

    # Connection crash
    grade, passed, _ = payload_fuzzer.evaluate_resilience(None, error="Connection reset by peer")
    assert grade == FuzzResilienceGrade.VULNERABLE
    assert passed is False


@pytest.mark.asyncio
async def test_payload_fuzzer_execution_against_receiver():
    """Test full fuzz testing execution loop against an ASGI test receiver."""

    async def webhook_receiver(request):
        body = (await request.body()).decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            return JSONResponse({"error": "Malformed JSON"}, status_code=400)

        # Crashes if type confused customer_id is int
        if isinstance(data.get("data", {}).get("customer_id"), int):
            return JSONResponse({"error": "Internal Server Error"}, status_code=500)

        # Graceful 422 if missing required field or null
        if "amount" not in data or data.get("amount") is None:
            return JSONResponse({"error": "Validation failed"}, status_code=422)

        return JSONResponse({"ok": True}, status_code=200)

    app = Starlette(
        routes=[
            Route("/webhook", webhook_receiver, methods=["POST"]),
        ]
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testreceiver") as client:
        payload = json.dumps(
            {
                "amount": 100,
                "data": {"customer_id": "cus_test"},
            }
        )
        headers = {"Content-Type": "application/json"}

        result = await payload_fuzzer.run_fuzz_tests(
            target_url="http://testreceiver/webhook",
            payload_raw=payload,
            headers=headers,
            client=client,
        )

        assert result.total_cases > 0
        assert result.passed_count > 0
        # Should have captured at least one vulnerable 500 crash
        assert result.vulnerable_count >= 1
        assert result.all_passed is False
        assert "Vulnerable" in result.summary


@pytest.mark.asyncio
async def test_fuzzing_api_endpoints(temp_db):
    """Test fuzzing generation and captured request trigger endpoints."""
    app = create_app(db_path=temp_db)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Generate endpoint
        gen_resp = await client.post(
            "/api/scenarios/fuzz/generate",
            json={
                "target_url": "http://localhost:8000",
                "payload_raw": '{"test": "val", "num": 123}',
                "headers": {"Content-Type": "application/json"},
            },
        )
        assert gen_resp.status_code == 200
        cases = gen_resp.json()
        assert len(cases) > 0

        # 2. Insert captured webhook
        req_id = await insert_webhook_request(
            temp_db,
            {
                "channel_id": "fuzz_chan",
                "method": "POST",
                "path": "/catch/fuzz_chan/v1/event",
                "headers": {"Content-Type": "application/json"},
                "body_raw": '{"user_id": 42, "role": "admin"}',
            },
        )

        # 3. Fuzz captured request directly
        from unittest.mock import AsyncMock, patch

        from hook_trap.models import FuzzRunResult

        mock_fuzz_result = FuzzRunResult(
            target_url="http://testreceiver/webhook",
            total_cases=5,
            passed_count=4,
            vulnerable_count=1,
            accepted_count=0,
            error_count=0,
            all_passed=False,
            summary="Fuzz test completed",
            cases=[],
        )

        with patch(
            "hook_trap.routes.scenarios.payload_fuzzer.run_fuzz_tests",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = mock_fuzz_result
            fuzz_resp = await client.post(
                f"/api/channels/fuzz_chan/requests/{req_id}/fuzz",
                json={"target_url": "http://testreceiver/webhook"},
            )
            assert fuzz_resp.status_code == 200
            fuzz_data = fuzz_resp.json()
            assert fuzz_data["total_cases"] == 5
            assert fuzz_data["vulnerable_count"] == 1
            mock_run.assert_awaited_once()

