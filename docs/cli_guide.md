# Command Line Interface Guide

This document describes command line options, environment variables, and configuration practices for `hook-trap`.

## Commands

### `hook-trap serve`

Launches the web server, SQLite persistence engine, and dashboard. Running `hook-trap` without subcommands defaults to `serve`.

```bash
hook-trap serve [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--port` | `-p` | INTEGER | `8080` | Port to bind the HTTP and WebSocket server |
| `--host` | `-h` | TEXT | `127.0.0.1` | Network host interface |
| `--db-path` | | TEXT | `hook_trap.db` | File path for the SQLite database |
| `--auto-forward` | `-f` | TEXT | `None` | Default URL for automatic forwarding |
| `--tunnel` | `-t` | TEXT | `None` | Start a public HTTPS tunnel (`cloudflare`, `ngrok`, `auto`) |
| `--open-browser` | `-b` | BOOLEAN | `False` | Opens default web browser on launch |
| `--log-level` | | TEXT | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

#### Examples

Run on a custom port with a public Cloudflare tunnel:

```bash
hook-trap serve --port 8080 --tunnel cloudflare
```

Enable auto-forwarding for all incoming requests:

```bash
hook-trap serve --auto-forward http://localhost:3000/api/webhook
```

---

### `hook-trap tail <channel_id>`

Streams incoming webhooks live in your terminal using WebSockets without opening the browser.

```bash
hook-trap tail <channel_id> [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--host` | `-h` | TEXT | `127.0.0.1` | Server host |
| `--port` | `-p` | INTEGER | `8080` | Server port |
| `--headers` | | BOOLEAN | `False` | Display all request headers in terminal output |
| `--raw` | | BOOLEAN | `False` | Output raw JSON lines |

#### Examples

Stream events for channel `stripe_test`:

```bash
hook-trap tail stripe_test
```

Stream events including header tables:

```bash
hook-trap tail stripe_test --headers
```

---

## Environment Variables

All command line options can also be configured via environment variables prefixed with `HOOK_TRAP_`:

| Environment Variable | Equivalent Flag | Default | Description |
|---|---|---|---|
| `HOOK_TRAP_PORT` | `--port` | `8080` | HTTP port |
| `HOOK_TRAP_HOST` | `--host` | `127.0.0.1` | Host address |
| `HOOK_TRAP_DB_PATH` | `--db-path` | `hook_trap.db` | SQLite database file |
| `HOOK_TRAP_DEFAULT_AUTO_FORWARD_URL` | `--auto-forward` | `None` | Default auto-forward URL |
| `HOOK_TRAP_REPLAY_TIMEOUT` | | `10.0` | HTTP replay timeout in seconds |

Variables can be defined in a `.env` file in the project root directory.

---

## Running as a system service (systemd)

To run `hook-trap` persistently on a Linux machine:

```ini
# /etc/systemd/system/hook-trap.service
[Unit]
Description=hook-trap webhook inspector
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/hook-trap
ExecStart=/opt/hook-trap/.venv/bin/hook-trap --host 127.0.0.1 --port 8080 --db-path /var/lib/hook-trap/hook_trap.db
Restart=always

[Install]
WantedBy=multi-user.target
```
