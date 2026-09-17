import asyncio
import json
import sys
import webbrowser
from typing import Any

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from hook_trap.config import settings
from hook_trap.server import create_app
from hook_trap.tunnel import tunnel_manager

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

cli = typer.Typer(
    name="hook-trap",
    help="Real-Time Webhook Inspector & Local Forwarder",
    add_completion=False,
)
console = Console()


class CliRenderer:
    """Handles formatted terminal outputs, banners, and real-time streaming displays."""

    def __init__(self, console_instance: Console | None = None) -> None:
        self.console = console_instance or console
        self._method_styles = {
            "POST": "bold green",
            "GET": "bold blue",
            "PUT": "bold yellow",
            "PATCH": "bold yellow",
            "DELETE": "bold red",
        }

    def print_banner(
        self,
        host: str,
        port: int,
        db_path: str,
        auto_forward: str | None,
        tunnel_url: str | None = None,
    ) -> None:
        """Render startup dashboard info using Rich."""
        title = Text("HOOK-TRAP", style="bold cyan")

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold white", justify="right")
        grid.add_column(style="green")

        grid.add_row("Dashboard UI:", f"http://{host}:{port}/")
        grid.add_row("Webhook Ingestion:", f"http://{host}:{port}/catch/<channel_id>")
        if tunnel_url:
            grid.add_row("Public Tunnel:", f"{tunnel_url}/catch/<channel_id>")
        grid.add_row("SQLite Database:", db_path)
        grid.add_row(
            "Auto-Forward Target:", auto_forward if auto_forward else "[dim]Disabled[/dim]"
        )

        panel = Panel(
            grid,
            title=title,
            subtitle="[dim]Press CTRL+C to stop the server[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print(panel)

    def render_tail_request(self, req: dict[str, Any], show_headers: bool = False) -> None:
        """Render captured request summary in the live tail CLI output."""
        method = (req.get("method") or "POST").upper()
        method_style = self._method_styles.get(method, "bold white")
        path = req.get("path", "")
        ts = req.get("timestamp", "")[:19]
        size = req.get("body_size", 0)
        ip = req.get("client_ip", "127.0.0.1")

        self.console.print(
            f"[{method_style}]{method}[/{method_style}] [bold white]{path}[/bold white] "
            f"[dim]{size} B &bull; {ip} &bull; {ts}[/dim]"
        )

        if show_headers and req.get("headers"):
            tbl = Table(title="Headers", show_header=True, header_style="bold dim", padding=(0, 1))
            tbl.add_column("Header")
            tbl.add_column("Value")
            for k, v in req["headers"].items():
                tbl.add_row(k, v)
            self.console.print(tbl)

        body = req.get("body")
        if body:
            if isinstance(body, (dict, list)):
                json_str = json.dumps(body, indent=2)
                self.console.print(Syntax(json_str, "json", theme="monokai", line_numbers=False))
            else:
                self.console.print(f"[dim]{str(body)[:500]}[/dim]")
        self.console.print()

    def render_replay_event(self, rep: dict[str, Any]) -> None:
        """Render replay execution result in terminal."""
        status = rep.get("status_code", "ERR")
        lat = rep.get("latency_ms", 0)
        target = rep.get("target_url", "")
        self.console.print(
            f"  [bold magenta]↳ REPLAY[/bold magenta] [cyan]{target}[/cyan] "
            f"[bold green]{status} OK[/bold green] ({lat} ms)\n"
        )


renderer = CliRenderer(console)


# Keep module-level backward compatibility for print_banner and _render_tail_request
def print_banner(
    host: str,
    port: int,
    db_path: str,
    auto_forward: str | None,
    tunnel_url: str | None = None,
) -> None:
    renderer.print_banner(host, port, db_path, auto_forward, tunnel_url)


def _render_tail_request(req: dict[str, Any], show_headers: bool = False) -> None:
    renderer.render_tail_request(req, show_headers=show_headers)


@cli.command(name="serve")
def serve(
    port: int = typer.Option(8080, "-p", "--port", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "-h", "--host", help="Network host interface"),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
    auto_forward: str | None = typer.Option(
        None, "-f", "--auto-forward", help="Default target URL to auto-forward incoming webhooks"
    ),
    open_browser: bool = typer.Option(
        False, "-b", "--open-browser", help="Automatically open browser dashboard upon startup"
    ),
    tunnel: str | None = typer.Option(
        None,
        "-t",
        "--tunnel",
        help="Start a public HTTPS tunnel (e.g. 'cloudflare', 'ngrok', or 'auto')",
    ),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level"),
) -> None:
    """Launch the hook-trap inspector and forwarding proxy server."""
    settings.host = host
    settings.port = port
    settings.db_path = db_path
    if auto_forward:
        settings.default_auto_forward_url = auto_forward

    public_url = None
    if tunnel:
        console.print(f"[dim]Starting {tunnel} tunnel...[/dim]")
        public_url = tunnel_manager.start(host, port, provider=tunnel)
        if public_url:
            settings.public_tunnel_url = public_url
        else:
            console.print(
                "[yellow]Could not establish public tunnel. Falling back to local.[/yellow]"
            )

    renderer.print_banner(
        host=host,
        port=port,
        db_path=db_path,
        auto_forward=auto_forward,
        tunnel_url=public_url,
    )

    if open_browser:
        target_url = f"http://{host}:{port}/"
        try:
            webbrowser.open(target_url)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[dim]Could not auto-open browser: {exc}[/dim]")

    app = create_app(db_path=db_path, default_auto_forward_url=auto_forward)

    uvicorn_log_level = log_level.lower()
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=uvicorn_log_level,
        )
    finally:
        tunnel_manager.stop()


