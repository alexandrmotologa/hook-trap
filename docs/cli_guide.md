# Command Line Interface Guide

This document describes command line options, environment variables, and configuration practices for `hook-trap`.

## Commands

### `hook-trap`

Launches the web server, SQLite persistence engine, and dashboard.

```bash
hook-trap [OPTIONS]
```

### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--port` | `-p` | INTEGER | `8080` | Port to bind the HTTP and WebSocket server |
| `--host` | `-h` | TEXT | `127.0.0.1` | Network host interface |
| `--db-path` | | TEXT | `hook_trap.db` | File path for the SQLite database |
| `--auto-forward` | `-f` | TEXT | `None` | Default URL for automatic forwarding |
| `--open-browser` | `-b` | BOOLEAN | `False` | Opens default web browser on launch |
| `--log-level` | | TEXT | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

### Examples

Run on a custom port:

```bash
hook-trap --port 9000
```

Listen on all network interfaces (for Docker or local network sharing):

```bash
hook-trap --host 0.0.0.0 --port 8080
```

Specify a persistent database path in another directory:

```bash
hook-trap --db-path /var/lib/hook-trap/data.db
```

Launch and open the browser automatically:

```bash
hook-trap --open-browser
```

Enable auto-forwarding for all incoming requests:

```bash
hook-trap --auto-forward http://localhost:4000/webhooks
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
