import asyncio
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from hook_trap import __version__
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
        title = Text(f"HOOK-TRAP v{__version__}", style="bold cyan")

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
        ts = str(req.get("timestamp", ""))[:19]
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
                tbl.add_row(k, str(v))
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

    def render_request_list(
        self,
        items: list[dict[str, Any]],
        total: int,
        channel_id: str,
        limit: int,
        offset: int,
    ) -> None:
        """Render a table of captured requests."""
        if not items:
            self.console.print(
                f"[yellow]No webhooks captured yet for channel [bold]{channel_id}[/bold].[/yellow]"
            )
            return

        tbl = Table(
            title=f"Captured Webhooks (Channel: {channel_id} • Showing {len(items)} of {total})",
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        tbl.add_column("ID", style="bold white", width=8)
        tbl.add_column("Method", justify="center", width=6)
        tbl.add_column("Path", style="dim")
        tbl.add_column("Size", justify="right", width=8)
        tbl.add_column("Replays", justify="center", width=7)
        tbl.add_column("Timestamp", style="dim", width=19)

        for item in items:
            req_id = str(item.get("id", ""))[:8]
            m = (item.get("method") or "POST").upper()
            m_style = self._method_styles.get(m, "bold white")
            path = item.get("path", "")
            size = f"{item.get('body_size', 0)} B"
            replays = str(item.get("replay_count", 0))
            ts = str(item.get("timestamp") or "")[:19]

            tbl.add_row(
                req_id,
                f"[{m_style}]{m}[/{m_style}]",
                path,
                size,
                replays,
                ts,
            )

        self.console.print(tbl)

    def render_request_detail(self, detail: dict[str, Any]) -> None:
        """Render full request details including headers, body, and replays."""
        req_id = detail.get("id", "")
        method = (detail.get("method") or "POST").upper()
        path = detail.get("path", "")
        ts = detail.get("timestamp", "")
        ip = detail.get("client_ip", "")
        ct = detail.get("content_type", "n/a")
        replays_count = detail.get("replay_count", 0)

        meta_grid = Table.grid(padding=(0, 2))
        meta_grid.add_column(style="bold cyan", justify="right")
        meta_grid.add_column(style="white")
        meta_grid.add_row("Request ID:", req_id)
        meta_grid.add_row("Method / Path:", f"{method} {path}")
        meta_grid.add_row("Client IP:", ip)
        meta_grid.add_row("Content-Type:", str(ct))
        meta_grid.add_row("Timestamp:", str(ts))
        meta_grid.add_row("Replay Count:", str(replays_count))

        self.console.print(
            Panel(meta_grid, title=f"[bold]Webhook {req_id[:8]}[/bold]", border_style="cyan")
        )

        headers = detail.get("headers") or {}
        if headers:
            tbl = Table(title="Headers", show_header=True, header_style="bold dim")
            tbl.add_column("Header", style="cyan")
            tbl.add_column("Value")
            for k, v in headers.items():
                tbl.add_row(k, str(v))
            self.console.print(tbl)

        body_json = detail.get("body_json")
        body_raw = detail.get("body_raw", "")
        self.console.print("\n[bold]Payload:[/bold]")
        if body_json is not None:
            self.console.print(
                Syntax(json.dumps(body_json, indent=2), "json", theme="monokai", line_numbers=False)
            )
        elif body_raw:
            self.console.print(Syntax(body_raw, "text", theme="monokai", line_numbers=False))
        else:
            self.console.print("[dim](Empty body)[/dim]")

        replays = detail.get("replays") or []
        if replays:
            rep_tbl = Table(title="Replay History", show_header=True, header_style="bold dim")
            rep_tbl.add_column("Target URL")
            rep_tbl.add_column("Status", justify="center")
            rep_tbl.add_column("Latency", justify="right")
            rep_tbl.add_column("Timestamp", style="dim")
            for rep in replays:
                st = rep.get("status_code", "ERR")
                lat = f"{rep.get('latency_ms', 0):.1f} ms"
                st_style = "green" if st == 200 else "red"
                rep_tbl.add_row(
                    rep.get("target_url", ""),
                    f"[{st_style}]{st}[/{st_style}]",
                    lat,
                    str(rep.get("timestamp") or "")[:19],
                )
            self.console.print(rep_tbl)


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
    if interactive:
        console.print(
            "[dim]Interactive mode enabled. Shortcuts: "
            "[bold white]r[/bold white]=replay last, "
            "[bold white]b[/bold white]=burst 5x, "
            "[bold white]c[/bold white]=clear screen, "
            "[bold white]q[/bold white]=quit, "
            "[bold white]?[/bold white]=help[/dim]\n"
        )

    use_interactive = interactive and sys.stdin.isatty()

    async def run_tail() -> None:
        state: dict[str, Any] = {
            "last_request_id": None,
            "last_target_url": f"http://{host}:{port}/api/mock",
            "stop": False,
        }

        async with httpx.AsyncClient(timeout=2.0) as client:
            cfg_resp = await client.get(f"http://{host}:{port}/api/channels/{channel_id}/config")
            if cfg_resp.status_code == 200:
                cfg_data = cfg_resp.json()
                if cfg_data.get("auto_forward_url"):
                    state["last_target_url"] = cfg_data["auto_forward_url"]

        async def key_loop() -> None:
            while not state["stop"]:
                await asyncio.sleep(0.05)
                key = _read_char()
                if not key:
                    continue
                if key == "q":
                    state["stop"] = True
                    break
                elif key == "c":
                    console.clear()
                    console.print(f"[bold cyan]hook-trap tail: channel {channel_id}[/bold cyan]\n")
                elif key in ("?", "h"):
                    console.print(
                        "[dim]Shortcuts: r (replay), b (burst 5x), c (clear), q (quit)[/dim]"
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


@cli.command(name="list")
def list_requests(
    channel_id: str = typer.Argument(..., help="Channel identifier to query"),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
    limit: int = typer.Option(20, "-n", "--limit", help="Maximum requests to list"),
    offset: int = typer.Option(0, "--offset", help="Number of records to skip"),
    method: str | None = typer.Option(None, "-m", "--method", help="Filter by HTTP method"),
    search: str | None = typer.Option(None, "-s", "--search", help="Search query in payload/path"),
) -> None:
    """List captured webhooks for a channel from the database."""
    from hook_trap.database import get_webhook_requests, init_db

    async def _run() -> None:
        await init_db(db_path)
        items, total = await get_webhook_requests(
            db_path=db_path,
            channel_id=channel_id,
            limit=limit,
            offset=offset,
            method=method,
            search=search,
        )
        renderer.render_request_list(items, total, channel_id, limit, offset)

    asyncio.run(_run())


@cli.command(name="show")
def show_request(
    channel_id: str = typer.Argument(..., help="Channel identifier"),
    request_id: str = typer.Argument(..., help="Request identifier"),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
) -> None:
    """Display headers, raw body, and replay logs for a captured webhook."""
    from hook_trap.database import (
        get_replay_logs_for_request,
        get_webhook_request_detail,
        init_db,
    )

    async def _run() -> None:
        await init_db(db_path)
        detail = await get_webhook_request_detail(db_path, channel_id, request_id)
        if not detail:
            console.print(f"[red]Request {request_id} not found in channel {channel_id}.[/red]")
            raise typer.Exit(code=1)
        replays = await get_replay_logs_for_request(db_path, request_id)
        detail["replays"] = replays
        renderer.render_request_detail(detail)

    asyncio.run(_run())


@cli.command(name="replay")
def replay(
    channel_id: str = typer.Argument(..., help="Channel identifier"),
    request_id: str = typer.Argument(..., help="Request identifier"),
    target_url: str = typer.Option(..., "-t", "--target", help="Target URL to forward replay to"),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
    re_sign: bool = typer.Option(False, "--re-sign", help="Recompute fresh HMAC signature headers"),
    provider: str | None = typer.Option(
        None, "--provider", help="Signing provider (stripe, github, shopify, generic)"
    ),
    secret: str | None = typer.Option(None, "--secret", help="HMAC secret key for re-signing"),
    timeout: float = typer.Option(10.0, "--timeout", help="Replay request timeout in seconds"),
) -> None:
    """Replay a captured webhook to a target URL directly from CLI."""
    from hook_trap.database import init_db
    from hook_trap.forwarder import forward_request

    async def _run() -> None:
        await init_db(db_path)
        console.print(f"[cyan]Dispatching replay for {request_id[:8]} -> {target_url}...[/cyan]")
        try:
            result = await forward_request(
                db_path=db_path,
                channel_id=channel_id,
                request_id=request_id,
                target_url=target_url,
                timeout=timeout,
                re_sign=re_sign,
                signing_provider=provider,
                signing_secret=secret,
            )
            renderer.render_replay_event(result)
        except Exception as exc:
            console.print(f"[red]Replay execution failed: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    asyncio.run(_run())


@cli.command(name="trigger")
def trigger(
    channel_id: str = typer.Argument(..., help="Channel identifier"),
    provider: str = typer.Option(
        "stripe-payment",
        "-p",
        "--provider",
        help=(
            "Preset: stripe-payment, stripe-checkout, github-push, "
            "github-pr, shopify-order, slack-challenge, custom"
        ),
    ),
    host: str = typer.Option("127.0.0.1", "-h", "--host", help="Server host"),
    port: int = typer.Option(8080, "-p", "--port", help="Server port"),
) -> None:
    """Send a realistic synthetic sample webhook (Stripe, GitHub, Shopify, Slack) to the channel."""
    import httpx

    from hook_trap.services.samples import get_sample_template

    template = get_sample_template(provider)
    subpath = template.get("subpath", "")
    target = f"http://{host}:{port}/catch/{channel_id}"
    if subpath:
        target = f"{target}/{subpath}"

    headers = dict(template.get("headers", {}))
    body = template.get("body", {})

    console.print(f"[cyan]Sending synthetic '{provider}' webhook to {target}...[/cyan]")
    try:
        resp = httpx.post(target, json=body, headers=headers, timeout=5.0)
        if resp.status_code in (200, 201):
            console.print(
                f"[bold green]✓ Webhook sent successfully! (HTTP {resp.status_code})[/bold green]"
            )
            console.print(f"[dim]{resp.text}[/dim]")
        else:
            console.print(
                f"[yellow]Server responded with HTTP {resp.status_code}: {resp.text}[/yellow]"
            )
    except Exception as exc:
        console.print(f"[red]Failed to connect to {target}: {exc}[/red]")
        raise typer.Exit(code=1) from exc


@cli.command(name="export")
def export(
    channel_id: str = typer.Argument(..., help="Channel identifier"),
    format_name: str = typer.Option(
        "json", "-f", "--format", help="Export format: json, postman, or bruno"
    ),
    output: str | None = typer.Option(
        None, "-o", "--output", help="Output file path (prints to stdout if omitted)"
    ),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
    host: str = typer.Option(
        "127.0.0.1", "-h", "--host", help="Server host for collection base URLs"
    ),
    port: int = typer.Option(8080, "-p", "--port", help="Server port"),
) -> None:
    """Export captured webhooks for a channel to JSON, Postman collection, or Bruno collection."""
    from hook_trap.database import get_all_channel_requests_for_export, init_db
    from hook_trap.services.export import export_service

    async def _run() -> None:
        await init_db(db_path)
        requests = await get_all_channel_requests_for_export(db_path, channel_id)
        if not requests:
            console.print(f"[yellow]No webhooks found for channel {channel_id} to export.[/yellow]")
            return

        base_url = f"http://{host}:{port}"
        resp = export_service.export(
            format_name=format_name,
            channel_id=channel_id,
            requests=requests,
            base_url=base_url,
        )
        content_str = resp.body.decode("utf-8")

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content_str, encoding="utf-8")
            console.print(
                f"[bold green]✓ Successfully exported {len(requests)} requests to "
                f"[cyan]{output}[/cyan][/bold green]"
            )
        else:
            console.print(content_str)

    asyncio.run(_run())


@cli.command(name="clear")
def clear(
    channel_id: str = typer.Argument(..., help="Channel identifier"),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
    force: bool = typer.Option(False, "-f", "--force", help="Bypass confirmation prompt"),
) -> None:
    """Clear all captured webhooks and replay logs for a channel."""
    from hook_trap.database import delete_channel_requests, init_db

    if not force:
        confirm = typer.confirm(
            f"Are you sure you want to delete all captured requests for channel '{channel_id}'?",
            default=False,
        )
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            return

    async def _run() -> None:
        await init_db(db_path)
        deleted = await delete_channel_requests(db_path, channel_id)
        console.print(
            f"[bold green]✓ Cleared channel {channel_id} ({deleted} requests removed).[/bold green]"
        )

    asyncio.run(_run())


def version_callback(value: bool) -> None:
    if value:
        console.print(f"hook-trap v{__version__}")
        raise typer.Exit()


@cli.callback(invoke_without_command=True)
def default_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "-v",
        "-V",
        "--version",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """If no subcommand is given, default to running the server."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
