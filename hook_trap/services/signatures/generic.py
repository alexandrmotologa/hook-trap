import hashlib
import hmac

from hook_trap.models import SignatureVerifyRequest, SignatureVerifyResponse
from hook_trap.services.signatures.base import BaseSignatureVerifier


class GenericHmacVerifier(BaseSignatureVerifier):
    """Generic HMAC verifier supporting SHA256 and SHA1 algorithms."""

    def __init__(self, algorithm: str = "sha256") -> None:
        self._algorithm = algorithm.lower()

    def verify(self, request: SignatureVerifyRequest) -> SignatureVerifyResponse:
        secret_bytes = request.secret.encode("utf-8")
        payload_bytes = request.raw_payload.encode("utf-8")
        sig_header = request.signature_header.strip()

        hash_func = hashlib.sha1 if self._algorithm in ("sha1", "generic_sha1") else hashlib.sha256
        prefix = f"{self._algorithm}=" if not self._algorithm.startswith("generic_") else ""

        clean_sig = sig_header.lower()
        if clean_sig.startswith(f"{self._algorithm}="):
            clean_sig = clean_sig.removeprefix(f"{self._algorithm}=")
        elif clean_sig.startswith("sha256="):
            clean_sig = clean_sig.removeprefix("sha256=")
        elif clean_sig.startswith("sha1="):
            clean_sig = clean_sig.removeprefix("sha1=")

        expected = hmac.new(secret_bytes, payload_bytes, hash_func).hexdigest()
        matched = hmac.compare_digest(expected, clean_sig)

        return SignatureVerifyResponse(
            valid=matched,
            message=(
                f"HMAC-{self._algorithm.upper()} signature matched"
                if matched
                else "Signature mismatch"
            ),
            details={"computed": f"{prefix}{expected}".strip("="), "provided": sig_header},
        )
