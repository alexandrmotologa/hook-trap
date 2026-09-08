import json
import logging
import shutil
import subprocess
import time
import urllib.request

from hook_trap.services.tunnel.base import BaseTunnelProvider

logger = logging.getLogger("hook_trap.tunnel.ngrok")


class NgrokTunnelProvider(BaseTunnelProvider):
    """Tunnel provider using ngrok binary."""

    def __init__(self) -> None:
        self._binary: str | None = None

    def is_available(self) -> bool:
        self._binary = shutil.which("ngrok")
        return self._binary is not None

    def start(self, host: str, port: int) -> tuple[subprocess.Popen | None, str | None]:
        if not self._binary and not self.is_available():
            return None, None

        cmd = [self._binary, "http", str(port)]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2.0)
            req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode())
                for tun in data.get("tunnels", []):
                    public_url = tun.get("public_url", "")
                    if public_url.startswith("https"):
                        return process, public_url
            return process, None
        except Exception as exc:
            logger.warning("Failed to start ngrok tunnel: %s", exc)
            return None, None
