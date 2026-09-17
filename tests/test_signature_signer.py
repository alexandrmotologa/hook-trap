from hook_trap.models import SignatureVerifyRequest
from hook_trap.services.signatures.generic import GenericHmacVerifier
from hook_trap.services.signatures.github import GitHubSignatureVerifier
from hook_trap.services.signatures.shopify import ShopifySignatureVerifier
from hook_trap.services.signatures.signer import SignatureSigner
from hook_trap.services.signatures.stripe import StripeSignatureVerifier


def test_stripe_signature_generation_and_verification():
    signer = SignatureSigner()
    verifier = StripeSignatureVerifier()

    secret = "whsec_test_secret_12345"
    payload = '{"id": "evt_test", "object": "event"}'

    header_name, header_value = signer.sign("stripe", secret, payload, timestamp=1700000000)
    assert header_name == "Stripe-Signature"
    assert "t=1700000000" in header_value
    assert "v1=" in header_value

    req = SignatureVerifyRequest(
        provider="stripe",
        secret=secret,
        signature_header=header_value,
        raw_payload=payload,
    )
    res = verifier.verify(req)
    assert res.valid is True
    assert "matched" in res.message


def test_github_signature_generation_and_verification():
    signer = SignatureSigner()
    verifier = GitHubSignatureVerifier()

    secret = "github_webhook_secret_xyz"
    payload = '{"ref": "refs/heads/main", "action": "push"}'

    header_name, header_value = signer.sign("github", secret, payload)
    assert header_name == "X-Hub-Signature-256"
    assert header_value.startswith("sha256=")

    req = SignatureVerifyRequest(
        provider="github",
        secret=secret,
        signature_header=header_value,
        raw_payload=payload,
    )
    res = verifier.verify(req)
    assert res.valid is True
    assert "matched" in res.message


def test_shopify_signature_generation_and_verification():
    signer = SignatureSigner()
    verifier = ShopifySignatureVerifier()

    secret = "shpss_test_shopify_secret"
    payload = '{"id": 999999, "total_price": "100.00"}'

    header_name, header_value = signer.sign("shopify", secret, payload)
    assert header_name == "X-Shopify-Hmac-Sha256"

    req = SignatureVerifyRequest(
        provider="shopify",
        secret=secret,
        signature_header=header_value,
        raw_payload=payload,
    )
    res = verifier.verify(req)
    assert res.valid is True
    assert "matched" in res.message


def test_generic_signature_generation_and_verification():
    signer = SignatureSigner()
    verifier = GenericHmacVerifier(algorithm="sha256")

    secret = "my_custom_secret"
    payload = "test message content"

    header_name, header_value = signer.sign("generic", secret, payload)
    assert header_name == "X-Signature"

    req = SignatureVerifyRequest(
        provider="generic",
        secret=secret,
        signature_header=header_value,
        raw_payload=payload,
    )
    res = verifier.verify(req)
    assert res.valid is True
    assert "matched" in res.message
