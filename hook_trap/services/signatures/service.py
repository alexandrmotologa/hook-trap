from hook_trap.models import SignatureProvider, SignatureVerifyRequest, SignatureVerifyResponse
from hook_trap.services.signatures.base import BaseSignatureVerifier
from hook_trap.services.signatures.generic import GenericHmacVerifier
from hook_trap.services.signatures.github import GitHubSignatureVerifier
from hook_trap.services.signatures.shopify import ShopifySignatureVerifier
from hook_trap.services.signatures.stripe import StripeSignatureVerifier


class SignatureVerificationService:
    """Service orchestrating signature verification using registered strategies."""

    def __init__(self) -> None:
        self._verifiers: dict[str, BaseSignatureVerifier] = {}
        self._default_verifier = GenericHmacVerifier("sha256")
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(SignatureProvider.STRIPE, StripeSignatureVerifier())
        self.register(SignatureProvider.GITHUB, GitHubSignatureVerifier())
        self.register(SignatureProvider.SHOPIFY, ShopifySignatureVerifier())
        self.register(SignatureProvider.GENERIC_SHA256, GenericHmacVerifier("sha256"))
        self.register(SignatureProvider.GENERIC_SHA1, GenericHmacVerifier("sha1"))

    def register(self, provider: str, verifier: BaseSignatureVerifier) -> None:
        """Register a new signature verification strategy for a provider name."""
        self._verifiers[provider.lower().strip()] = verifier

    def verify(self, request: SignatureVerifyRequest) -> SignatureVerifyResponse:
        """Verify request signature using the appropriate provider strategy."""
        provider_key = request.provider.lower().strip()
        verifier = self._verifiers.get(provider_key, self._default_verifier)
        return verifier.verify(request)


# Default singleton instance
signature_verification_service = SignatureVerificationService()
