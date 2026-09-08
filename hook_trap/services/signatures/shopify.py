import base64
import hashlib
import hmac

from hook_trap.models import SignatureVerifyRequest, SignatureVerifyResponse
from hook_trap.services.signatures.base import BaseSignatureVerifier


class ShopifySignatureVerifier(BaseSignatureVerifier):
    """Verifier for Shopify webhook signatures (Base64-encoded HMAC-SHA256)."""

    def verify(self, request: SignatureVerifyRequest) -> SignatureVerifyResponse:
        secret_bytes = request.secret.encode("utf-8")
        payload_bytes = request.raw_payload.encode("utf-8")
        sig_header = request.signature_header.strip()

        expected = base64.b64encode(
            hmac.new(secret_bytes, payload_bytes, hashlib.sha256).digest()
        ).decode("utf-8")
        matched = hmac.compare_digest(expected, sig_header)

        return SignatureVerifyResponse(
            valid=matched,
            message="Shopify signature matched" if matched else "Shopify signature mismatch",
            details={"computed": expected, "provided": sig_header},
        )
