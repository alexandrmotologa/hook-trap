import hashlib
import hmac

import pytest
from httpx import ASGITransport, AsyncClient

from hook_trap.database import init_db
from hook_trap.server import create_app


@pytest.fixture
async def app_client(tmp_path):
    db_path = str(tmp_path / "test_sig.db")
    await init_db(db_path)
    app = create_app(db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_stripe_signature_verification(app_client):
    secret = "whsec_test_secret_123"
    payload = '{"event": "charge.succeeded"}'
    ts = "1620000000"
    signed_payload = f"{ts}.".encode() + payload.encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    header = f"t={ts},v1={expected_sig}"

    # Valid
    resp = await app_client.post(
        "/api/verify-signature",
        json={
            "provider": "stripe",
            "secret": secret,
            "signature_header": header,
            "raw_payload": payload,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True

    # Invalid secret
    resp_invalid = await app_client.post(
        "/api/verify-signature",
        json={
            "provider": "stripe",
            "secret": "wrong_secret",
            "signature_header": header,
            "raw_payload": payload,
        },
    )
    assert resp_invalid.json()["valid"] is False


@pytest.mark.asyncio
async def test_github_signature_verification(app_client):
    secret = "gh_secret_xyz"
    payload = '{"action": "opened"}'
    expected_sig = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    header = f"sha256={expected_sig}"

    resp = await app_client.post(
        "/api/verify-signature",
        json={
            "provider": "github",
            "secret": secret,
            "signature_header": header,
            "raw_payload": payload,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
