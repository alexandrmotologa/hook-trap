import hashlib
import hmac

from hook_trap.models import SignatureVerifyRequest, SignatureVerifyResponse
from hook_trap.services.signatures.base import BaseSignatureVerifier


class GitHubSignatureVerifier(BaseSignatureVerifier):
    """Verifier for GitHub webhook signatures (sha256=... or legacy sha1=...)."""

    def verify(self, request: SignatureVerifyRequest) -> SignatureVerifyResponse:
        secret_bytes = request.secret.encode("utf-8")
        payload_bytes = request.raw_payload.encode("utf-8")
        sig_header = request.signature_header.strip()

        hash_func = hashlib.sha256
        prefix = "sha256="
        if sig_header.startswith("sha1="):
            hash_func = hashlib.sha1
            prefix = "sha1="

        provided_sig = sig_header.removeprefix(prefix)
        expected = hmac.new(secret_bytes, payload_bytes, hash_func).hexdigest()
        matched = hmac.compare_digest(expected, provided_sig)

        return SignatureVerifyResponse(
            valid=matched,
            message="GitHub signature matched" if matched else "GitHub signature mismatch",
            details={"computed": f"{prefix}{expected}", "provided": sig_header},
        )
