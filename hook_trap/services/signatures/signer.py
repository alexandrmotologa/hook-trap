import base64
import hashlib
import hmac
import time


class SignatureSigner:
    """Calculates valid HMAC signature headers with fresh timestamps for replaying webhooks."""

    def sign(
        self,
        provider: str,
        secret: str | bytes,
        payload: str | bytes,
        timestamp: int | None = None,
    ) -> tuple[str, str]:
        """
        Generate signature header name and value for a given provider and payload.

        Returns (header_name, header_value).
        """
        provider_key = (provider or "generic").lower().strip()
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
        payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)

        if provider_key in ("stripe",):
            ts = timestamp if timestamp is not None else int(time.time())
            signed_payload = f"{ts}.".encode() + payload_bytes
            sig = hmac.new(secret_bytes, signed_payload, hashlib.sha256).hexdigest()
            return ("Stripe-Signature", f"t={ts},v1={sig}")

        if provider_key in ("github",):
            sig = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
            return ("X-Hub-Signature-256", f"sha256={sig}")

        if provider_key in ("shopify",):
            digest = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).digest()
            sig = base64.b64encode(digest).decode("utf-8")
            return ("X-Shopify-Hmac-Sha256", sig)

        if provider_key in ("generic_sha1",):
            sig = hmac.new(secret_bytes, payload_bytes, hashlib.sha1).hexdigest()
            return ("X-Signature", sig)

        # Default: generic_sha256 / generic
        sig = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
        return ("X-Signature", sig)


signature_signer = SignatureSigner()
