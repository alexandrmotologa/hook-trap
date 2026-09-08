import logging
import re
import shutil
import subprocess
import threading
import time

from hook_trap.services.tunnel.base import BaseTunnelProvider

logger = logging.getLogger("hook_trap.tunnel.cloudflare")


class CloudflareTunnelProvider(BaseTunnelProvider):
    """Tunnel provider using cloudflared quick tunnels."""

    def __init__(self) -> None:
        self._binary: str | None = None

    def is_available(self) -> bool:
        self._binary = shutil.which("cloudflared")
        return self._binary is not None

    def start(self, host: str, port: int) -> tuple[subprocess.Popen | None, str | None]:
        if not self._binary and not self.is_available():
            return None, None

        cmd = [self._binary, "tunnel", "--url", f"http://{host}:{port}"]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            found_url: str | None = None
            url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

            def reader() -> None:
                nonlocal found_url
                if process.stdout:
                    for line in process.stdout:
                        match = url_pattern.search(line)
                        if match and not found_url:
                            found_url = match.group(0)

            thread = threading.Thread(target=reader, daemon=True)
            thread.start()

            start_wait = time.time()
            while time.time() - start_wait < 10.0:
                if found_url:
                    return process, found_url
                time.sleep(0.2)

            return process, found_url
        except Exception as exc:
            logger.warning("Failed to start cloudflared tunnel: %s", exc)
            return None, None