def _read_char() -> str:
    """Read a single character from terminal non-blockingly."""
    try:
        import msvcrt

        if msvcrt.kbhit():
            ch = msvcrt.getch()
            return ch.decode("utf-8", errors="ignore").lower()
        return ""
    except ImportError:
        import select
        import termios
        import tty

        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return ""
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1).lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


@cli.command(name="tail")
def tail(
    channel_id: str = typer.Argument(..., help="Channel identifier to stream"),
    host: str = typer.Option("127.0.0.1", "-h", "--host", help="Server host"),
    port: int = typer.Option(8080, "-p", "--port", help="Server port"),
    show_headers: bool = typer.Option(False, "--headers", help="Display all request headers"),
    raw: bool = typer.Option(False, "--raw", help="Output raw JSON messages"),
    interactive: bool = typer.Option(
        True,
        "-i",
        "--interactive/--no-interactive",
        help="Enable interactive terminal shortcuts (r=replay, b=burst, c=clear, q=quit)",
    ),
) -> None:
    """Stream incoming webhooks live in the terminal."""
    import httpx
    import websockets

    ws_url = f"ws://{host}:{port}/ws/{channel_id}"
    console.print(f"[bold cyan]Connecting to live stream on {ws_url}...[/bold cyan]")

    use_interactive = interactive and sys.stdin.isatty() and not raw
    if use_interactive:
        console.print(
            "[dim]Interactive mode enabled: [bold cyan]r[/bold cyan]=Replay "
            "[bold magenta]b[/bold magenta]=Burst (5x) [bold]c[/bold]=Clear "
            "[bold red]q[/bold red]=Quit[/dim]\n"
        )
    else:
        console.print("[dim]Listening for incoming webhooks. Press CTRL+C to exit.[/dim]\n")

    state = {
        "last_request_id": None,
        "last_target_url": "http://localhost:3000/api/webhook",
        "stop": False,
    }

    async def run_tail() -> None:
        # Attempt to pre-fetch channel auto-forward URL
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                cfg_resp = await client.get(f"http://{host}:{port}/api/channels/{channel_id}/config")
                if cfg_resp.status_code == 200:
                    cfg_data = cfg_resp.json()
                    if cfg_data.get("auto_forward_url"):
                        state["last_target_url"] = cfg_data["auto_forward_url"]
        except Exception:
            pass

        async def key_loop() -> None:
            loop = asyncio.get_running_loop()
            while not state["stop"]:
                key = await loop.run_in_executor(None, _read_char)
                if not key:
                    await asyncio.sleep(0.08)
                    continue

                if key == "q":
                    state["stop"] = True
                    break
                elif key == "c":
                    console.clear()
                    console.print(
                        f"[bold cyan]hook-trap tail: channel {channel_id}[/bold cyan]\n"
                    )
                elif key in ("?", "h"):
                    console.print(
                        "\n[dim]Shortcuts: [bold cyan]r[/bold cyan]=Replay "
                        "[bold magenta]b[/bold magenta]=Burst 5x [bold]c[/bold]=Clear "
                        "[bold red]q[/bold red]=Quit[/dim]\n"
                    )
                elif key == "r":
                    req_id = state.get("last_request_id")
                    if not req_id:
                        console.print("[yellow]! No webhook captured yet to replay.[/yellow]")
                        continue
                    tgt = state.get("last_target_url")
                    console.print(f"[cyan]⚡ Replaying {req_id[:8]} -> {tgt}...[/cyan]")
                    try:
                        api_url = (
                            f"http://{host}:{port}/api/channels/{channel_id}"
                            f"/requests/{req_id}/replay"
                        )
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            resp = await client.post(api_url, json={"target_url": tgt})
                            if resp.status_code == 200:
                                renderer.render_replay_event(resp.json())
                            else:
                                console.print(
                                    f"[red]Replay failed ({resp.status_code}): {resp.text}[/red]"
                                )
                    except Exception as exc:
                        console.print(f"[red]Replay execution error: {exc}[/red]")
                elif key == "b":
                    req_id = state.get("last_request_id")
                    if not req_id:
                        console.print("[yellow]! No webhook captured yet to burst.[/yellow]")
                        continue
                    tgt = state.get("last_target_url")
                    console.print(
                        f"[magenta]⚡ Firing 5x burst for {req_id[:8]} -> {tgt}...[/magenta]"
                    )
                    try:
                        api_url = (
                            f"http://{host}:{port}/api/channels/{channel_id}"
                            f"/requests/{req_id}/burst"
                        )
                        async with httpx.AsyncClient(timeout=15.0) as client:
                            resp = await client.post(
                                api_url,
                                json={"target_url": tgt, "count": 5, "concurrency": 5},
                            )
                            if resp.status_code == 200:
                                bdata = resp.json()
                                s_cnt = bdata.get("success_count")
                                tot = bdata.get("total")
                                verdict = bdata.get("idempotency_verdict")
                                avg_lat = bdata.get("avg_latency_ms")
                                console.print(
                                    f"  [bold magenta]↳ BURST[/bold magenta] {s_cnt}/{tot} ok "
                                    f"&bull; [bold green]{verdict}[/bold green] "
                                    f"&bull; avg {avg_lat} ms\n"
                                )
                            else:
                                console.print(
                                    f"[red]Burst failed ({resp.status_code}): {resp.text}[/red]"
                                )
                    except Exception as exc:
                        console.print(f"[red]Burst execution error: {exc}[/red]")

        async def ws_loop() -> None:
            try:
                async with websockets.connect(ws_url) as ws:
                    while not state["stop"]:
                        try:
                            msg_text = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        except TimeoutError:
                            continue

                        try:
                            data = json.loads(msg_text)
                        except json.JSONDecodeError:
                            continue

                        if raw:
                            console.print(msg_text)
                            continue

                        event = data.get("event")
                        if event == "connected":
                            console.print(
                                f"[green]Connected to channel [bold]{channel_id}[/bold][/green]\n"
                            )
                        elif event == "new_request":
                            req = data.get("data", {})
                            state["last_request_id"] = req.get("id")
                            renderer.render_tail_request(req, show_headers=show_headers)
                        elif event == "replay_executed":
                            rep = data.get("data", {})
                            if rep.get("target_url"):
                                state["last_target_url"] = rep["target_url"]
                            renderer.render_replay_event(rep)
                        elif event == "ping":
                            await ws.send("pong")
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            except Exception as exc:  # noqa: BLE001
                if not state["stop"]:
                    console.print(f"[red]Connection error: {exc}[/red]")

        tasks = [asyncio.create_task(ws_loop())]
        if use_interactive:
            tasks.append(asyncio.create_task(key_loop()))

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    try:
        asyncio.run(run_tail())
    except KeyboardInterrupt:
        pass
    finally:
        console.print("\n[dim]Disconnected.[/dim]")


@cli.callback(invoke_without_command=True)
def default_callback(ctx: typer.Context) -> None:
    """If no subcommand is given, default to running the server."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
