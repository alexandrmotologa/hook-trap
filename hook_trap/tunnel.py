import logging
import re
import shutil
import subprocess
import threading
import time

logger = logging.getLogger("hook_trap.tunnel")


class TunnelManager:
    """Manages quick public HTTPS tunnels via cloudflared or ngrok."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.public_url: str | None = None

    def start(self, host: str, port: int, provider: str = "cloudflare") -> str | None:
        """Start a public tunnel if the requested provider is installed."""
        target_host = "127.0.0.1" if host in ("0.0.0.0", "") else host

        if provider in ("cloudflare", "auto"):
            cf_bin = shutil.which("cloudflared")
            if cf_bin:
                return self._start_cloudflared(cf_bin, target_host, port)

        if provider in ("ngrok", "auto"):
            ngrok_bin = shutil.which("ngrok")
            if ngrok_bin:
                return self._start_ngrok(ngrok_bin, port)

        logger.info(
            "Tunnel binary not found for %s. Install cloudflared "
            "(e.g. winget install Cloudflare.cloudflared) "
            "or ngrok to enable public HTTPS URLs.",
            provider,
        )
        return None

    def _start_cloudflared(self, binary_path: str, host: str, port: int) -> str | None:
        cmd = [binary_path, "tunnel", "--url", f"http://{host}:{port}"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            # Read stderr/stdout until the trycloudflare URL appears
            found_url: str | None = None
            url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

            def reader():
                nonlocal found_url
                for line in self.process.stdout:
                    match = url_pattern.search(line)
                    if match and not found_url:
                        found_url = match.group(0)
                        self.public_url = found_url

            t = threading.Thread(target=reader, daemon=True)
            t.start()

            # Wait up to 10 seconds for the URL to be issued
            start = time.time()
            while time.time() - start < 10.0:
                if found_url:
                    return found_url
                time.sleep(0.2)

            return found_url
        except Exception as exc:
            logger.warning("Failed to start cloudflared tunnel: %s", exc)
            return None

    def _start_ngrok(self, binary_path: str, port: int) -> str | None:
        import json
        import urllib.request

        cmd = [binary_path, "http", str(port)]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2.0)
            req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode())
                for tun in data.get("tunnels", []):
                    if tun.get("public_url", "").startswith("https"):
                        self.public_url = tun["public_url"]
                        return self.public_url
            return None
        except Exception as exc:
            logger.warning("Failed to start ngrok tunnel: %s", exc)
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


tunnel_manager = TunnelManager()
