from io import StringIO

from rich.console import Console

from hook_trap.cli import CliRenderer


def test_cli_renderer_banner():
    buffer = StringIO()
    custom_console = Console(file=buffer, color_system=None, width=120)
    renderer = CliRenderer(custom_console)

    renderer.print_banner(
        host="127.0.0.1",
        port=8080,
        db_path="test.db",
        auto_forward="http://target/hooks",
        tunnel_url="https://xyz.trycloudflare.com",
    )

    output = buffer.getvalue()
    assert "HOOK-TRAP" in output
    assert "127.0.0.1:8080" in output
    assert "trycloudflare.com" in output
    assert "http://target/hooks" in output


def test_cli_renderer_tail_request():
    buffer = StringIO()
    custom_console = Console(file=buffer, color_system=None, width=120)
    renderer = CliRenderer(custom_console)

    req = {
        "method": "POST",
        "path": "/catch/c1/order",
        "timestamp": "2026-03-08T20:00:00Z",
        "body_size": 42,
        "client_ip": "1.2.3.4",
        "headers": {"X-Custom": "val"},
        "body": {"event": "purchase"},
    }

    renderer.render_tail_request(req, show_headers=True)
    output = buffer.getvalue()
    assert "POST" in output
    assert "/catch/c1/order" in output
    assert "X-Custom" in output
    assert "purchase" in output


def test_cli_renderer_replay_event():
    buffer = StringIO()
    custom_console = Console(file=buffer, color_system=None, width=120)
    renderer = CliRenderer(custom_console)

    rep = {
        "target_url": "http://localhost:3000/webhook",
        "status_code": 200,
        "latency_ms": 15.2,
    }
    renderer.render_replay_event(rep)
    output = buffer.getvalue()
    assert "REPLAY" in output
    assert "http://localhost:3000/webhook" in output
    assert "200" in output
