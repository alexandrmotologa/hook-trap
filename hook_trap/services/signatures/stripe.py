import hashlib
import hmac

from hook_trap.models import SignatureVerifyRequest, SignatureVerifyResponse
from hook_trap.services.signatures.base import BaseSignatureVerifier


class StripeSignatureVerifier(BaseSignatureVerifier):
    """Verifier for Stripe webhook signatures (t=...,v1=... format)."""

    def verify(self, request: SignatureVerifyRequest) -> SignatureVerifyResponse:
        secret_bytes = request.secret.encode("utf-8")
        payload_bytes = request.raw_payload.encode("utf-8")
        sig_header = request.signature_header.strip()

        # Format: t=1614000000,v1=abc...,v0=...
        parts: dict[str, list[str]] = {}
        for item in sig_header.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                parts.setdefault(k.strip(), []).append(v.strip())

        timestamps = parts.get("t", [])
        v1_signatures = parts.get("v1", [])

        if not timestamps or not v1_signatures:
            return SignatureVerifyResponse(
                valid=False,
                message="Missing t= or v1= parts in Stripe-Signature header",
                details={"parsed_parts": str(list(parts.keys()))},
            )

        ts = request.timestamp or timestamps[0]
        signed_payload = f"{ts}.".encode() + payload_bytes
        expected = hmac.new(secret_bytes, signed_payload, hashlib.sha256).hexdigest()

        matched = any(hmac.compare_digest(expected, s) for s in v1_signatures)
        return SignatureVerifyResponse(
            valid=matched,
            message="Stripe signature matched" if matched else "Stripe signature mismatch",
            details={"computed": expected, "provided": ", ".join(v1_signatures), "timestamp": ts},
        )
