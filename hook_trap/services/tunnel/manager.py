import logging
import subprocess

from hook_trap.services.tunnel.base import BaseTunnelProvider
from hook_trap.services.tunnel.cloudflare import CloudflareTunnelProvider
from hook_trap.services.tunnel.ngrok import NgrokTunnelProvider

logger = logging.getLogger("hook_trap.tunnel.manager")


class TunnelManager:
    """Coordinates public HTTPS tunnel providers and process lifecycles."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.public_url: str | None = None
        self._providers: dict[str, BaseTunnelProvider] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("cloudflare", CloudflareTunnelProvider())
        self.register("ngrok", NgrokTunnelProvider())

    def register(self, name: str, provider: BaseTunnelProvider) -> None:
        """Register a tunnel provider strategy."""
        self._providers[name.lower().strip()] = provider

    def start(self, host: str, port: int, provider: str = "cloudflare") -> str | None:
        """Start a public tunnel using the requested or first available provider."""
        target_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
        provider_name = provider.lower().strip()

        # Try specific provider or auto-detection
        candidate_names = ["cloudflare", "ngrok"] if provider_name == "auto" else [provider_name]

        for name in candidate_names:
            prov = self._providers.get(name)
            if prov and prov.is_available():
                proc, url = prov.start(target_host, port)
                if url:
                    self.process = proc
                    self.public_url = url
                    return url

        logger.info(
            "Tunnel binary not found for %s. Install cloudflared "
            "(e.g. winget install Cloudflare.cloudflared) "
            "or ngrok to enable public HTTPS URLs.",
            provider,
        )
        return None

    def stop(self) -> None:
        """Terminate the active tunnel process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                pass
            self.process = None
        self.public_url = None


# Default singleton instance
tunnel_manager = TunnelManager()
