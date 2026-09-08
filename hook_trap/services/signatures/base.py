from abc import ABC, abstractmethod

from hook_trap.models import SignatureVerifyRequest, SignatureVerifyResponse


class BaseSignatureVerifier(ABC):
    """Abstract strategy for webhook HMAC signature verification."""

    @abstractmethod
    def verify(self, request: SignatureVerifyRequest) -> SignatureVerifyResponse:
        """Verify the signature in the request against the raw payload and secret."""
