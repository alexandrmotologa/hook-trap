import sys
import webbrowser

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hook_trap.config import settings
from hook_trap.server import create_app

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


def print_banner(host: str, port: int, db_path: str, auto_forward: str | None) -> None:
    """Render startup dashboard info using Rich."""
    title = Text("HOOK-TRAP", style="bold cyan")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold white", justify="right")
    grid.add_column(style="green")

    grid.add_row("Dashboard UI:", f"http://{host}:{port}/")
    grid.add_row("Webhook Ingestion:", f"http://{host}:{port}/catch/<channel_id>")
    grid.add_row("SQLite Database:", db_path)
    grid.add_row("Auto-Forward Target:", auto_forward if auto_forward else "[dim]Disabled[/dim]")

    panel = Panel(
        grid,
        title=title,
        subtitle="[dim]Press CTRL+C to stop the server[/dim]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


@cli.command()
def main(
    port: int = typer.Option(8080, "-p", "--port", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "-h", "--host", help="Network host interface"),
    db_path: str = typer.Option("hook_trap.db", "--db-path", help="Path to SQLite database file"),
    auto_forward: str | None = typer.Option(
        None, "-f", "--auto-forward", help="Default target URL to auto-forward incoming webhooks"
    ),
    open_browser: bool = typer.Option(
        False, "-b", "--open-browser", help="Automatically open browser dashboard upon startup"
    ),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level"),
) -> None:
    """Launch the hook-trap inspector and forwarding proxy server."""
    settings.host = host
    settings.port = port
    settings.db_path = db_path
    if auto_forward:
        settings.default_auto_forward_url = auto_forward

    print_banner(host=host, port=port, db_path=db_path, auto_forward=auto_forward)

    if open_browser:
        target_url = f"http://{host}:{port}/"
        try:
            webbrowser.open(target_url)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[dim]Could not auto-open browser: {exc}[/dim]")

    app = create_app(db_path=db_path, default_auto_forward_url=auto_forward)

    uvicorn_log_level = log_level.lower()
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=uvicorn_log_level,
    )


if __name__ == "__main__":
    cli()
