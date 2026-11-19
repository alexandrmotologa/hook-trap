from typer.testing import CliRunner

from hook_trap import __version__
from hook_trap.cli import cli
from hook_trap.database import init_db, insert_webhook_request

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert f"hook-trap v{__version__}" in result.output


def test_cli_list_empty(tmp_path):
    db_file = str(tmp_path / "test_cli.db")
    result = runner.invoke(cli, ["list", "test_chan", "--db-path", db_file])
    assert result.exit_code == 0
    assert "No webhooks captured yet for channel test_chan" in result.output


def test_cli_list_and_show_with_records(tmp_path):
    import asyncio

    db_file = str(tmp_path / "test_cli.db")

    async def _setup():
        await init_db(db_file)
        return await insert_webhook_request(
            db_file,
            {
                "channel_id": "test_chan",
                "method": "POST",
                "path": "/catch/test_chan/v1/event",
                "headers": {"Content-Type": "application/json", "X-Key": "SecretVal"},
                "body_raw": '{"event": "test.ping", "amount": 100}',
                "body_json": {"event": "test.ping", "amount": 100},
                "client_ip": "127.0.0.1",
            },
        )

    req_id = asyncio.run(_setup())

    # Test list command
    list_res = runner.invoke(
        cli, ["list", "test_chan", "--db-path", db_file], env={"COLUMNS": "140"}
    )
    assert list_res.exit_code == 0
    assert "POST" in list_res.output
    assert "/catch/test_chan/v1/event" in list_res.output

    # Test show command
    show_res = runner.invoke(cli, ["show", "test_chan", req_id, "--db-path", db_file])
    assert show_res.exit_code == 0
    assert "test.ping" in show_res.output
    assert "X-Key" in show_res.output
    assert "SecretVal" in show_res.output


def test_cli_export_command(tmp_path):
    import asyncio

    db_file = str(tmp_path / "test_cli.db")
    out_file = str(tmp_path / "export.json")

    async def _setup():
        await init_db(db_file)
        await insert_webhook_request(
            db_file,
            {
                "channel_id": "export_chan",
                "method": "POST",
                "path": "/catch/export_chan",
                "headers": {"Content-Type": "application/json"},
                "body_raw": '{"exported": true}',
                "body_json": {"exported": True},
            },
        )

    asyncio.run(_setup())

    res = runner.invoke(
        cli,
        ["export", "export_chan", "--format", "json", "-o", out_file, "--db-path", db_file],
    )
    assert res.exit_code == 0
    assert "Successfully exported" in res.output
    assert tmp_path.joinpath("export.json").exists()


def test_cli_clear_command(tmp_path):
    import asyncio

    db_file = str(tmp_path / "test_cli.db")

    async def _setup():
        await init_db(db_file)
        await insert_webhook_request(
            db_file,
            {
                "channel_id": "clear_chan",
                "method": "POST",
                "path": "/catch/clear_chan",
                "body_raw": "data",
            },
        )

    asyncio.run(_setup())

    # Run clear with force flag
    res = runner.invoke(cli, ["clear", "clear_chan", "--force", "--db-path", db_file])
    assert res.exit_code == 0
    assert "Cleared channel clear_chan" in res.output

    # Verify empty
    list_res = runner.invoke(cli, ["list", "clear_chan", "--db-path", db_file])
    assert "No webhooks captured yet" in list_res.output
