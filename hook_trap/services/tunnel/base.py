import subprocess
from abc import ABC, abstractmethod


class BaseTunnelProvider(ABC):
    """Abstract strategy for public HTTPS tunnel providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the binary for this tunnel provider is installed on the host."""

    @abstractmethod
    def start(self, host: str, port: int) -> tuple[subprocess.Popen | None, str | None]:
        """Start tunnel process and return (process, public_https_url)."""
